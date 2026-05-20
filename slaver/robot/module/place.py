"""
放置/开关控制模块 - OmniGibson 真实仿真

新增模块，复制到 /home/fangqi/WorkXCJ/FQPlanner/slaver/robot/module/place.py
"""

import json
import sys

from .omnigibson_client import call_omnigibson


def register_tools(mcp):

    @mcp.tool()
    async def place_on_top(target_name: str) -> str:
        """将抓取的物体放在目标物体上面。仅当机器人当前抓取了物体时使用。

        Args:
            target_name: 目标物体名称，支持中英文（如 "breakfast_table"、"桌子"、"碗"、"bowl"）。

        Returns:
            放置结果，成功或失败信息。
        """
        print(f"[place] 放在 '{target_name}' 上面...", file=sys.stderr)
        result = call_omnigibson("/action/place_on_top", {"target_name": target_name})

        if result.get("success"):
            response = result.get("result")
            print(f"[place] ✓ {response}", file=sys.stderr)
            return response
        else:
            msg = result.get("result", f"放置在 {target_name} 上面失败，请重试。")
            print(f"[place] ✗ {msg}", file=sys.stderr)
            return msg

    @mcp.tool()
    async def place_inside(target_name: str) -> str:
        """将抓取的物体放入目标物体内部。仅当机器人当前抓取了物体时使用。

        Args:
            target_name: 目标容器名称（如 "垃圾桶"、"篮子"）。

        Returns:
            放置结果，成功或失败信息。
        """
        print(f"[place] 放入 '{target_name}' 内部...", file=sys.stderr)
        result = call_omnigibson("/action/place_inside", {"target_name": target_name})

        if result.get("success"):
            response = result.get("result")
            print(f"[place] ✓ {response}", file=sys.stderr)
            return response
        else:
            msg = result.get("result", f"放入 {target_name} 内部失败，请重试。")
            print(f"[place] ✗ {msg}", file=sys.stderr)
            return msg

    @mcp.tool()
    async def open_object(target_name: str) -> str:
        """打开物体（如门、柜子、冰箱等）。

        Args:
            target_name: 要打开的物体名称。

        Returns:
            操作结果。
        """
        print(f"[place] 打开 '{target_name}'...", file=sys.stderr)
        result = call_omnigibson("/action/open", {"target_name": target_name})

        if result.get("success"):
            response = result.get("result", f"成功打开了 {target_name}")
            print(f"[place] ✓ {response}", file=sys.stderr)
            return response
        else:
            msg = result.get("result", f"打开 {target_name} 失败，请重试。")
            print(f"[place] ✗ {msg}", file=sys.stderr)
            return msg

    @mcp.tool()
    async def close_object(target_name: str) -> str:
        """关闭物体（如门、柜子、冰箱等）。

        Args:
            target_name: 要关闭的物体名称。

        Returns:
            操作结果。
        """
        print(f"[place] 关闭 '{target_name}'...", file=sys.stderr)
        result = call_omnigibson("/action/close", {"target_name": target_name})

        if result.get("success"):
            response = result.get("result", f"成功关闭了 {target_name}")
            print(f"[place] ✓ {response}", file=sys.stderr)
            return response
        else:
            msg = result.get("result", f"关闭 {target_name} 失败，请重试。")
            print(f"[place] ✗ {msg}", file=sys.stderr)
            return msg

    @mcp.tool()
    async def release_object() -> str:
        """释放当前抓取的物体。

        Returns:
            操作结果。
        """
        print("[place] 释放物体...", file=sys.stderr)
        result = call_omnigibson("/action/release", {})

        if result.get("success"):
            response = result.get("result")
            print(f"[place] ✓ {response}", file=sys.stderr)
            return response
        else:
            msg = result.get("result", "释放物体失败，请重试。")
            print(f"[place] ✗ {msg}", file=sys.stderr)
            return msg

    print("[place.py] 放置/开关控制模块已注册 (OmniGibson)", file=sys.stderr)
