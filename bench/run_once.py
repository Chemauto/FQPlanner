#!/usr/bin/env python3
"""
bench/run_once.py — 把一批固定任务「只跑一遍」,报告每个任务 won/fail。

用途:做受控对比(比如「修了某个 bug 之后,同样这 10 个任务结果有没有变」)。
不带 checkpoint / 不带留出评测 —— 就是单纯把 train[i..j] 各跑一次。

默认「空经验 + 冻结」:每个任务前后快照/还原经验库,所以
  - 不受上次跑遗留的脏经验影响(配 --reset-experience 从空开始最干净)
  - 这次也不会把新经验写进去污染后续
=> 测到的差异可干净归因到「代码改动」,而不是经验变化。

前置:redis + master(:5000)+ slaver + serve_alfworld(:5301)都在跑;
      改过 serve_alfworld 的话要先重启它再跑。

    python bench/run_once.py                      # train[0..9],空经验冻结,跑一遍
    python bench/run_once.py --reset-experience   # 跑前先把现有经验库备份清空
    python bench/run_once.py --indices 0-9 --no-freeze --learn   # 让它边跑边写经验
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_curve import Driver, snapshot_skills, restore_skills, backup_and_clear_skills, DEFAULT_SKILLS_DIR, log

HERE = os.path.dirname(os.path.abspath(__file__))


def parse_indices(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return out


def main():
    p = argparse.ArgumentParser(description="同一批固定任务只跑一遍,报告 won/fail")
    p.add_argument("--master", default="http://127.0.0.1:5000")
    p.add_argument("--backend", default="http://127.0.0.1:5301")
    p.add_argument("--skills-dir", default=DEFAULT_SKILLS_DIR)
    p.add_argument("--split", default="train")
    p.add_argument("--indices", default="0-9", help="如 '0-9' 或 '0,2,5'")
    p.add_argument("--seed", type=int, default=int(os.environ.get("ALFWORLD_SEED", 0)))
    p.add_argument("--poll", type=float, default=2.0)
    p.add_argument("--task-timeout", type=float, default=300.0)
    p.add_argument("--reset-experience", action="store_true", help="跑前备份并清空经验库")
    p.add_argument("--no-freeze", dest="freeze", action="store_false",
                   help="不冻结:让经验在任务间累积(默认冻结,每任务后还原)")
    p.add_argument("--extract", action="store_true", default=True,
                   help="跑完自动抽取轨迹到 bench/traces_once/(默认开)")
    p.add_argument("--no-extract", dest="extract", action="store_false")
    p.add_argument("--yes", action="store_true")
    args = p.parse_args()

    indices = parse_indices(args.indices)
    log("=" * 60)
    log(f"split={args.split}  indices={indices}  seed={args.seed}")
    log(f"经验:{'reset+' if args.reset_experience else ''}{'冻结(不累积)' if args.freeze else '累积'}")
    log(f"任务数={len(indices)}(只跑一遍)")
    log("⚠ 确认改过的 serve_alfworld 已重启,否则测的是旧代码!")
    log("=" * 60)
    if not args.yes and input("开跑?(y/N) ").strip().lower() not in ("y", "yes"):
        return

    # seed 校验
    import requests
    try:
        info = requests.get(f"{args.backend}/dataset_info", params={"split": args.split}, timeout=60).json()
        if info.get("seed") is not None and int(info["seed"]) != int(args.seed):
            sys.exit(f"✗ seed 不一致:后端={info['seed']} vs --seed={args.seed}。"
                     f"用 ALFWORLD_SEED={args.seed} 重启后端。")
    except SystemExit:
        raise
    except Exception as e:
        sys.exit(f"✗ 后端不可达: {e}")

    if args.reset_experience:
        backup = backup_and_clear_skills(args.skills_dir)
        log(f"经验库已备份→{backup} 并清空")

    d = Driver(args)
    start = datetime.now()
    results = []
    for n, i in enumerate(indices, 1):
        snap = snapshot_skills(args.skills_dir) if args.freeze else None
        log(f"  [{n}/{len(indices)}] 正在跑 {args.split}[{i}] (最长 {int(args.task_timeout)}s)...")
        won = d.run_one_task(args.split, i)
        if args.freeze:
            restore_skills(args.skills_dir, snap)  # 丢弃本任务写入,保持空/冻结
        results.append((i, won))
        log(f"  [{n}/{len(indices)}] {args.split}[{i}]  won={won}")
    end = datetime.now()

    wins = sum(1 for _, w in results if w)
    log("=" * 60)
    log("结果:")
    for i, w in results:
        log(f"  {args.split}[{i}]  {'✅ WON' if w else '❌ fail'}")
    log(f"成功率: {wins}/{len(results)} = {wins / len(results):.3f}")
    log("=" * 60)

    if args.extract:
        out_dir = os.path.join(HERE, "traces_once")
        log(f"抽取本次轨迹 → {out_dir}/ …")
        subprocess.run([sys.executable, os.path.join(HERE, "extract_traces.py"),
                        "--since", start.strftime("%H:%M:%S"),
                        "--until", end.strftime("%H:%M:%S"),
                        "--out-dir", out_dir], check=False)


if __name__ == "__main__":
    main()
