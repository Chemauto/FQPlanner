#!/usr/bin/env python3
"""
bench/run_repeat.py — Phase 0 体检：同一个任务重复跑 N 次，经验在轮次间累积。

问题："经验有没有让步数下降（成功率保持）？"

用法：
    python bench/run_repeat.py --index 3 --repeats 8 --reset-experience --yes
    python bench/run_repeat.py --index 3 --repeats 8 --yes              # 不清空经验

对照实验：
    # 先用低探索率（真正用经验）
    EXPLORATION_RATE=0.1 python master/run.py
    python bench/run_repeat.py --index 3 --repeats 8 --reset-experience --yes

    # 再用高探索率（忽略经验，做对照）
    EXPLORATION_RATE=0.9 python master/run.py   # 重启
    python bench/run_repeat.py --index 3 --repeats 8 --reset-experience --yes

输出：bench/repeat_results.csv（run_k, won, steps）+ 终端打印
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
import uuid
from datetime import datetime

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_curve import (
    Driver,
    backup_and_clear_skills,
    log,
    DEFAULT_SKILLS_DIR,
)

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUT = os.path.join(HERE, "repeat_results.csv")


def run_one_task_with_steps(d: Driver, split: str, index: int) -> tuple[bool, int]:
    """同 run_one_task，但额外从后端读 steps。"""
    try:
        task_text = d.backend_reset_to(split, index)
    except Exception as e:
        log(f"  ! reset_to({split},{index}) 失败: {e}")
        return False, -1
    if not task_text:
        log(f"  ! {split}[{index}] 没解析出任务文本，记为失败")
        return False, -1

    tid = uuid.uuid4().hex
    try:
        pr = requests.post(
            f"{d.master}/publish_task",
            json={"task": task_text, "refresh": True, "task_id": tid},
            timeout=d.task_timeout,
        )
        if pr.status_code != 200:
            log(f"  ! publish 失败({pr.status_code}): {pr.text[:160]}")
            return False, -1
    except Exception as e:
        log(f"  ! publish 异常: {e}")
        return False, -1

    deadline = time.time() + d.task_timeout
    while time.time() < deadline:
        try:
            st = requests.get(f"{d.master}/api/task_status", timeout=15).json()
        except Exception:
            time.sleep(d.poll)
            continue
        if st.get("task_id") == tid and st.get("all_done"):
            break
        time.sleep(d.poll)
    else:
        log(f"  ! task {tid[:8]} 超时({d.task_timeout}s)，记为失败")

    try:
        resp = requests.get(f"{d.backend}/success", timeout=30).json()
        return bool(resp.get("won")), int(resp.get("steps", -1))
    except Exception as e:
        log(f"  ! 读 won/steps 失败: {e}")
        return False, -1


def main():
    p = argparse.ArgumentParser(description="Phase 0：同一任务重复跑 N 次，观察步数是否下降")
    p.add_argument("--master", default="http://127.0.0.1:5000")
    p.add_argument("--backend", default="http://127.0.0.1:5301")
    p.add_argument("--skills-dir", default=DEFAULT_SKILLS_DIR)
    p.add_argument("--split", default="train")
    p.add_argument("--index", type=int, default=0, help="锁定的 game index（train[N]）")
    p.add_argument("--repeats", type=int, default=8, help="重复次数（默认 8）")
    p.add_argument("--seed", type=int, default=int(os.environ.get("ALFWORLD_SEED", 0)))
    p.add_argument("--poll", type=float, default=2.0)
    p.add_argument("--task-timeout", type=float, default=300.0)
    p.add_argument("--out", default=DEFAULT_OUT, help="输出 CSV 路径")
    p.add_argument("--reset-experience", action="store_true", help="跑前备份并清空经验库")
    p.add_argument("--yes", action="store_true", help="跳过确认提示")
    args = p.parse_args()

    log("=" * 60)
    log(f"Phase 0 体检：{args.split}[{args.index}] × {args.repeats} 轮")
    log(f"经验：{'reset+累积' if args.reset_experience else '接续当前经验库，累积'}")
    log(f"输出：{args.out}")
    log("前置：redis + master(:5000) + slaver + serve_alfworld(:5301) 都在跑")
    log("=" * 60)
    if not args.yes and input("开跑?(y/N) ").strip().lower() not in ("y", "yes"):
        return

    # 校验后端可达
    try:
        info = requests.get(
            f"{args.backend}/dataset_info", params={"split": args.split}, timeout=60
        ).json()
        if info.get("seed") is not None and int(info["seed"]) != args.seed:
            sys.exit(
                f"✗ seed 不一致：后端={info['seed']} vs --seed={args.seed}。"
                f"用 ALFWORLD_SEED={args.seed} 重启后端。"
            )
    except SystemExit:
        raise
    except Exception as e:
        sys.exit(f"✗ 后端不可达: {e}")

    # 校验 master 可达 + exploration_rate
    try:
        er = requests.get(f"{args.master}/api/exploration_rate", timeout=10).json()
        rate = float(er.get("exploration_rate", 1.0))
        log(f"master exploration_rate = {rate}")
        if rate > 0.3:
            log(f"⚠  exploration_rate={rate} 偏高（>0.3），LLM 大概率忽略经验，步数曲线会平。")
            log("   对照实验（高探索率）请确认这是有意为之。")
    except Exception as e:
        sys.exit(f"✗ master 不可达: {e}")

    if args.reset_experience:
        backup = backup_and_clear_skills(args.skills_dir)
        log(f"经验库已备份 → {backup} 并清空")

    d = Driver(args)
    results: list[tuple[int, bool, int]] = []  # (run_k, won, steps)

    for k in range(1, args.repeats + 1):
        log(f"\n--- 第 {k}/{args.repeats} 轮 ---")
        won, steps = run_one_task_with_steps(d, args.split, args.index)
        results.append((k, won, steps))
        log(f"  结果：won={won}  steps={steps}")

    # 输出 CSV
    os.makedirs(os.path.dirname(args.out) if os.path.dirname(args.out) else ".", exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["run_k", "won", "steps"])
        w.writerows(results)

    log("\n" + "=" * 60)
    log("结果汇总：")
    log(f"  {'run_k':>6}  {'won':>5}  {'steps':>6}")
    for k, won, steps in results:
        log(f"  {k:>6}  {'✅' if won else '❌':>5}  {steps:>6}")
    wins = sum(1 for _, w, _ in results if w)
    valid_steps = [s for _, _, s in results if s >= 0]
    log(f"\n  成功率：{wins}/{args.repeats}")
    if valid_steps:
        log(f"  步数：首轮={valid_steps[0]}  末轮={valid_steps[-1]}  趋势={'↓降' if valid_steps[-1] < valid_steps[0] else '→平/↑升'}")
    log(f"\n  CSV → {args.out}")
    log("=" * 60)
    log("判读：步数降了且 won 保持 = 记忆管线通；步数平 = 先修经验机制再建 Phase 1-3。")


if __name__ == "__main__":
    main()
