#!/usr/bin/env python3
"""bench/run_home_llm.py — Phase 3A: 真实 LLM pipeline 在持续世界连跑多任务

在同一个 reset_home 持续世界里,用 master/slaver LLM pipeline 连跑 N 个任务;
中间可注入漂移(inject_move),验证 per-home 学习完整链路:
  - location_memory 写入/命中/漂移清除(by slaver search_and_grasp)
  - ShadowState 跨任务持续(shadow 不在 set_task 时重置)
  - shadow_judge 作完成裁判(代替 stock quest oracle)

前置:
    redis-server
    cd master && python run.py          # :5000
    python slaver/run.py                # MCP slaver
    conda activate alfworld
    python serve_alfworld/main.py       # :5301

用法:
    python bench/run_home_llm.py                   # floorplan 1, 2个任务, 无漂移
    python bench/run_home_llm.py --drift           # Task1→Task2 之间注入漂移
    python bench/run_home_llm.py --floorplan 5 --obj cup --drift
    python bench/run_home_llm.py --tasks "put mug in shelf" "put mug in countertop"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid

import requests

MASTER = "http://127.0.0.1:5000"
BACKEND = "http://127.0.0.1:5301"

POLL = 2.0
TASK_TIMEOUT = 300.0


# ── HTTP 工具 ──────────────────────────────────────────────────────────────────

def _get(url: str, **kw) -> dict:
    try:
        return requests.get(url, timeout=20, **kw).json()
    except Exception as e:
        return {"error": str(e)}


def _post(url: str, body: dict, timeout: float = 60, **kw) -> dict:
    try:
        return requests.post(url, json=body, timeout=timeout, **kw).json()
    except Exception as e:
        return {"success": False, "error": str(e)}


def log(msg: str) -> None:
    from datetime import datetime
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


# ── per-home 持续世界 driver ───────────────────────────────────────────────────

class PersistentDriver:

    def __init__(self, master: str = MASTER, backend: str = BACKEND,
                 poll: float = POLL, task_timeout: float = TASK_TIMEOUT):
        self.master = master.rstrip("/")
        self.backend = backend.rstrip("/")
        self.poll = poll
        self.task_timeout = task_timeout

    # ── preflight ──────────────────────────────────────────────────────────────

    def preflight(self) -> bool:
        """确认 master 和 backend 在线。返回 False 则应退出。"""
        for name, url in [("backend", f"{self.backend}/scene_state"),
                          ("master", f"{self.master}/api/task_status")]:
            r = _get(url)
            if "error" in r:
                log(f"✗ {name} ({url}) 不可达: {r['error']}")
                log(f"  先启动对应服务(见文件头注释)")
                return False
            log(f"✓ {name} 在线")
        return True

    # ── 持续世界初始化 ──────────────────────────────────────────────────────────

    def reset_home(self, floorplan_id: str, split: str = "train") -> dict:
        """载入持续世界(仅调一次)。返回初始 snapshot。"""
        r = _post(f"{self.backend}/reset_home",
                  {"floorplan_id": floorplan_id, "split": split})
        if not r.get("success"):
            raise RuntimeError(f"reset_home 失败: {r}")
        snap = r.get("result", {})
        if not snap.get("persistent"):
            raise RuntimeError("persistent 未置位,reset_home 异常")
        return snap

    # ── 单个任务:LLM pipeline ─────────────────────────────────────────────────

    def set_task(self, task_text: str) -> None:
        """更新持续世界的当前任务文字(不重置 shadow/world)。"""
        r = _post(f"{self.backend}/set_task", {"task": task_text})
        if not r.get("success"):
            raise RuntimeError(f"set_task 失败: {r}")
        log(f"  task 已设置: {task_text}")
        if r.get("shadow_done_now"):
            log(f"  ⚠ shadow 已判完成(任务在 set 之前就满足了?)")

    def publish_and_wait(self, task_text: str) -> bool:
        """发任务给 master,轮询到 all_done,返回 shadow_judge 结果(via /success)。"""
        tid = uuid.uuid4().hex
        log(f"  → publish_task [{tid[:8]}]: {task_text[:60]}")
        pr = _post(f"{self.master}/publish_task",
                   {"task": task_text, "refresh": True, "task_id": tid},
                   timeout=self.task_timeout)
        if pr.get("status") != "success":
            log(f"  ! publish_task 失败: {str(pr)[:120]}")
            return False

        deadline = time.time() + self.task_timeout
        while time.time() < deadline:
            st = _get(f"{self.master}/api/task_status")
            if st.get("task_id") == tid and st.get("all_done"):
                break
            time.sleep(self.poll)
        else:
            log(f"  ! 任务 {tid[:8]} 超时({self.task_timeout}s)")

        # /success 在 persistent 模式下返回 shadow_judge 结果
        r = _get(f"{self.backend}/success")
        won = bool(r.get("won"))
        via = "shadow_judge" if r.get("shadow_judge") else "oracle"
        log(f"  ← won={won} (via {via})  steps={r.get('steps', '?')}")
        return won

    def run_task(self, task_text: str) -> dict:
        """完整跑一个任务:set_task → publish_and_wait → 返回结果 dict。"""
        steps_before = _get(f"{self.backend}/success").get("steps", 0)
        self.set_task(task_text)
        won = self.publish_and_wait(task_text)
        steps_after = _get(f"{self.backend}/success").get("steps", 0)
        shadow = _get(f"{self.backend}/shadow_state")
        shadow_at = shadow.get("at", {})
        holding = shadow.get("holding")
        log(f"  [debug] shadow.holding={holding}  shadow.at={dict(list(shadow_at.items())[:5])}")
        return {
            "task": task_text,
            "won": won,
            "steps": steps_after - steps_before,
            "shadow_at": shadow_at,
            "holding": holding,
        }

    # ── 漂移注入 ────────────────────────────────────────────────────────────────

    def inject_drift(self, obj: str, to: str = "cabinet") -> bool:
        """注入漂移:把物体挪到别处,并将 agent 复位到中性位置,避免 Task2 在注入目标处直接命中。"""
        r = _post(f"{self.backend}/inject_move", {"obj": obj, "to": to})
        ok = r.get("success", False)
        log(f"  [drift] inject_move {obj} → {to}: {'✓' if ok else '✗'} {r.get('result','')[:60]}")
        if ok:
            # inject 后 agent 停在 to(cabinet);导航到中性位置,确保 Task2 必须经过 hint 检查。
            nr = _post(f"{self.backend}/nav", {"target": "countertop"})
            log(f"  [drift] 中性复位 → countertop: {'✓' if nr.get('success') else '✗'} {nr.get('result','')[:40]}")
        return ok

    # ── 主序列 ──────────────────────────────────────────────────────────────────

    def run_sequence(self, floorplan_id: str, tasks: list[str],
                     inject_obj: str = "", inject_between: bool = False,
                     split: str = "train") -> list[dict]:
        """在同一个持续世界里顺序跑 tasks,可在第一个任务后注入漂移。"""
        log(f"\n{'='*60}")
        log(f"reset_home floorplan={floorplan_id}")
        snap = self.reset_home(floorplan_id, split)
        log(f"  stock task(借用世界,不执行): {snap.get('task','?')}")

        results = []
        for i, task in enumerate(tasks):
            log(f"\n── Task {i+1}/{len(tasks)}: {task} ──")
            result = self.run_task(task)
            results.append(result)
            log(f"  结果: won={result['won']}  steps={result['steps']}")

            # 任务间注入漂移(只在中间,不在最后)
            if inject_between and inject_obj and i < len(tasks) - 1:
                log(f"\n── inject drift({inject_obj}) ──")
                if not result["won"]:
                    log(f"  [注意] Task {i+1} won=False,agent 可能仍持有 {inject_obj};"
                        f" holding={result.get('holding')}; 仍尝试 inject(已修复持有时的 take 逻辑)")
                self.inject_drift(inject_obj)

        return results


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", default=MASTER)
    ap.add_argument("--backend", default=BACKEND)
    ap.add_argument("--floorplan", default="1")
    ap.add_argument("--split", default="train")
    ap.add_argument("--obj", default="mug", help="测试物体基名(用于 drift 注入)")
    ap.add_argument("--drift", action="store_true", help="Task1→Task2 之间注入漂移")
    ap.add_argument("--poll", type=float, default=POLL)
    ap.add_argument("--timeout", type=float, default=TASK_TIMEOUT)
    ap.add_argument("--tasks", nargs="+", default=None,
                    help="自定义任务列表;默认用 --obj 构造两个任务")
    args = ap.parse_args()

    obj = args.obj.strip().lower()

    # 默认两任务:Task1 建立记忆,Task2 测记忆命中(或漂移恢复)
    tasks = args.tasks or [
        f"put {obj} in shelf",
        f"put {obj} in countertop",
    ]

    d = PersistentDriver(args.master, args.backend, args.poll, args.timeout)

    if not d.preflight():
        return 2

    log(f"\nPhase 3A  floorplan={args.floorplan}  obj={obj}  drift={'ON' if args.drift else 'OFF'}")
    log(f"任务序列: {tasks}")

    results = d.run_sequence(
        floorplan_id=args.floorplan,
        tasks=tasks,
        inject_obj=obj if args.drift else "",
        inject_between=args.drift,
        split=args.split,
    )

    log(f"\n{'='*60}")
    log("Phase 3A 结果汇总:")
    all_won = True
    for i, r in enumerate(results, 1):
        tag = "✓" if r["won"] else "✗"
        log(f"  Task {i}: [{tag}] {r['task']}  steps={r['steps']}")
        all_won = all_won and r["won"]

    log(f"\n全部成功: {'✓' if all_won else '✗'}")
    if args.drift:
        log("(有漂移注入:Task2 预期步数 > Task1,位置记忆应在 Task1 后建立)")
    log("=" * 60)
    return 0 if all_won else 1


if __name__ == "__main__":
    sys.exit(main())
