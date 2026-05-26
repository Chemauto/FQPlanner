"""
放置/释放控制模块 - RoboCasa 仿真
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from serve.sim import (
    place_object as _place_object,
    open_gripper as _open_gripper,
    get_objects,
)


def register_tools(mcp):

    @mcp.tool()
    async def place_on_top(obj_name: str, target_name: str) -> str:
        """将物体放置在目标物体上面。

        Args:
            obj_name: 要放置的物体名称（如 "mug"）
            target_name: 目标物体名称（如 "table"、"plate"）

        Returns:
            放置结果，成功或失败信息。
        """
        print(f"[place] 将 '{obj_name}' 放在 '{target_name}' 上面...", file=sys.stderr)

        objects = get_objects()
        if not objects or "error" in objects:
            return f"无法获取物体信息，请检查仿真状态"

        if target_name not in objects:
            return f"未找到目标物体 '{target_name}'"

        target_pos = objects[target_name]["pos"]
        place_pos = [target_pos[0], target_pos[1], target_pos[2] + 0.05]

        result = _place_object(obj_name, place_pos)

        if result.get("success"):
            response = result.get("result", f"成功将 {obj_name} 放在 {target_name} 上面")
            print(f"[place] ✓ {response}", file=sys.stderr)
            return response
        else:
            msg = result.get("result", f"放置失败，请重试。")
            print(f"[place] ✗ {msg}", file=sys.stderr)
            return msg

    @mcp.tool()
    async def place_object(obj_name: str, x: float, y: float, z: float) -> str:
        """将物体放置到指定坐标位置。

        Args:
            obj_name: 要放置的物体名称
            x: 目标位置 x 坐标
            y: 目标位置 y 坐标
            z: 目标位置 z 坐标

        Returns:
            放置结果，成功或失败信息。
        """
        target_pos = [x, y, z]
        print(f"[place] 将 '{obj_name}' 放到 {target_pos}...", file=sys.stderr)

        result = _place_object(obj_name, target_pos)

        if result.get("success"):
            response = result.get("result", f"成功将 {obj_name} 放到目标位置")
            print(f"[place] ✓ {response}", file=sys.stderr)
            return response
        else:
            msg = result.get("result", f"放置失败，请重试。")
            print(f"[place] ✗ {msg}", file=sys.stderr)
            return msg

    # @mcp.tool()
    # async def release_object() -> str:
    #     """释放当前抓取的物体（打开夹爪）。

    #     Returns:
    #         操作结果。
    #     """
    #     print("[place] 释放物体...", file=sys.stderr)
    #     result = _open_gripper()

    #     if result.get("success"):
    #         response = "成功释放物体"
    #         print(f"[place] ✓ {response}", file=sys.stderr)
    #         return response
    #     else:
    #         msg = result.get("result", "释放物体失败，请重试。")
    #         print(f"[place] ✗ {msg}", file=sys.stderr)
    #         return msg

    # print("[place.py] 放置/释放控制模块已注册 (RoboCasa)", file=sys.stderr)
