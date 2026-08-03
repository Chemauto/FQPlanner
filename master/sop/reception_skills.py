"""技能层 + 观测层 —— 大脑与外部执行/观测的接口抽象(八月接待 demo;呼应桌面 skill_executor.py)。

大脑只发【语义指令】(开灯/扫描/取可乐/走到会议室/摆放/播报),不给坐标;verify 只信【重新观测】。
整体两个 backend(拿到真机端口零改大脑决策逻辑):
  - mock:      调进程内 reception_world(验证大脑逻辑,可注入 fault)。
  - robot_api: 调 robot_api.client —— 你的统一执行/观测【总闸】。真正接哪个后端(sim_atomic 仿真
               抓取 / robocasa / dream 导航 / VLA 组真机)由 robot_api/config.yaml 决定。
               → "接入 VLA" = 切 robot_api 后端 + 填 url,**这里和大脑都不用改**。

切 backend:环境变量 RECEPTION_BACKEND=robot_api,或 reception_loop.py --backend robot_api。
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# mock 世界(仅 mock backend 用)
from reception_world import (w_set_light, w_pick_cola, w_walk, w_place_cola,   # noqa: E402
                             w_count_cola, w_chairs_blocking, w_light_state,
                             w_robot_holding, w_robot_at, w_last_slot, w_all_slots)

COLA = "可乐"
BACKEND = os.environ.get("RECEPTION_BACKEND", "mock")

# 语义地名 → robot_api 区域名(与标准图/waypoint 对齐;见对接手册-导航建图组 / fqplanner-external-integration)
REGION = {"茶水间": "tea_room", "会议室": "meeting_room"}


def set_backend(name):
    global BACKEND
    BACKEND = name


def _api():
    """延迟 import robot_api.client(mock 模式不触碰,避免起服务依赖)。"""
    _ROOT = os.path.dirname(os.path.dirname(_HERE))
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)
    from robot_api import client as api
    return api


def _is_cola(name, v):
    s = (str(name) + str(v.get("category", ""))).lower()
    return "可乐" in (str(name) + str(v.get("category", ""))) or "cola" in s or "coke" in s


# ============ 技能(大脑发语义指令) ============

def turn_on_lights(room):
    if BACKEND == "mock":
        return {"success": w_set_light(room, True), "room": room}
    # robot_api:灯控归 IoT/触发组,robot_api 无此接口 → TODO 接灯控服务;暂当已开
    return {"success": True, "room": room, "note": "TODO 接灯控/IoT"}


def scan(room):
    if BACKEND == "mock":
        return {"success": True, "cola": w_count_cola(room),
                "chairs_blocking": w_chairs_blocking(room)}
    # robot_api:观测(VLA 看图 / 世界模型场景图)—— 数该房间可乐 + 障碍
    return {"success": True, "cola": obs_count_cola(room),
            "chairs_blocking": False, "note": "TODO 办公椅检测接场景图"}


def pick(target=COLA, at="茶水间"):
    """取物。mock:world;robot_api:VLA /grasp(给语义物体名,坐标 VLA 看图;对齐 VLA_ACT)。"""
    if BACKEND == "mock":
        ok = w_pick_cola(at)
        return {"success": True} if ok else {
            "success": False, "fail_stage": "grasp", "fail_reason": f"没抓到{target}"}
    r = _api().grasp_object(target) or {}
    if r.get("success"):
        return {"success": True}
    return {"success": False, "fail_stage": "grasp", "fail_reason": r.get("result")}


def walk(to="会议室"):
    """行走。mock:world;robot_api:导航组 /nav(给语义地名;地名→坐标由 waypoint/导航组解析)。"""
    if BACKEND == "mock":
        ok = w_walk(to)
        return {"success": True, "at": to} if ok else {
            "success": False, "fail_reason": "办公椅挡路,过不去"}
    r = _api().navigate_to(REGION.get(to, to)) or {}
    if r.get("success", True):
        return {"success": True, "at": to}
    return {"success": False, "fail_reason": r.get("result")}


def place(target=COLA, to="会议室"):
    """摆放。mock:world;robot_api:VLA /place(给语义目标区;最简版放桌面,不给精确位姿)。"""
    if BACKEND == "mock":
        return {"success": w_place_cola(to)}
    r = _api().place_object(target, REGION.get(to, to)) or {}
    if r.get("success"):
        return {"success": True}
    return {"success": False, "fail_reason": r.get("result")}


def speak(text):
    print(f"    🔊 [语音播报] {text}")
    return {"success": True}   # robot_api 模式 TODO 接 TTS 服务


# ============ 观测层(大脑 verify 用;永远重新观测,不采信技能自报) ============

def obs_light_on(room):
    if BACKEND == "mock":
        return w_light_state(room) == "on"
    return True   # TODO robot_api 接灯控状态回读


def obs_holding():
    """手上有没有可乐(= empty-grasp 检测)。"""
    if BACKEND == "mock":
        return w_robot_holding()
    # robot_api:is_object_grasped —— 直接对应论文 empty-grasp failure model,现成可用
    return COLA if _api().is_object_grasped(COLA) else None


def obs_robot_at():
    """机器人在哪个房间。"""
    if BACKEND == "mock":
        return w_robot_at()
    # robot_api:/base_status 拿位姿 → 最近区域名。TODO 需区域锚点坐标表做映射;
    # 未接前返回 None,verify 降级为暂信导航自报(见 reception_loop._v_walk)。
    # bs = _api().get_base_status(); return _nearest_region(bs["pos"])
    return None


def obs_count_cola(room):
    """room 里的可乐数(用于缺口/放置确认)。"""
    if BACKEND == "mock":
        return w_count_cola(room)
    # robot_api:get_objects 数可乐。TODO 按 room 区域过滤(现数全局,单房间够用);
    # 真机更稳的做法 = capture_image + vlm_judge 拍照数会议室桌面可乐。
    objs = _api().get_objects() or {}
    return sum(1 for k, v in objs.items() if _is_cola(k, v))


def obs_last_slot(room):
    """最近摆放槽位(间隔/朝向);最简版不查姿态。"""
    if BACKEND == "mock":
        return w_last_slot(room)
    return None   # TODO robot_api 姿态复核靠 capture_image + vlm_judge


def obs_all_slots(room):
    """所有已摆放槽位(终局全局摆放复核)。"""
    if BACKEND == "mock":
        return w_all_slots(room)
    return []     # TODO robot_api 靠 vlm_judge 逐罐复核
