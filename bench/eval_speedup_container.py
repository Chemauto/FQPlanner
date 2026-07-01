#!/usr/bin/env python3
"""bench/eval_speedup_container.py — Phase E: 藏容器版 memory_speedup 测试

动机(见 memory perhome-testbed-progress · Phase E):物体都在开放表面时,转头扫描一眼
看全 → 首次发现不贵 → speedup≈1(记忆省不下遍历)。把物体藏进高柜后:
  - 冷(belief 未知):走完逐工作点转头扫描(看不到藏的东西)再逐柜 open 翻找 = 贵
  - 热(belief 命中柜):直达 open 那个柜 = 便宜(1 步)
→ speedup = 热/冷 < 1 回来,学习曲线才有意义。

本脚本**直连 serve 直接驱动 slaver 的 _discover_object_waypoint**(不经 master LLM/redis),
所以只需要 serve(:5001,mujoco 模式)在跑。每次都是 fresh import → 直接吃 base.py 改动,
不用重启 slaver。步数用 serve /success 的 steps(nav 与 open 各计一步)。

前置:
    cd serve && python main.py --no-viewer      # :5001
    robot_api/config.yaml mujoco.enabled=1
    slaver/config.yaml perception: use_realtime_coords=false, backend=segmentation, camera=all

用法:
    python bench/eval_speedup_container.py                         # mug,默认容器
    python bench/eval_speedup_container.py --objs mug cup bowl
    python bench/eval_speedup_container.py --container cab_1_main_group
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import requests

# ── 让 base.py(及其 robot_api / waypoint_manager / scene_memory 依赖)可导入 ──
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (_REPO,
          os.path.join(_REPO, "slaver"),
          os.path.join(_REPO, "slaver", "robot"),
          os.path.join(_REPO, "slaver", "robot", "module"),
          os.path.join(_REPO, "serve")):
    if p not in sys.path:
        sys.path.insert(0, p)

SERVE = "http://127.0.0.1:5001"


def log(msg: str) -> None:
    from datetime import datetime
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def _steps() -> int:
    try:
        return int(requests.get(f"{SERVE}/success", timeout=10).json().get("steps", 0))
    except Exception:
        return -1


def _scan_visible() -> list:
    """转头扫描当前可见物体(camera=all),用于诊断藏/露是否生效。"""
    try:
        r = requests.get(f"{SERVE}/visible_objects", params={"camera": "all", "scan": 1}, timeout=60)
        return sorted(r.json().get("visible") or [])
    except Exception as e:
        return [f"<err {e}>"]


def _reset_home() -> None:
    r = requests.post(f"{SERVE}/reset_home", json={"floorplan_id": "1"}, timeout=180).json()
    if not r.get("success"):
        raise RuntimeError(f"reset_home 失败: {r}")


def _inject_to_container(obj: str, container: str) -> dict:
    return requests.post(f"{SERVE}/inject_to_container",
                         json={"obj": obj, "container": container}, timeout=60).json()


def _containers() -> list:
    r = requests.get(f"{SERVE}/containers", timeout=30).json()
    return r.get("containers") or []


def main() -> int:
    global SERVE
    ap = argparse.ArgumentParser()
    ap.add_argument("--objs", nargs="+", default=["mug"], help="测试物体基名(默认 mug)")
    ap.add_argument("--container", default=None, help="藏物容器名(默认取 /containers 里含 cab_1 的,否则第一个)")
    ap.add_argument("--serve", default="http://127.0.0.1:5001")
    args = ap.parse_args()

    SERVE = args.serve.rstrip("/")

    # preflight
    try:
        requests.get(f"{SERVE}/success", timeout=5)
    except Exception as e:
        log(f"✗ serve ({SERVE}) 不可达: {e}  先 cd serve && python main.py --no-viewer")
        return 2

    # fresh import → 吃 base.py 最新改动
    from base import _discover_object_waypoint, _list_containers  # noqa: E402
    sys.path.insert(0, os.path.join(_REPO, "serve"))
    from scene import scene_memory as sm  # noqa: E402

    containers = _containers()
    if not containers:
        log("✗ /containers 返回空 —— 场景没有可藏物的高柜(或 serve 未更新代码)。"
            " 确认 serve 已重启加载新 /containers 端点。")
        return 1
    cnames = [c["name"] for c in containers]
    log(f"可藏容器({len(cnames)}): {cnames}")

    container = args.container
    if container not in cnames:
        container = next((n for n in cnames if "cab_1" in n), cnames[0])
    log(f"用容器: {container}")

    rows = []
    for obj in args.objs:
        log(f"\n{'#'*64}\n# 物体 {obj}\n{'#'*64}")
        _reset_home()
        log(f"  reset_home 完成(belief 清空,物体归开放表面)")

        # 藏进容器
        r = _inject_to_container(obj, container)
        if not r.get("success"):
            log(f"  ✗ inject_to_container 失败: {r}; 跳过 {obj}")
            continue
        vis = _scan_visible()
        hidden_ok = obj not in vis
        log(f"  藏 {obj} → {container};转头可见={vis}  → {obj} {'看不到✓(藏住了)' if hidden_ok else '仍可见✗(没藏住,测试前提不成立)'}")

        # ── 冷:belief 未知 → 逐工作点扫描(扫不到)+ 逐柜翻找 ──
        s0 = _steps()
        t0 = time.time()
        ok_c, msg_c = _discover_object_waypoint(obj)
        cold = _steps() - s0
        log(f"  [冷] discover: ok={ok_c} steps={cold} ({time.time()-t0:.0f}s)  {msg_c}")
        belief_after_cold = sm.get_object_location(obj)
        log(f"       belief 现在 = {belief_after_cold}  (期望=容器名 {container})")

        # ── 重新藏回同一柜(belief 保持容器名),准备测"命中柜直达" ──
        _inject_to_container(obj, container)

        # ── 热:belief 命中容器 → 直达 open 那个柜 ──
        s1 = _steps()
        t1 = time.time()
        ok_w, msg_w = _discover_object_waypoint(obj)
        warm = _steps() - s1
        log(f"  [热] discover: ok={ok_w} steps={warm} ({time.time()-t1:.0f}s)  {msg_w}")

        speedup = (warm / cold) if cold else float("nan")
        rows.append({"obj": obj, "container": container, "cold": cold, "warm": warm,
                     "cold_ok": ok_c, "warm_ok": ok_w, "hidden_ok": hidden_ok,
                     "speedup": speedup})
        log(f"  → speedup(热/冷) = {warm}/{cold} = {speedup:.3f}")

    if not rows:
        log("✗ 无有效样本")
        return 1

    log("\n" + "=" * 64)
    log(f"{'obj':>8} {'container':>20} {'cold':>5} {'warm':>5} {'speedup':>8} {'ok':>4}")
    log("-" * 64)
    valid = [r for r in rows if r["cold_ok"] and r["warm_ok"]]
    for r in rows:
        ok = "✓" if (r["cold_ok"] and r["warm_ok"]) else "✗"
        log(f"{r['obj']:>8} {r['container']:>20} {r['cold']:>5} {r['warm']:>5} "
            f"{r['speedup']:>8.3f} {ok:>4}")
    log("=" * 64)
    if valid:
        mean_speedup = sum(r["speedup"] for r in valid) / len(valid)
        log(f"  有效样本: {len(valid)}/{len(rows)}")
        log(f"  mean memory_speedup = {mean_speedup:.3f}   (< 1.0 = 记忆更快,藏容器学习曲线回来了)")
        log(f"  {'✓ speedup<1 成立' if mean_speedup < 1.0 else '✗ speedup≥1,未达预期'}")
    log("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
