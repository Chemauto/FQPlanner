"""
底盘导航模块 - 导航到工作点而非精确坐标
"""

import os
import sys
import math

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
                x, y = parts[0], parts[1]
                w = parts[2] if len(parts) > 2 else 0
                return await _do_navigate(x, y, w, target)
        except ValueError:
            pass

        # 是物体名称，找最佳工作点
        wp = find_waypoint(target)
        return await _do_navigate(wp['x'], wp['y'], wp['yaw_deg'], target)

# _do_navigate 里，yaw 已经是度了
    async def _do_navigate(x, y, yaw_deg, target):
        result = navigate(x, y, w=yaw_deg)
        if result.get("success"):
            pos = result.get("pos", [0, 0, 0])
            yaw = result.get("yaw", 0)
            response = f"导航成功，当前位置: [{pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}], 朝向: {yaw:.1f}°"
            # 把状态更新打包成 JSON tuple，让 slaver_agent 捡到
            import json
            return json.dumps([response, {
                "position": target,
                "coordinates": pos,
            }])
        else:
            msg = result.get("result", f"导航到 {target} 失败，请重试。")
            return msg

    print("[base.py] 底盘控制模块已注册 (RoboCasa)", file=sys.stderr)