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
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../master/scene')))
import LOCATION_MAP


def register_tools(mcp):
    """
    注册底盘相关的所有工具函数到 MCP 服务器

    Args:
        mcp: FastMCP 服务器实例
    """

    @mcp.tool()
    async def navigate_to_target(target: str) -> str:
        """Navigate to a target location.

        This function navigates the robot's base to a specified location in the scene.
        The target location should match one of the predefined locations in the scene configuration.

        Args:
            target: The name of the navigation destination (e.g., "kitchenTable", "trashCan", "livingRoom", "卧室", "客厅").

        Returns:
            A JSON string containing the result message and state updates.

        Examples:
            navigate_to_target(target="bedroom")  # Navigate to bedroom
            navigate_to_target(target="livingRoom")  # Navigate to living room
            navigate_to_target(target="卧室")  # Navigate to bedroom (Chinese)
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

        # Try to get coordinates from LOCATION_MAP (hardcoded for now)
        # In the future, this could be read from profile.yaml
        location_coordinates = {
            "entrance": [0.0, 0.0, 0.0],
            "livingRoom": [2.0, 3.0, 0.0],
            "bedroom": [4.0, 1.0, 0.0],
            "kitchenTable": [1.0, 2.0, 0.0],
            "customTable": [2.0, 1.0, 0.0],
            "servingTable": [3.0, 2.0, 0.0],
            "basket": [1.5, 1.5, 0.5],
            "trashCan": [4.0, 3.0, 0.0]
        }

        if target_en in location_coordinates:
            state_updates["coordinates"] = location_coordinates[target_en]
            print(f"[base.navigate_to_target] Updated coordinates to {location_coordinates[target_en]}", file=sys.stderr)

        # Return JSON array: [result_message, state_updates]
        response = json.dumps([result, state_updates], ensure_ascii=False)
        print(f"[base.navigate_to_target] Returning: {response}", file=sys.stderr)
        return response

    @mcp.tool()
    async def move(direction: float, speed: float, duration: float) -> str:
        """Control robot base movement (底盘移动).

        移动机器人底盘到指定方向，保持指定速度，持续指定时间。
        注意：这是控制底盘整体移动，不是机械臂关节运动。
        For arm joint control, use move_joint_relative or move_joint_absolute instead.

        Args:
            direction: Movement direction in robot coordinate system (0-360 degrees).
                       0 degrees = forward (positive direction of robot's coordinate system),
                       90 degrees = left, 180 degrees = backward, 270 degrees = right.
            speed: Movement speed in meters per second (e.g., 0.5 m/s).
            duration: Movement duration in seconds (e.g., 2.0 seconds).

        Returns:
            A tuple containing the result message and updated robot state with movement details.

        Examples:
            move(direction=0.0, speed=1.0, duration=2.0)  # Move forward at 1 m/s for 2 seconds
            move(direction=90.0, speed=0.5, duration=3.0)  # Move left at 0.5 m/s for 3 seconds
            move(direction=180.0, speed=0.8, duration=1.5)  # Move backward at 0.8 m/s for 1.5 seconds
        """
        # Calculate the distance moved
        distance = speed * duration

        # Normalize direction to 0-360 range
        direction_normalized = direction % 360

        # Determine direction description for better logging
        if direction_normalized == 0:
            direction_desc = "forward"
        elif direction_normalized == 90:
            direction_desc = "left"
        elif direction_normalized == 180:
            direction_desc = "backward"
        elif direction_normalized == 270:
            direction_desc = "right"
        else:
            direction_desc = f"{direction_normalized}°"

        # In a real robot, this would send commands to the motor controller.
        # For simulation, we just confirm the action is "done".
        result = f"Successfully moved {direction_desc} at {speed} m/s for {duration} seconds (distance: {distance:.2f} m)."

        # Log to stderr for debugging (visible in terminal)
        print(f"[base.move] Called with direction={direction}°, speed={speed} m/s, duration={duration} s, result: {result}", file=sys.stderr)

        # Return result message only (move doesn't update position state)
        return result

    print("[base.py]底盘控制模块已注册", file=sys.stderr)
