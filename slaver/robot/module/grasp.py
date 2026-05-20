"""
抓取控制模块 - OmniGibson 真实仿真

替换原版 /home/fangqi/WorkXCJ/FQPlanner/slaver/robot/module/grasp.py
"""

import json
import sys

# 将 omnigibson_client.py 复制到同目录后使用:
from .omnigibson_client import call_omnigibson


def register_tools(mcp):

    @mcp.tool()
    async def grasp_object(object_name: str = None) -> str:
        """抓取物体。

        机器人抓取指定物体。仅当机器人当前没有抓取任何物体时使用。
        如果已经抓取了物体，需要先使用 release_object 释放，或使用 place_on_top/place_inside 放置。

        Args:
            object_name: 要抓取的物体名称，支持中英文（如 "laptop"、"笔记本电脑"、"apple"、"苹果"）。一次只能抓取一个物体。

        Returns:
            抓取结果，成功或失败信息。
        """
        target = object_name or "unknown_object"
        print(f"[grasp] 开始抓取 '{target}'...", file=sys.stderr)

        result = call_omnigibson("/action/grasp", {"object_name": target})

        if result.get("success"):
            response = result.get("result")
            # result 已经是 JSON 字符串格式 ["消息", {状态}]
            print(f"[grasp] ✓ {response}", file=sys.stderr)
            return response
        else:
            msg = result.get("result", f"抓取 {target} 失败，请重试。")
            print(f"[grasp] ✗ {msg}", file=sys.stderr)
            return msg

    print("[grasp.py] 抓取控制模块已注册 (OmniGibson)", file=sys.stderr)
