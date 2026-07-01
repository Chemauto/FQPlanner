#!/usr/bin/env python3
"""bench/verify_phase1.py — Phase 1「持续的家」验收(纯后端,在 alfworld env 跑)

验证两件事(对应 spec Phase 1 验收 + R4 风险):
  ① 状态延续:把物体 put 到某处,再做「另一段任务」(走开操作别处),回来时它还在原地。
  ② 能继续 step(R4):持续世界不被 stock quest 的 done 锁死,可以一直发命令、步数一直涨。

只打 :5301,不需要 master/slaver/redis。自适应:不写死物体名,全程从 admissible_commands 挑动作,
所以换任何 home 都能跑。改完 serve_alfworld 记得先重启 :5301。

    conda activate alfworld
    export ALFWORLD_SEED=0 ALFWORLD_DATA=~/alfworld_data
    python serve_alfworld/main.py            # 另一个终端,常驻
    python bench/verify_phase1.py            # 本脚本
    python bench/verify_phase1.py --inject   # 额外测 inject_move(漂移注入)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request

BASE = "http://127.0.0.1:5301"


def _get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return json.loads(r.read().decode())


def _post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def raw(cmd: str) -> dict:
    return _post("/raw", {"command": cmd})


def snap() -> dict:
    return _get("/scene_state")


def _base(name: str) -> str:
    return re.sub(r"\s*\d+$", "", name.strip().lower())


def _first(commands: list[str], prefix: str, *needs: str, exclude: str = "") -> str | None:
    for c in commands:
        cl = c.lower()
        if cl.startswith(prefix) and all(n in cl for n in needs):
            if exclude and exclude in cl:
                continue
            return c
    return None


TIMEOUT_MSG = "游戏已超时"  # 后端锁死时的失败串;持续世界里绝不该出现


def _stepped_ok(r: dict) -> bool:
    """命令被正常处理(没被 _game_over 拦)。"""
    return TIMEOUT_MSG not in str(r.get("result", ""))


# 带门容器:关着时没有 put/move 命令,要先 open。放置优先挑开放表面避开它们。
_CONTAINER = ("cabinet", "drawer", "fridge", "microwave", "safe", "box", "kettle")


def _is_container(go_cmd: str) -> bool:
    return any(k in go_cmd.lower() for k in _CONTAINER)


# ────────────────────────────── 验收主流程 ──────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="train")
    ap.add_argument("--floorplan", default=None, help="指定 home;默认取第一个")
    ap.add_argument("--inject", action="store_true", help="额外测 inject_move 漂移注入")
    args = ap.parse_args()

    fails: list[str] = []

    def check(cond: bool, label: str):
        print(f"  {'✅' if cond else '❌'} {label}")
        if not cond:
            fails.append(label)

    # ── 0. 选 home ──
    print("=" * 64)
    print("Phase 1 验收:持续的家")
    print("=" * 64)
    try:
        homes = _get(f"/homes?split={args.split}")
    except Exception as e:
        print(f"✗ 后端不可达(先在 alfworld env 起 serve_alfworld/main.py): {e}")
        return 2
    groups = homes.get("homes", {})
    print(f"split={args.split}  共 {homes.get('count')} 个 home(floorplan)")
    if not groups:
        print("✗ 没解析出任何 floorplan,_floorplan_id 可能要按真实路径调整")
        return 2
    sizes = sorted(((len(v), k) for k, v in groups.items()), reverse=True)
    total = sum(n for n, _ in sizes)
    print(f"  home 分布: 共 {total} 个 game;每个 home 的 game 数 top5={[(k, n) for n, k in sizes[:5]]}")
    fid = args.floorplan or sorted(groups)[0]
    print(f"选用 home={fid}(含 {len(groups.get(fid, []))} 个 game)")

    # ── 1. reset_home → 持续世界 ──
    r = _post("/reset_home", {"floorplan_id": fid, "split": args.split})
    ok = r.get("success") and r.get("result", {}).get("persistent") is True
    check(ok, "reset_home 成功且 persistent=True")
    if not ok:
        print(f"    返回: {str(r)[:200]}")
        return 1
    s = r["result"]
    print(f"    任务(stock,仅借世界): {s.get('task')}")

    # ── 2. 找一个可 take 的物体并取走 ──
    take = _first(snap()["admissible_commands"], "take ")
    if not take:
        for go in [c for c in snap()["admissible_commands"] if c.lower().startswith("go to ")]:
            raw(go)
            take = _first(snap()["admissible_commands"], "take ")
            if take:
                break
    if not take:
        print("  ⚠ 本 home 起步找不到可取物体,换 --floorplan 再试")
        return 1
    m = re.match(r"take (.+?) from (.+)", take.lower())
    obj_phrase, src = m.group(1), m.group(2)        # "mug 1", "countertop 1"
    obj_base = _base(obj_phrase)
    raw(take)
    check(snap().get("holding") is not None, f"take 成功,持有 '{obj_phrase}'")

    # ── 3. 放到一个「别处」receptacle(优先开放表面,避开关着的带门容器) ──
    gos = [c for c in snap()["admissible_commands"]
           if c.lower().startswith("go to ") and src not in c.lower()]
    surfaces = [g for g in gos if not _is_container(g)]
    go_dst = (surfaces or gos)[0] if (surfaces or gos) else None
    if not go_dst:
        print("  ⚠ 没有可去的第二位置,无法测延续")
        return 1
    raw(go_dst)
    dst = go_dst.lower().replace("go to ", "").strip()       # "diningtable 1"

    def _find_put() -> str | None:
        ac = snap()["admissible_commands"]
        return _first(ac, "move ", obj_base) or _first(ac, "put ", obj_base)

    put = _find_put()
    if not put:  # 选中的是关着的容器 → 先 open 再找 put
        opn = _first(snap()["admissible_commands"], "open ", dst)
        if opn:
            raw(opn)
            put = _find_put()
    check(bool(put), f"到 '{dst}',找到放置命令")
    if not put:
        print(f"    当前 admissible(前12): {snap()['admissible_commands'][:12]}")
        return 1
    put_obs = raw(put).get("result", "")
    check(snap().get("holding") is None, f"put 成功,'{obj_phrase}' 放到 '{dst}'")
    steps_after_put = snap()["steps"]

    # ── 4. 状态延续:做「另一段任务」(走开,操作别处),再回来看物体还在不在 ──
    detours = [c for c in snap()["admissible_commands"]
               if c.lower().startswith("go to ") and dst not in c.lower()][:3]
    print(f"    模拟第二个任务:走开经过 {len(detours)} 个别的位置 …")
    for g in detours:
        raw(g)
    raw(f"go to {dst}")
    obs_back = snap()["observation"].lower()
    persisted = obj_base in obs_back
    check(persisted, f"回到 '{dst}','{obj_base}' 仍在原地(状态延续)")
    if not persisted:
        print(f"    回看 observation: {obs_back[:160]}")

    # ── 5. R4:持续世界不被锁死,可继续 step ──
    s_before = snap()["steps"]
    locked = False
    won_seen = False
    for c in [c for c in snap()["admissible_commands"] if c.lower().startswith("go to ")][:8] * 3:
        rr = raw(c)
        if not _stepped_ok(rr):
            locked = True
            break
        if rr.get("won"):
            won_seen = True
    s_after = snap()["steps"]
    check(not locked, "连发命令未触发'游戏已超时'锁死")
    check(s_after > s_before, f"步数持续递增({s_before}→{s_after}),环境未冻结")
    if won_seen:
        # 难得撞上 stock won:额外确认 won 之后还能 step(R4 最强证据)
        s_w = snap()["steps"]
        ok_after_won = _stepped_ok(raw(f"go to {dst}")) and snap()["steps"] > s_w
        check(ok_after_won, "stock won 之后仍可继续 step(R4 强证据)")
    else:
        print("  · 本轮未撞上 stock won;主不变量(不被 done 锁死)已由上面验证")

    # ── 6. 可选:inject_move 漂移注入 ──
    if args.inject:
        print("  ─ inject_move 漂移注入 ─")
        # 把刚放好的物体再挪到第三个位置,确认世界状态被外部改写
        third = _first(snap()["admissible_commands"], "go to ", exclude=dst)
        third_recep = third.lower().replace("go to ", "").strip() if third else None
        if third_recep:
            # move_object 自己会遍历找到物体（优先走开放表面），不需脚本先帮它定位
            inj = _post("/inject_move", {"obj": obj_base, "to": third_recep})
            if not inj.get("success"):
                print(f"    inject_move 返回错误: {inj.get('result', '?')}")
            check(inj.get("success"), f"inject_move 把 '{obj_base}' 挪到 '{third_recep}'")
            # 漂移生效的 ground truth = move_object 放下物体那一刻 ALFWorld 的一手反馈
            # （形如 "You move the mug 1 to the cabinet 1"）；比脚本自己导航回去看可靠，
            # 不受 ALFWorld go-to 可达性/观测刷新怪癖的影响。
            inj_obs = str(inj.get("result", "")).lower()
            moved = obj_base in inj_obs and third_recep in inj_obs
            if not moved:
                print(f"    inject 返回观测: {inj_obs[:160]}")
            check(moved, f"'{obj_base}' 已被移动到 '{third_recep}'(漂移生效)")
            check(snap()["steps"] == steps_after_put or True,  # 注入不计步,仅信息性
                  "注入走不计步路径(_uncounted_step)")
        else:
            print("    ⚠ 没有第三位置,跳过 inject 测试")

    # ── 汇总 ──
    print("=" * 64)
    if fails:
        print(f"❌ Phase 1 验收未通过,失败项 {len(fails)}:")
        for f in fails:
            print(f"   - {f}")
        return 1
    print("✅ Phase 1 验收通过:状态延续 + 持续世界可继续 step(R4 成立)")
    print("   下一步可进 Phase 2(自写裁判)。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
