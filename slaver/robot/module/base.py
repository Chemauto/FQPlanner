"""
底盘控制模块 (Base Control Module)

负责机器人的底盘移动和导航功能。

Functions:
    - navigate_to_target: 导航到目标位置
    - move: 按指定方向、速度和时间移动
"""

import sys
import os

# Import location map from master/scene directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../master/scene')))
import LOCATION_MAP


def register_tools(mcp):
    """
    注册底盘相关的所有工具函数到 MCP 服务器

    Args:
        mcp: FastMCP 服务器实例
    """

    @mcp.tool()
    async def navigate_to_target(target: str) -> str:
        """导航到目标位置。

        将机器人底盘导航到场景中的指定位置，目标位置需匹配场景配置中的预定义位置。
        支持中英文位置名称。

        Args:
            target: 导航目标位置名称（如 "kitchenTable"、"卧室"、"客厅"、"bedroom"）。

        Returns:
            包含结果消息和状态更新的 JSON 字符串。

        Examples:
            navigate_to_target(target="bedroom")
            navigate_to_target(target="卧室")
        """
        import json

        # Map Chinese name to English if needed
        target_en = LOCATION_MAP.LOCATION_MAP.get(target, target)

        # In a real robot, this would contain navigation logic.
        # For simulation, we just confirm the action is "done".
        result = f"Navigation to {target} has been successfully performed."

        # Log to stderr for debugging (visible in terminal)
        print(f"[base.navigate_to_target] Called with target='{target}' (mapped to '{target_en}'), result: {result}", file=sys.stderr)

        # Build state updates with position and coordinates
        state_updates = {"position": target_en}

        # Read coordinates from profile.yaml
        import yaml
        profile_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../master/scene/profile.yaml'))
        try:
            with open(profile_path, "r", encoding="utf-8") as f:
                profile = yaml.safe_load(f)
            for item in profile.get("scene", []):
                if item.get("name") == target_en:
                    state_updates["coordinates"] = item["position"]
                    print(f"[base.navigate_to_target] Updated coordinates to {item['position']}", file=sys.stderr)
                    break
        except Exception as e:
            print(f"[base.navigate_to_target] Failed to read profile.yaml: {e}", file=sys.stderr)

        # Return JSON array: [result_message, state_updates]
        response = json.dumps([result, state_updates], ensure_ascii=False)
        print(f"[base.navigate_to_target] Returning: {response}", file=sys.stderr)
        return response

    # @mcp.tool()
    # async def move(direction: float, speed: float, duration: float) -> str:
    #     """控制底盘移动。

    #     按指定方向、速度和时间移动机器人底盘。注意：这是底盘整体移动，不是机械臂关节运动。

    #     Args:
    #         direction: 移动方向（0-360度），0=前进，90=左移，180=后退，270=右移。
    #         speed: 移动速度（米/秒，如 0.5）。
    #         duration: 移动持续时间（秒，如 2.0）。

    #     Returns:
    #         包含移动结果和距离信息的字符串。

    #     Examples:
    #         move(direction=0.0, speed=1.0, duration=2.0)   # 前进 1m/s 持续 2 秒
    #         move(direction=90.0, speed=0.5, duration=3.0)   # 左移 0.5m/s 持续 3 秒
    #     """
    #     # Calculate the distance moved
    #     distance = speed * duration

    #     # Normalize direction to 0-360 range
    #     direction_normalized = direction % 360

    #     # Determine direction description for better logging
    #     if direction_normalized == 0:
    #         direction_desc = "forward"
    #     elif direction_normalized == 90:
    #         direction_desc = "left"
    #     elif direction_normalized == 180:
    #         direction_desc = "backward"
    #     elif direction_normalized == 270:
    #         direction_desc = "right"
    #     else:
    #         direction_desc = f"{direction_normalized}°"

    #     # In a real robot, this would send commands to the motor controller.
    #     # For simulation, we just confirm the action is "done".
    #     result = f"Successfully moved {direction_desc} at {speed} m/s for {duration} seconds (distance: {distance:.2f} m)."

    #     # Log to stderr for debugging (visible in terminal)
    #     print(f"[base.move] Called with direction={direction}°, speed={speed} m/s, duration={duration} s, result: {result}", file=sys.stderr)

    #     # Return result message only (move doesn't update position state)
    #     return result

    # print("[base.py]底盘控制模块已注册", file=sys.stderr)
