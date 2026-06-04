"""
底盘导航模块 - PID 直线导航
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from serve.service.client import navigate, get_base_status, move_for_duration

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from waypoint_manager import find_waypoint


# ============================================================
# MCP 工具注册
# ============================================================

def register_tools(mcp):

    @mcp.tool()
    async def navigate_to_target(target: str) -> str:
        """导航到目标位置。

        将机器人底盘导航到场景中的指定位置。
        优先使用物体名称（如 "apple"、"counter"），系统会自动找到最佳工作点和朝向。
        仅在没有对应物体名时才传坐标。

        Args:
            target: 物体名称（推荐）或坐标字符串

        Returns:
            包含结果消息和状态更新的 JSON 字符串。

        Examples:
            navigate_to_target(target="apple")
            navigate_to_target(target="counter")
        """
        print(f"[base] 导航请求: '{target}'", file=sys.stderr)

        # 先尝试解析为坐标
        try:
            cleaned = target.strip().strip("()")
            parts = [float(x.strip()) for x in cleaned.split(",")]
            if len(parts) >= 2:
                x, y = parts[0], parts[1]
                yaw_deg = parts[2] if len(parts) > 2 else None
                return await _do_navigate(x, y, yaw_deg)
        except ValueError:
            pass

        # 是物体名称，找最佳工作点
        try:
            wp = find_waypoint(target)
        except Exception as e:
            msg = f"导航失败：无法找到目标 '{target}' 的实时位置或工作点：{e}"
            print(f"[base] {msg}", file=sys.stderr)
            return json.dumps([msg, {"_status": "failure"}])
        return await _do_navigate(wp['x'], wp['y'], wp['yaw_deg'])

    async def _do_navigate(x, y, yaw_deg):
        result = navigate(x, y, target_yaw=yaw_deg)

        if result.get("success"):
            pos = result.get("pos", [0, 0, 0])
            yaw = result.get("yaw", 0)
            response = f"导航成功，当前位置: [{pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}], 朝向: {yaw:.1f}°"
            return json.dumps([response, {
                "_status": "success",
                "coordinates": pos,
            }])
        else:
            msg = result.get("result", f"导航到 ({x:.2f}, {y:.2f}) 失败，请重试。")
            return json.dumps([msg, {"_status": "failure"}])

    @mcp.tool()
    async def move_forward(duration: float = 1.0, speed: float = 0.5) -> str:
        """控制机器人以指定速度持续前进/后退一段时间。

        适用于"往前走2秒"、"后退1秒"等基于时间的运动指令。
        正 speed 为前进，负 speed 为后退。

        Args:
            duration: 持续时间（秒），默认 1.0
            speed:    前进速度 [-1, 1]，正值前进，负值后退，默认 0.5

        Returns:
            包含结果消息和最终位置的 JSON 字符串。

        Examples:
            move_forward(duration=2.0)         # 前进2秒
            move_forward(duration=1.0, speed=-0.3)  # 后退1秒
        """
        print(f"[base] 持续移动请求: speed={speed}, duration={duration}s", file=sys.stderr)
        result = move_for_duration(vx=speed, vw=0.0, duration=duration)

        if result.get("success"):
            pos = result.get("pos", [0, 0, 0])
            yaw = result.get("yaw", 0)
            response = f"移动完成（{duration}秒），当前位置: [{pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}], 朝向: {yaw:.1f}°"
            return json.dumps([response, {
                "_status": "success",
                "coordinates": pos,
            }])
        else:
            msg = result.get("result", "移动失败，请重试。")
            return json.dumps([msg, {"_status": "failure"}])

    @mcp.tool()
    async def rotate(duration: float = 1.0, speed: float = 0.5) -> str:
        """控制机器人原地旋转一段时间。

        适用于"左转2秒"、"右转1秒"等基于时间的旋转指令。
        正 speed 为左转（逆时针），负 speed 为右转（顺时针）。

        Args:
            duration: 持续时间（秒），默认 1.0
            speed:    旋转速度 [-1, 1]，正值左转，负值右转，默认 0.5

        Returns:
            包含结果消息和最终朝向的 JSON 字符串。

        Examples:
            rotate(duration=2.0)          # 左转2秒
            rotate(duration=1.0, speed=-0.5)  # 右转1秒
        """
        print(f"[base] 旋转请求: speed={speed}, duration={duration}s", file=sys.stderr)
        result = move_for_duration(vx=0.0, vw=speed, duration=duration)

        if result.get("success"):
            pos = result.get("pos", [0, 0, 0])
            yaw = result.get("yaw", 0)
            response = f"旋转完成（{duration}秒），当前朝向: {yaw:.1f}°，位置: [{pos[0]:.2f}, {pos[1]:.2f}]"
            return json.dumps([response, {
                "_status": "success",
                "yaw": yaw,
            }])
        else:
            msg = result.get("result", "旋转失败，请重试。")
            return json.dumps([msg, {"_status": "failure"}])

    print("[base.py] 底盘控制模块已注册 (PID 直线导航 + 持续运动)", file=sys.stderr)
