"""
底盘控制模块 - OmniGibson 真实仿真

替换原版 /home/fangqi/WorkXCJ/FQPlanner/slaver/robot/module/base.py
"""

import json
import sys

from .omnigibson_client import call_omnigibson


def register_tools(mcp):

    @mcp.tool()
    async def navigate_to_target(target: str) -> str:
        """导航到目标位置。

        将机器人底盘导航到场景中的指定位置，目标位置需匹配场景配置中的预定义位置。
        支持中英文位置名称，支持物体名称（自动导航到物体附近）。

        Args:
            target: 导航目标位置或物体名称，支持中英文（如 "breakfast_table"、"早餐桌"、"laptop"、"笔记本电脑"）。

        Returns:
            包含结果消息和状态更新的 JSON 字符串。

        Examples:
            navigate_to_target(target="breakfast_table")
            navigate_to_target(target="早餐桌")
        """
        print(f"[base] 导航到 '{target}'...", file=sys.stderr)

        result = call_omnigibson("/action/navigate", {"target_name": target})

        if result.get("success"):
            response = result.get("result")
            print(f"[base] ✓ {response}", file=sys.stderr)
            return response
        else:
            msg = result.get("result", f"导航到 {target} 失败，请重试。")
            print(f"[base] ✗ {msg}", file=sys.stderr)
            return msg

    print("[base.py] 底盘控制模块已注册 (OmniGibson)", file=sys.stderr)
