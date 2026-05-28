"""
底盘导航模块 - 导航到工作点而非精确坐标
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from serve.sim import navigate, get_base_status

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from waypoint_manager import find_waypoint


def register_tools(mcp):

    @mcp.tool()
    async def navigate_to_target(target: str) -> str:
        """导航到目标位置。

        将机器人底盘导航到场景中的指定位置。
        支持坐标格式："(x, y)" 或 "x, y"
        也支持物体名称："apple"、"counter" 等

        Args:
            target: 导航目标，可以是物体名称或坐标字符串

        Returns:
            包含结果消息和状态更新的 JSON 字符串。
        """
        print(f"[base] 导航请求: '{target}'", file=sys.stderr)

        # 找到最近工作点
        waypoint = find_waypoint(target)
        wp_name = waypoint['name']
        wp_pos = waypoint['pos']

        print(f"[base] 目标工作点: {wp_name} @ {wp_pos}", file=sys.stderr)

        result = _navigate(wp_pos[0], wp_pos[1])

        if result.get('success'):
            response = f"导航成功，到达工作点 [{wp_name}]，位置: {wp_pos}"
            print(f"[base] ✓ {response}", file=sys.stderr)
            return response
        else:
            msg = result.get('result', f"导航到工作点 {wp_name} 失败，请重试。")
            print(f"[base] ✗ {msg}", file=sys.stderr)
            return msg

    print("[base.py] 底盘控制模块已注册 (RoboCasa)", file=sys.stderr)