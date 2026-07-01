#!/usr/bin/env python3
"""bench/eval_drift.py — Phase 3B: 漂移恢复率量化评估

对 N 个 home 各跑两轮(无漂移 + 有漂移),量化:
  memory_speedup     : avg(task2_nodrift_steps) / avg(task1_steps)  [< 1.0 = 记忆更快]
  drift_detect_rate  : 漂移被正确检测(hint miss)的比例
  drift_recover_rate : 漂移后仍能完成任务的比例
  drift_step_overhead: avg(task2_drift_steps) / avg(task2_nodrift_steps)  [> 1.0 = 漂移代价]

用法:
    python bench/eval_drift.py               # 跑前 10 个 home
    python bench/eval_drift.py --homes 20
    python bench/eval_drift.py --obj cup
    python bench/eval_drift.py --out results/drift_eval.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import urllib.request
from typing import Optional

# ── 路径 ──────────────────────────────────────────────────────────────────────
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOCATION_MEMORY_FILE = os.path.join(_REPO_ROOT, "master", "memory", "location_memory.json")

_HOST = "127.0.0.1"
_PORT = 5301


# ── HTTP ──────────────────────────────────────────────────────────────────────

def _get(path: str, timeout: float = 20.0) -> dict:
    url = f"http://{_HOST}:{_PORT}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)}


def _post(path: str, body: dict, timeout: float = 30.0) -> dict:
    url = f"http://{_HOST}:{_PORT}{path}"
    try:
        req = urllib.request.Request(
            url, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"success": False, "result": str(e)}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())


def _base(s: str) -> str:
    return re.sub(r"\s*\d+$", "", _norm(s))


def _admissible() -> list[str]:
    return _get("/scene_state").get("admissible_commands", [])


def _steps() -> int:
    return _get("/success").get("steps", -1)


# ── location memory ───────────────────────────────────────────────────────────

def _read_mem() -> dict:
    try:
        if os.path.exists(_LOCATION_MEMORY_FILE):
            with open(_LOCATION_MEMORY_FILE, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _write_mem(mem: dict) -> None:
    os.makedirs(os.path.dirname(_LOCATION_MEMORY_FILE), exist_ok=True)
    with open(_LOCATION_MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(mem, f, indent=2, ensure_ascii=False)


def _get_hint(obj_base: str) -> Optional[str]:
    return _read_mem().get(obj_base, {}).get("location")


def _set_hint(obj_base: str, location: str) -> None:
    mem = _read_mem()
    mem[obj_base] = {"location": location}
    _write_mem(mem)


def _clear_hint(obj_base: str) -> None:
    mem = _read_mem()
    if obj_base in mem:
        del mem[obj_base]
        _write_mem(mem)


# ── scripted agent ────────────────────────────────────────────────────────────

_CONTAINERS = ("cabinet", "drawer", "fridge", "microwave", "safe", "box")


def _find_take(obj_base: str, admissible: list[str]) -> Optional[str]:
    for cmd in admissible:
        c = _norm(cmd)
        if c.startswith("take ") and obj_base in c:
            return cmd
    return None


def _find_put(obj_base: str, recep_base: str, admissible: list[str]) -> Optional[str]:
    for cmd in admissible:
        c = _norm(cmd)
        if (c.startswith("put ") or c.startswith("move ")) and obj_base in c and recep_base in c:
            return cmd
    return None


def _loc_from_take(take_cmd: str) -> str:
    m = re.search(r" from (.+)$", _norm(take_cmd))
    return m.group(1).strip() if m else ""


def _loc_from_put(put_cmd: str) -> str:
    m = re.search(r" (?:in(?:to)?|on(?:to)?|to) (.+)$", _norm(put_cmd))
    return m.group(1).strip() if m else ""


def _search_and_grasp(obj_base: str, drift_log: list) -> tuple[bool, str]:
    adm = _admissible()
    take = _find_take(obj_base, adm)
    if take:
        r = _post("/raw", {"command": take})
        if r.get("success"):
            return True, f"当前位置 ({_loc_from_take(take)})"

    all_gos = [c for c in _admissible() if _norm(c).startswith("go to ")]

    hint = _get_hint(obj_base)
    if hint:
        h_norm = _norm(hint)
        for go in all_gos:
            if h_norm in _norm(go):
                _post("/raw", {"command": go})
                take = _find_take(obj_base, _admissible())
                if take:
                    r = _post("/raw", {"command": take})
                    if r.get("success"):
                        return True, f"记忆命中 ({hint})"
                _clear_hint(obj_base)
                drift_log.append(True)
                break

    all_gos = [c for c in _admissible() if _norm(c).startswith("go to ")]
    surfaces = [g for g in all_gos if not any(k in g.lower() for k in _CONTAINERS)]
    containers = [g for g in all_gos if any(k in g.lower() for k in _CONTAINERS)]

    for go in surfaces + containers:
        _post("/raw", {"command": go})
        take = _find_take(obj_base, _admissible())
        if take:
            r = _post("/raw", {"command": take})
            if r.get("success"):
                return True, f"第一遍 ({_loc_from_take(take)})"

    for go in containers:
        _post("/raw", {"command": go})
        for oc in [c for c in _admissible() if _norm(c).startswith("open ")]:
            r_op = _post("/raw", {"command": oc})
            if "nothing happens" in _norm(r_op.get("result", "")):
                continue
            take = _find_take(obj_base, _admissible())
            if take:
                r = _post("/raw", {"command": take})
                if r.get("success"):
                    return True, f"第二遍 ({_loc_from_take(take)})"

    return False, "未找到"


def _navigate_and_put(obj_base: str, recep_base: str) -> tuple[bool, str]:
    all_gos = [c for c in _admissible() if _norm(c).startswith("go to ")]
    for go in (g for g in all_gos if recep_base in _norm(g)):
        _post("/raw", {"command": go})
        put = _find_put(obj_base, recep_base, _admissible())
        if put:
            r = _post("/raw", {"command": put})
            if r.get("success"):
                return True, _loc_from_put(put)
    return False, ""


def _navigate_and_put_any(obj_base: str, candidates: list[str],
                          exclude: str = "") -> tuple[bool, str, str]:
    """Try receptacle candidates in order; returns (ok, recep_used, specific_loc)."""
    for recep in candidates:
        if exclude and recep == exclude:
            continue
        all_gos = [c for c in _admissible() if _norm(c).startswith("go to ")]
        for go in (g for g in all_gos if recep in _norm(g)):
            _post("/raw", {"command": go})
            put = _find_put(obj_base, recep, _admissible())
            if put:
                r = _post("/raw", {"command": put})
                if r.get("success"):
                    return True, recep, _loc_from_put(put)
    return False, "", ""


def _find_inject_target() -> Optional[str]:
    """Return the base name of the first available closed container (for inject_move)."""
    all_gos = _admissible()
    for container in ("cabinet", "drawer", "fridge", "microwave", "safe"):
        if any(container in _norm(c) for c in all_gos if _norm(c).startswith("go to ")):
            return container
    return None


def _navigate_neutral(*exclude: str) -> None:
    """Navigate to any open (non-container) location not matching any exclude term.

    Used after inject_move. Must avoid BOTH the injection site (so the agent
    doesn't immediately see the injected object) AND recep_a (so that
    'go to <recep_a>' is still available in admissible — if the agent is already
    AT recep_a, that go-to disappears and the hint path is silently skipped).
    Falls back to any non-excluded location if no open surface exists.
    """
    all_gos = [c for c in _admissible() if _norm(c).startswith("go to ")]
    excl = [_norm(e) for e in exclude if e]

    def _ok(go_cmd: str) -> bool:
        gn = _norm(go_cmd)
        return not any(e in gn for e in excl) and not any(k in gn for k in _CONTAINERS)

    target = next((g for g in all_gos if _ok(g)), None)
    if target is None:
        # Fallback: at least avoid excluded locations (container ok)
        target = next((g for g in all_gos if not any(e in _norm(g) for e in excl)), None)
    if target:
        _post("/raw", {"command": target})


def _reset_to_open_surface() -> None:
    """Navigate to any open (non-container) surface to maximize go-to reachability.

    After search_and_grasp traverses containers, the agent can end up in a
    low-connectivity sub-location (e.g. drawer 3). Moving to an open surface
    first ensures all go-to commands are available for the put step.
    """
    all_gos = [c for c in _admissible() if _norm(c).startswith("go to ")]
    open_gos = [g for g in all_gos if not any(k in _norm(g) for k in _CONTAINERS)]
    if open_gos:
        _post("/raw", {"command": open_gos[0]})


# ── single home trial ─────────────────────────────────────────────────────────

def _eval_trial(fid: str, obj: str, split: str, with_drift: bool) -> dict:
    """Run one trial. Returns metrics dict; 'error' key set on skip."""
    _clear_hint(obj)

    r = _post("/reset_home", {"floorplan_id": fid, "split": split})
    if not r.get("success") or not r.get("result", {}).get("persistent"):
        return {"home": fid, "drift": with_drift, "error": "reset_home failed"}

    # Task 1 目标候选:尽量不用 countertop/sinkbasin（留给 Task 2 优先），
    # 但末尾保留作兜底,否则纯厨房 home 会全部失败。
    _T1_CANDS = ["shelf", "sidetable", "diningtable", "sofa", "armchair", "bed",
                 "desk", "ottoman", "coffeetable", "dresser",
                 "countertop", "sinkbasin", "stoveburner"]
    # Task 2 目标候选:不同于 Task 1（由 exclude=recep_a 保证）
    _T2_CANDS = ["countertop", "sinkbasin", "sidetable", "diningtable", "sofa",
                 "armchair", "shelf", "stoveburner", "desk", "coffeetable"]

    # Task 1: search + put in 第一个可用的 Task1 目标
    s0 = _steps()
    drift_t1: list = []
    ok1, _ = _search_and_grasp(obj, drift_t1)
    if not ok1:
        return {"home": fid, "drift": with_drift, "error": f"task1 search failed ({obj} not found)"}
    _reset_to_open_surface()   # 搜索后可能留在封闭容器里,复位提高 go-to 可达性
    ok_p1, recep_a, put_loc1 = _navigate_and_put_any(obj, _T1_CANDS)
    if not ok_p1:
        return {"home": fid, "drift": with_drift, "error": f"task1 put failed (tried all {len(_T1_CANDS)} candidates)"}
    steps_t1 = _steps() - s0
    _set_hint(obj, put_loc1)

    # Inject drift
    inject_target = _find_inject_target()
    if with_drift:
        if not inject_target:
            return {"home": fid, "drift": with_drift, "error": "no container for inject"}
        r_inj = _post("/inject_move", {"obj": obj, "to": inject_target})
        if not r_inj.get("success"):
            return {"home": fid, "drift": with_drift, "error": f"inject failed: {r_inj.get('result','')}"}
        # 排除 inject 目标 AND recep_a:防止 agent 落在 recep_a 导致
        # 'go to <recep_a>' 从 admissible 消失,hint 循环静默跳过
        _navigate_neutral(inject_target, recep_a)

    # Task 2: search + put in 第一个可用的 Task2 目标(排除 Task1 目标)
    s1 = _steps()
    drift_t2: list = []
    ok2, desc2 = _search_and_grasp(obj, drift_t2)
    if ok2:
        _reset_to_open_surface()
    ok_p2, recep_b, put_loc2 = _navigate_and_put_any(obj, _T2_CANDS, exclude=recep_a) if ok2 else (False, "", "")
    steps_t2 = _steps() - s1
    if ok2 and ok_p2:
        _set_hint(obj, put_loc2)

    return {
        "home": fid,
        "drift": with_drift,
        "recep_a": recep_a,
        "recep_b": recep_b,
        "inject_target": inject_target if with_drift else None,
        "task1_steps": steps_t1,
        "task2_steps": steps_t2,
        "task1_ok": True,
        "task2_ok": ok2 and ok_p2,
        "drift_detected": bool(drift_t2) if with_drift else None,
        "task2_desc": desc2,
        "error": None,
    }


# ── main ──────────────────────────────────────────────────────────────────────

def _safe_div(a: float, b: float) -> float:
    return a / b if b else float("nan")


def main() -> int:
    global _HOST, _PORT

    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5301)
    ap.add_argument("--homes", type=int, default=10, help="评估的 home 数量(排序后取前 N)")
    ap.add_argument("--obj", default="mug", help="测试物体基名")
    ap.add_argument("--split", default="train")
    ap.add_argument("--out", default=None, help="CSV 输出路径(可选)")
    args = ap.parse_args()

    _HOST = args.host
    _PORT = args.port
    obj = _base(args.obj)

    # 检查后端
    probe = _get("/scene_state")
    if "error" in probe:
        print(f"✗ 后端 :{args.port} 不可达。先起 serve_alfworld/main.py")
        return 2

    # 获取 home 列表
    homes_resp = _get(f"/homes?split={args.split}")
    groups = homes_resp.get("homes", {})
    if not groups:
        print("✗ 没有 home 可用")
        return 2

    all_fids = sorted(groups.keys())
    selected = all_fids[: args.homes]
    total = len(selected)

    print("=" * 76)
    print(f"Phase 3B 漂移恢复率评估  obj={obj}  homes={total}  split={args.split}")
    print("=" * 76)
    print(f"{'home':>6}  {'recepA→B':^14}  {'T1':>4}  {'T2(no)':>6}  {'T2(drf)':>7}  "
          f"{'det':>3}  {'rec':>3}  {'err'}")
    print("-" * 76)

    rows: list[dict] = []

    for i, fid in enumerate(selected, 1):
        # 无漂移
        nd = _eval_trial(fid, obj, args.split, with_drift=False)
        # 有漂移
        wd = _eval_trial(fid, obj, args.split, with_drift=True)

        rows.append({**nd, "mode": "nodrift"})
        rows.append({**wd, "mode": "drift"})

        err_nd = nd.get("error") or ""
        err_wd = wd.get("error") or ""
        recep_ab = f"{nd.get('recep_a','?')}→{nd.get('recep_b','?')}" if not err_nd else "?"
        t1 = nd.get("task1_steps", "-")
        t2_nd = nd.get("task2_steps", "-") if not err_nd else "ERR"
        t2_dr = wd.get("task2_steps", "-") if not err_wd else "ERR"
        det = ("✓" if wd.get("drift_detected") else "✗") if not err_wd else "-"
        rec = ("✓" if wd.get("task2_ok") else "✗") if not err_wd else "-"
        err_str = (err_nd or err_wd or "")[:28]

        print(f"{fid:>6}  {recep_ab:^14}  {t1!s:>4}  {t2_nd!s:>6}  {t2_dr!s:>7}  "
              f"{det:>3}  {rec:>3}  {err_str}")

    # ── 汇总指标 ──────────────────────────────────────────────────────────────
    nd_ok = [r for r in rows if r.get("mode") == "nodrift" and not r.get("error") and r.get("task2_ok")]
    wd_ok = [r for r in rows if r.get("mode") == "drift"   and not r.get("error")]
    wd_success = [r for r in wd_ok if r.get("task2_ok")]
    wd_detect  = [r for r in wd_ok if r.get("drift_detected")]

    avg_t1     = sum(r["task1_steps"] for r in nd_ok) / len(nd_ok) if nd_ok else float("nan")
    avg_t2_nd  = sum(r["task2_steps"] for r in nd_ok) / len(nd_ok) if nd_ok else float("nan")
    avg_t2_dr  = sum(r["task2_steps"] for r in wd_success) / len(wd_success) if wd_success else float("nan")

    memory_speedup     = _safe_div(avg_t2_nd, avg_t1)
    drift_detect_rate  = _safe_div(len(wd_detect), len(wd_ok))
    drift_recover_rate = _safe_div(len(wd_success), len(wd_ok))
    drift_overhead     = _safe_div(avg_t2_dr, avg_t2_nd)

    print("=" * 68)
    print(f"  有效 home 数(无漂移 task2 成功): {len(nd_ok)}/{total}")
    print(f"  有效 home 数(有漂移):             {len(wd_ok)}/{total}")
    print()
    print(f"  avg task1 steps (baseline):    {avg_t1:.1f}")
    print(f"  avg task2 steps (no drift):    {avg_t2_nd:.1f}")
    print(f"  avg task2 steps (with drift):  {avg_t2_dr:.1f}")
    print()
    print(f"  memory_speedup      = {memory_speedup:.3f}   (< 1.0 = 记忆更快)")
    print(f"  drift_detect_rate   = {drift_detect_rate:.1%}  (漂移被正确检测)")
    print(f"  drift_recover_rate  = {drift_recover_rate:.1%}  (漂移后仍完成任务)")
    print(f"  drift_step_overhead = {drift_overhead:.3f}  (> 1.0 = 漂移增加步数)")
    print("=" * 68)

    # ── 可选 CSV ──────────────────────────────────────────────────────────────
    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        fields = ["home", "mode", "recep_a", "recep_b", "inject_target",
                  "task1_steps", "task2_steps", "task1_ok", "task2_ok",
                  "drift_detected", "task2_desc", "error"]
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        print(f"\n  结果已写入: {args.out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
