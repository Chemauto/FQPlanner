#!/usr/bin/env python3
"""bench/run_home.py — Phase 3 全链路测试 driver

在持续世界里连续执行两个任务,中间可注入漂移,验证:
  ① ShadowState 跨任务位置信念持续(同 home 内 at/is_open 不重置)
  ② 位置记忆命中后 take 失败 → 检测漂移、清除过期记忆、全量重搜
  ③ 全链路跑通:scripted agent 在 persistent world 里连做多个任务

只需 alfworld server 在 :5301,不需要 master/slaver/redis。

用法:
    # 先在 alfworld env 起后端
    conda activate alfworld
    python serve_alfworld/main.py

    # 另一个终端
    python bench/run_home.py                     # 不注入漂移
    python bench/run_home.py --drift             # Task1→Task2 之间注入漂移
    python bench/run_home.py --floorplan 2 --drift
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from typing import Optional

# ── 路径 ──────────────────────────────────────────────────────────────────────
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOCATION_MEMORY_FILE = os.path.join(_REPO_ROOT, "master", "memory", "location_memory.json")

# ── 全局配置(由 argparse 覆盖) ────────────────────────────────────────────────
_HOST = "127.0.0.1"
_PORT = 5301


# ── HTTP 工具 ──────────────────────────────────────────────────────────────────

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


def _shadow() -> dict:
    return _get("/shadow_state")


def _steps() -> int:
    return _get("/success").get("steps", -1)


# ── location_memory 工具(运行在 bench 层,直接读写文件) ─────────────────────────

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
    print(f"    [location_memory] {obj_base} → {location}")


def _clear_hint(obj_base: str) -> None:
    mem = _read_mem()
    if obj_base in mem:
        old = mem[obj_base].get("location", "?")
        del mem[obj_base]
        _write_mem(mem)
        print(f"    [drift] ⚠ 漂移检测! 清除 '{obj_base}' 的过期记忆 (was: {old})")


# ── scripted agent ─────────────────────────────────────────────────────────────

# 容器关键字:关着时没有 put/move,且 go-to 后可达性缩减 → 排到遍历末尾
_CONTAINERS = ("cabinet", "drawer", "fridge", "microwave", "safe", "box")


def _find_take(obj_base: str, admissible: list[str], exclude_from: str = "") -> Optional[str]:
    excl = _norm(exclude_from)
    for cmd in admissible:
        c = _norm(cmd)
        if c.startswith("take ") and obj_base in c:
            if excl and f" from {excl}" in c:
                continue
            return cmd
    return None


def _find_put(obj_base: str, recep_base: str, admissible: list[str]) -> Optional[str]:
    for cmd in admissible:
        c = _norm(cmd)
        if (c.startswith("put ") or c.startswith("move ")) and obj_base in c and recep_base in c:
            return cmd
    return None


def _loc_from_take(take_cmd: str) -> str:
    """'take mug 1 from shelf 1' → 'shelf 1'"""
    m = re.search(r" from (.+)$", _norm(take_cmd))
    return m.group(1).strip() if m else ""


def _loc_from_put(put_cmd: str) -> str:
    """'move mug 1 to shelf 1' or 'put mug 1 in shelf 1' → 'shelf 1'"""
    m = re.search(r" (?:in(?:to)?|on(?:to)?|to) (.+)$", _norm(put_cmd))
    return m.group(1).strip() if m else ""


def _search_and_grasp(obj_base: str, drift_log: list) -> tuple[bool, str]:
    """Scripted search-and-grasp with location memory + drift detection.

    drift_log: mutable list; appends True if drift was detected (hint miss).
    Returns (success, description).
    """
    # 当前位置先试
    adm = _admissible()
    take = _find_take(obj_base, adm)
    if take:
        r = _post("/raw", {"command": take})
        if r.get("success"):
            return True, f"当前位置即可取 ({_loc_from_take(take)})"

    all_gos = [c for c in _admissible() if _norm(c).startswith("go to ")]
    surfaces = [g for g in all_gos if not any(k in g.lower() for k in _CONTAINERS)]
    containers = [g for g in all_gos if any(k in g.lower() for k in _CONTAINERS)]

    # ── 位置记忆优先 ──────────────────────────────────────────────────────────
    hint = _get_hint(obj_base)
    if hint:
        h_norm = _norm(hint)
        for go in all_gos:
            if h_norm in _norm(go):
                print(f"    [search] 位置记忆: {obj_base} → {hint}，优先尝试")
                _post("/raw", {"command": go})
                take = _find_take(obj_base, _admissible())
                if take:
                    r = _post("/raw", {"command": take})
                    if r.get("success"):
                        return True, f"位置记忆命中 ({hint})"
                # 位置记忆未命中 → 漂移检测
                _clear_hint(obj_base)
                drift_log.append(True)
                print(f"    [search] 位置记忆未命中，已清除，开始全量遍历")
                break

    # ── 第一遍:开放表面优先 ──────────────────────────────────────────────────
    all_gos = [c for c in _admissible() if _norm(c).startswith("go to ")]
    surfaces = [g for g in all_gos if not any(k in g.lower() for k in _CONTAINERS)]
    containers = [g for g in all_gos if any(k in g.lower() for k in _CONTAINERS)]

    for go in surfaces + containers:
        _post("/raw", {"command": go})
        take = _find_take(obj_base, _admissible())
        if take:
            r = _post("/raw", {"command": take})
            if r.get("success"):
                found_at = _loc_from_take(take)
                return True, f"第一遍遍历找到 ({found_at})"

    # ── 第二遍:开容器 ────────────────────────────────────────────────────────
    all_gos = [c for c in _admissible() if _norm(c).startswith("go to ")]
    containers = [g for g in all_gos if any(k in g.lower() for k in _CONTAINERS)]
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
                    found_at = _loc_from_take(take)
                    return True, f"第二遍(开容器)找到 ({found_at})"

    return False, f"全量遍历未找到 '{obj_base}'"


def _navigate_and_put(obj_base: str, recep_base: str) -> tuple[bool, str, str]:
    """导航到目标容器并放下持有物。返回 (success, cmd_used, specific_loc)。"""
    all_gos = [c for c in _admissible() if _norm(c).startswith("go to ")]
    target_gos = [g for g in all_gos if recep_base in _norm(g)]

    for go in target_gos:
        _post("/raw", {"command": go})
        adm = _admissible()
        put = _find_put(obj_base, recep_base, adm)
        if put:
            r = _post("/raw", {"command": put})
            if r.get("success"):
                specific_loc = _loc_from_put(put)
                return True, put, specific_loc

    return False, f"put {obj_base} → {recep_base} 失败", ""


# ── 报告工具 ──────────────────────────────────────────────────────────────────

_fails: list[str] = []


def check(ok: bool, label: str) -> None:
    tag = "✓" if ok else "✗"
    print(f"  [{tag}] {label}")
    if not ok:
        _fails.append(label)


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    global _HOST, _PORT, _fails
    _fails = []

    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5301)
    ap.add_argument("--floorplan", default=None, help="floorplan_id;默认取第一个可用")
    ap.add_argument("--split", default="train")
    ap.add_argument("--drift", action="store_true", help="Task1→Task2 之间注入漂移")
    ap.add_argument("--obj", default="mug", help="测试用物体基名(默认 mug)")
    args = ap.parse_args()

    _HOST = args.host
    _PORT = args.port
    obj = _base(args.obj)

    print("=" * 64)
    print(f"Phase 3 全链路测试  obj={obj}  drift={'ON' if args.drift else 'OFF'}")
    print("=" * 64)

    # ── Step 0: 检查后端 ──────────────────────────────────────────────────────
    probe = _get("/scene_state")
    if "error" in probe:
        print(f"✗ 后端 :5301 不可达。先在 alfworld env 里启动:")
        print(f"    conda activate alfworld && python serve_alfworld/main.py")
        return 2

    # ── Step 1: 选 home 并 reset_home ─────────────────────────────────────────
    print(f"\n[Step 1] 选 home 并 POST /reset_home")
    homes = _get(f"/homes?split={args.split}")
    groups = homes.get("homes", {})
    if not groups:
        print("✗ 没有解析出 floorplan")
        return 2

    fid = args.floorplan or sorted(groups)[0]
    if fid not in groups:
        print(f"✗ floorplan '{fid}' 不存在;可用: {sorted(groups)[:10]}")
        return 2

    r = _post("/reset_home", {"floorplan_id": fid, "split": args.split})
    check(r.get("success") and r.get("result", {}).get("persistent") is True,
          f"reset_home floorplan={fid}, persistent=True")
    if _fails:
        print(f"  返回: {str(r)[:200]}")
        return 1

    snap = r["result"]
    print(f"  stock task: {snap.get('task', '?')}")
    steps_home = _steps()

    # ── Step 2: 清位置记忆(避免上次运行的残留干扰) ────────────────────────────
    print(f"\n[Step 2] 清除 '{obj}' 的旧位置记忆(保证本轮从零开始)")
    _clear_hint(obj)          # 若有就删,没有也没关系
    mem_before = _read_mem()
    check(obj not in mem_before, f"'{obj}' 的位置记忆已清除")

    # ── Step 3: Task 1 — search + put in shelf ──────────────────────────────
    task1_label = f"put {obj} in shelf"
    print(f"\n[Step 3] Task 1: {task1_label}")
    shadow_pre = _shadow()
    print(f"  shadow.at['{obj} 1'] 前 = {shadow_pre.get('at', {}).get(obj + ' 1', 'N/A')}")
    steps_t1_start = _steps()

    drift_t1: list = []
    ok_grasp, grasp_desc = _search_and_grasp(obj, drift_t1)
    check(ok_grasp, f"Task 1 search_and_grasp: {grasp_desc}")
    if not ok_grasp:
        print(f"  ✗ 找不到物体 '{obj}'，换 --obj 或 --floorplan 重试")
        return 1

    ok_put, put_cmd, put_loc = _navigate_and_put(obj, "shelf")
    check(ok_put, f"Task 1 put {obj} in shelf → {put_loc}")
    if not ok_put:
        print(f"  提示: shelf 可能不在这个 home,换 --obj 再试")
        return 1

    steps_t1 = _steps() - steps_t1_start
    # 写位置记忆:记录任务完成时物体的位置(shelf X)
    _set_hint(obj, put_loc)

    shadow_t1 = _shadow()
    mem_t1 = _read_mem()
    print(f"  shadow.at['{obj} 1'] 后 = {shadow_t1.get('at', {}).get(obj + ' 1', '?')}")
    print(f"  location_memory: {mem_t1.get(obj, {})}")
    print(f"  Task 1 steps: {steps_t1}")

    check("location_memory" and obj in mem_t1, f"location_memory 已写入 '{obj}' → '{put_loc}'")
    check(not drift_t1, "Task 1 无漂移(首次搜索应全量遍历,不触发漂移)")

    # ── Step 4: ShadowState 跨任务持续性验证 ──────────────────────────────────
    print(f"\n[Step 4] 验证 ShadowState 跨任务持续(不重置)")
    shadow_check = _shadow()
    mug_in_shadow = shadow_check.get("at", {}).get(obj + " 1")
    check(mug_in_shadow is not None,
          f"shadow.at['{obj} 1'] 跨任务仍存在 = '{mug_in_shadow}'")

    # ── Step 5(可选): inject_move 模拟漂移 ───────────────────────────────────
    drift_receptacle = "cabinet"   # move_object 用 base name,自动选第一个匹配实例
    if args.drift:
        print(f"\n[Step 5] POST /inject_move  {obj} → {drift_receptacle}")
        r_inj = _post("/inject_move", {"obj": obj, "to": drift_receptacle})
        check(r_inj.get("success"), f"inject_move {obj} → {drift_receptacle}: {r_inj.get('result','')[:80]}")
        shadow_inj = _shadow()
        print(f"  shadow.at['{obj} 1'] after inject = {shadow_inj.get('at', {}).get(obj + ' 1', '?')}")
        print(f"  location_memory(未变): {_read_mem().get(obj, {})}")

        # inject_move 的 _uncounted_step 把 agent 留在 cabinet（cabinet 是开着的,
        # 物体当场可取）。Task 2 必须先走到「记忆中的 shelf」踩 miss 才能触发漂移检测,
        # 所以这里先把 agent 导航到一个不含目标物的开放表面当中性起点。
        _NEUTRAL = ("countertop", "sinkbasin", "stoveburner")
        all_gos = [c for c in _admissible() if _norm(c).startswith("go to ")]
        neutral = next(
            (g for g in all_gos
             if any(k in _norm(g) for k in _NEUTRAL) and drift_receptacle not in _norm(g)),
            None,
        )
        if neutral:
            r_nav = _post("/raw", {"command": neutral})
            print(f"  [复位中性位置] {neutral}: {_norm(r_nav.get('result', ''))[:60]}")
        else:
            print("  [warning] 没找到中性导航目标,漂移检测可能短路")
    else:
        print(f"\n[Step 5] 跳过 inject_move (加 --drift 开启)")

    # ── Step 6: Task 2 — search + put in countertop ───────────────────────────
    task2_label = f"put {obj} in countertop"
    print(f"\n[Step 6] Task 2: {task2_label}")
    steps_t2_start = _steps()

    drift_t2: list = []
    ok_grasp2, grasp_desc2 = _search_and_grasp(obj, drift_t2)
    check(ok_grasp2, f"Task 2 search_and_grasp: {grasp_desc2}")
    if not ok_grasp2:
        print(f"  ✗ Task 2 找不到物体")
        return 1

    ok_put2, put_cmd2, put_loc2 = _navigate_and_put(obj, "countertop")
    check(ok_put2, f"Task 2 put {obj} in countertop → {put_loc2}")

    steps_t2 = _steps() - steps_t2_start
    if ok_put2:
        _set_hint(obj, put_loc2)   # 更新记忆到最新位置

    shadow_t2 = _shadow()
    mem_t2 = _read_mem()
    print(f"  shadow.at['{obj} 1'] 后 = {shadow_t2.get('at', {}).get(obj + ' 1', '?')}")
    print(f"  location_memory: {mem_t2.get(obj, {})}")
    print(f"  Task 2 steps: {steps_t2}")

    if args.drift:
        check(bool(drift_t2),
              "Task 2 触发漂移检测(记忆指向 shelf,实际不在,重搜找到)")
        check(obj in mem_t2 and mem_t2[obj].get("location") != put_loc,
              f"漂移后 location_memory 更新(旧={put_loc}, 新={mem_t2.get(obj, {}).get('location','?')})")
    else:
        # 无漂移:位置记忆命中(mug 仍在 shelf),直接命中不触发漂移检测
        check(not drift_t2,
              "无漂移注入时位置记忆命中(或全量找到),未触发漂移清除")

    # ── 汇总 ──────────────────────────────────────────────────────────────────
    total_steps = _steps() - steps_home
    print(f"\n{'=' * 64}")
    if _fails:
        print(f"✗ Phase 3 未通过,失败项 {len(_fails)}:")
        for f in _fails:
            print(f"   - {f}")
        return 1

    print("✓ Phase 3 全部通过")
    print(f"  总 steps: {total_steps}  (Task1={steps_t1}, Task2={steps_t2})")
    if args.drift:
        print(f"  漂移检测: 触发 {len(drift_t2)} 次 ✓")
        print(f"  ShadowState: 跨任务持续 ✓  inject 后记忆失效再重建 ✓")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
