"""
底盘导航模块 - 导航到工作点而非精确坐标
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from serve.sim import navigate, get_base_status, get_scene

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from waypoint_manager import find_waypoint


def register_tools(mcp):

    @mcp.tool()
    async def navigate_to_target(target: str) -> str:
        """导航到目标位置。

        将机器人底盘导航到场景中的指定位置。
        支持坐标格式："(x, y)" 或 "x, y"
        也支持物体名称："apple"、"counter" 等，会自动查找最近工作点。

        Args:
            target: 导航目标，可以是物体名称或坐标字符串

        Returns:
            包含结果消息和状态更新的 JSON 字符串。

        Examples:
            navigate_to_target(target="(1.5, -0.5)")
            navigate_to_target(target="apple")
        """
        print(f"[base] 导航请求: '{target}'", file=sys.stderr)

        # 先尝试解析为坐标
        try:
            cleaned = target.strip().strip("()")
            parts = [float(x.strip()) for x in cleaned.split(",")]
            if len(parts) >= 2:
                # 是坐标，直接导航（不走工作点）
                x, y = parts[0], parts[1]
                w = parts[2] if len(parts) > 2 else 0
                return await _do_navigate(x, y, w, target)
        except ValueError:
            pass  # 不是坐标，走工作点逻辑

        # 是物体/家具名称，找最近工作点
        waypoint = find_waypoint(target)
        wp_name = waypoint['name']
        wp_pos = waypoint['pos']
        print(f"[base] 目标工作点: {wp_name} @ {wp_pos}", file=sys.stderr)
        return await _do_navigate(wp_pos[0], wp_pos[1], 0, target)

    async def _do_navigate(x, y, w, target):
        result = navigate(x, y, w)

        if result.get("success"):
            pos = result.get("pos", [0, 0, 0])
            yaw = result.get("yaw", 0)
            response = f"导航成功，当前位置: [{pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}], 朝向: {yaw:.1f}°"
            print(f"[base] ✓ {response}", file=sys.stderr)
            return response
        else:
            msg = result.get("result", f"导航到 {target} 失败，请重试。")
            print(f"[base] ✗ {msg}", file=sys.stderr)
            return msg

    print("[base.py] 底盘控制模块已注册 (RoboCasa)", file=sys.stderr)