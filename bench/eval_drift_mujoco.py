#!/usr/bin/env python3
"""bench/eval_drift_mujoco.py — MuJoCo 版漂移恢复批量量化(走 master/slaver LLM 链路)

对应 ALFWorld 的 eval_drift.py,但 MuJoCo 经真 LLM pipeline(master 规划 + slaver 执行),
而非 ALFWorld 那个脚本化 agent。复用 run_home_llm.py 的 PersistentDriver。

对每个物体跑**两条独立序列**(各自 reset_home → 清空 belief、物体归初始):
  no-drift : Task1 put X in <t1>(发现建记忆) → Task2 put X in <t2>(记忆命中直达)
  drift    : Task1 put X in <t1>           → inject X→cabinet → Task2(belief 扑空→重搜恢复)

汇总(三个能从 bench 侧拿到的指标):
  memory_speedup      = mean(t2_nodrift_steps) / mean(t1_steps)        [<1 = 记忆更快]
  drift_recover_rate  = drift 轮 Task2 won 比例                         [漂移后仍完成]
  drift_step_overhead = mean(t2_drift_steps) / mean(t2_nodrift_steps)  [>1 = 漂移代价]

注:drift_detect_rate(belief 扑空被察觉)的信号在 slaver stderr 的
   "[base] ⚠ 漂移检测:..." 行,bench 进程拿不到;这里由 step_overhead>1 间接体现
   (步数变多正是因为扑空后重遍历)。要精确 detect 率需让 server 暴露计数端点。

前置:serve(:5001,mujoco 模式) + master(:5000) + slaver + redis 都在跑,
     robot_api/config.yaml 切到 mujoco(改完重启 master+slaver)。

用法:
    python bench/eval_drift_mujoco.py                              # 默认 mug cup bowl
    python bench/eval_drift_mujoco.py --objs mug cup bowl apple pot
    python bench/eval_drift_mujoco.py --t1 sink --t2 stove --out bench/drift_mujoco.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_home_llm import PersistentDriver, log


def _trial(d: PersistentDriver, obj: str, t1_recep: str, t2_recep: str,
           with_drift: bool, floorplan: str, split: str) -> tuple[dict, dict]:
    """跑一条序列:reset_home(清 belief) → Task1 建记忆 →[可选 inject]→ Task2。返回 (t1, t2)。"""
    tag = "drift" if with_drift else "no-drift"
    log(f"\n{'#' * 60}\n# 物体 {obj} · {tag} 轮\n{'#' * 60}")
    d.reset_home(floorplan, split)
    t1 = d.run_task(f"put {obj} in {t1_recep}")
    if with_drift:
        log(f"\n── inject drift({obj}) ──")
        d.inject_drift(obj)
    t2 = d.run_task(f"put {obj} in {t2_recep}")
    return t1, t2


def _mean(xs: list) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", default="http://127.0.0.1:5000")
    ap.add_argument("--backend", default="http://127.0.0.1:5001")
    ap.add_argument("--floorplan", default="1")
    ap.add_argument("--split", default="train")
    ap.add_argument("--objs", nargs="+", default=["mug", "cup", "bowl"],
                    help="测试物体基名列表(默认 mug cup bowl)")
    ap.add_argument("--t1", default="sink", help="Task1 放置目标(建记忆)")
    ap.add_argument("--t2", default="stove", help="Task2 放置目标(测命中/恢复)")
    ap.add_argument("--poll", type=float, default=2.0)
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--out", default=None, help="CSV 输出路径(可选)")
    args = ap.parse_args()

    d = PersistentDriver(args.master, args.backend, args.poll, args.timeout)
    if not d.preflight():
        return 2

    log("=" * 72)
    log(f"MuJoCo 漂移批量量化  objs={args.objs}  任务: put X in {args.t1} → {args.t2}")
    log(f"每物体 4 个 LLM 任务(no-drift 2 + drift 2),共 {len(args.objs) * 4} 个")
    log("=" * 72)

    rows = []
    for obj in args.objs:
        try:
            t1_nd, t2_nd = _trial(d, obj, args.t1, args.t2, False, args.floorplan, args.split)
            t1_d, t2_d = _trial(d, obj, args.t1, args.t2, True, args.floorplan, args.split)
        except Exception as e:
            log(f"  ! 物体 {obj} 跑挂: {e}")
            continue
        rows.append({
            "obj": obj,
            "t1_steps": t1_nd["steps"], "t1_won": t1_nd["won"],
            "t2_nodrift_steps": t2_nd["steps"], "t2_nodrift_won": t2_nd["won"],
            "t2_drift_steps": t2_d["steps"], "t2_drift_won": t2_d["won"],
        })

    if not rows:
        log("✗ 没有有效样本")
        return 1

    # memory_speedup / step_overhead 的 steps 只在任务真完成时有意义,故按 won 过滤分母
    valid_nd = [r for r in rows if r["t1_won"] and r["t2_nodrift_won"]]
    valid_d = [r for r in rows if r["t2_drift_won"]]
    avg_t1 = _mean([r["t1_steps"] for r in valid_nd])
    avg_t2_nd = _mean([r["t2_nodrift_steps"] for r in valid_nd])
    avg_t2_d = _mean([r["t2_drift_steps"] for r in valid_d])

    memory_speedup = avg_t2_nd / avg_t1 if avg_t1 and avg_t1 == avg_t1 else float("nan")
    recover_rate = sum(1 for r in rows if r["t2_drift_won"]) / len(rows)
    step_overhead = avg_t2_d / avg_t2_nd if avg_t2_nd and avg_t2_nd == avg_t2_nd else float("nan")

    log("\n" + "=" * 72)
    log(f"{'obj':>6} {'t1':>4} {'t2_nd':>6} {'t2_drf':>7} {'nd_won':>7} {'drf_won':>8}")
    log("-" * 72)
    for r in rows:
        log(f"{r['obj']:>6} {r['t1_steps']:>4} {r['t2_nodrift_steps']:>6} "
            f"{r['t2_drift_steps']:>7} {str(r['t2_nodrift_won']):>7} {str(r['t2_drift_won']):>8}")
    log("=" * 72)
    log(f"  有效样本(no-drift): {len(valid_nd)}/{len(rows)}   (drift won): {len(valid_d)}/{len(rows)}")
    log(f"  avg t1 steps:            {avg_t1:.1f}")
    log(f"  avg t2 steps (no drift): {avg_t2_nd:.1f}")
    log(f"  avg t2 steps (drift):    {avg_t2_d:.1f}")
    log("")
    log(f"  memory_speedup      = {memory_speedup:.3f}   (< 1.0 = 记忆更快)")
    log(f"  drift_recover_rate  = {recover_rate:.1%}  (漂移后仍完成任务)")
    log(f"  drift_step_overhead = {step_overhead:.3f}   (> 1.0 = 漂移增加步数)")
    log(f"  drift_detect        见 slaver stderr '[base] ⚠ 漂移检测' 行(bench 侧拿不到)")
    log("=" * 72)

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        log(f"\n  结果已写入: {args.out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
