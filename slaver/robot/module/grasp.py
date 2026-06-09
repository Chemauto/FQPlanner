"""
抓取控制模块 - XLeRobot MuJoCo 仿真
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from serve.service.client import grasp_object as _grasp_object

try:
    from serve_real.Arm.arm_bridge import trigger_real_grasp, real_arm_fail_on_error
except Exception as e:
    print(f"[grasp] real_arm bridge 未启用: {e}", file=sys.stderr)

    def trigger_real_grasp(obj_name=None):
        return {"enabled": False, "sent": False, "success": None}

    def real_arm_fail_on_error():
        return False


def _append_real_grasp_result(response: str, state: dict, target: str):
    real_result = trigger_real_grasp(target)
    if not real_result.get("enabled"):
        print("[grasp] real_arm 未启用，跳过真实抓取信号", file=sys.stderr)
        return response, state

    state["real_arm"] = real_result
    if real_result.get("success"):
        return f"{response}；真实抓取成功", state

    error = real_result.get("error") or real_result.get("response") or "真实抓取失败"
    state["_status"] = "failure" if real_arm_fail_on_error() else "success"
    return f"{response}；真实抓取失败: {error}", state


def register_tools(mcp):

    @mcp.tool()
    async def grasp_object(object_name: str = None) -> str:
        """抓取物体。

        机器人抓取指定物体。仅当机器人当前没有抓取任何物体时使用。
        如果已经抓取了物体，需要先使用 release_object 释放。

        Args:
            object_name: 要抓取的物体名称（如 "mug"、"apple"）。一次只能抓取一个物体。

        Returns:
            抓取结果，成功或失败信息。
        """
        target = object_name or "unknown_object"
        print(f"[grasp] 开始抓取 '{target}'...", file=sys.stderr)

        result = _grasp_object(target)

        if result.get("success"):
            response = result.get("result", f"成功抓取 {target}")
            state = {"_status": "success"}
            response, state = _append_real_grasp_result(response, state, target)
            if state.get("_status") == "success":
                print(f"[grasp] ✓ {response}", file=sys.stderr)
            else:
                print(f"[grasp] ✗ {response}", file=sys.stderr)
            return json.dumps([response, state], ensure_ascii=False)
        else:
            msg = result.get("result", f"抓取 {target} 失败，请重试。")
            print(f"[grasp] ✗ {msg}", file=sys.stderr)
            return json.dumps([msg, {"_status": "failure"}], ensure_ascii=False)

    print("[grasp.py] 抓取控制模块已注册 (XLeRobot MuJoCo)", file=sys.stderr)
