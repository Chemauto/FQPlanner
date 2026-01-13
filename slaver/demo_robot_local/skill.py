import sys
import os
import signal
import atexit
from mcp.server.fastmcp import FastMCP

# 添加TestSo101路径到sys.path
testso101_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../TestSo101'))
sys.path.insert(0, testso101_path)

# 导入机械臂控制器
from arm_controller import get_arm_controller

# Initialize FastMCP server
mcp = FastMCP("robots")

# 获取机械臂控制器实例
arm_controller = None


def cleanup_arm():
    """清理机械臂连接 - 禁用扭矩使机械臂松弛"""
    global arm_controller
    if arm_controller is not None:
        try:
            print("[skill.py] 正在断开机械臂连接并禁用扭矩...", file=sys.stderr)
            arm_controller.disconnect()
            print("[skill.py] ✓ 机械臂已断电，可以自由移动", file=sys.stderr)
        except Exception as e:
            print(f"[skill.py] ✗ 断开机械臂时出错: {e}", file=sys.stderr)
        finally:
            arm_controller = None


def signal_handler(signum, frame):
    """信号处理器 - 处理Ctrl+C等信号"""
    print(f"[skill.py] 收到信号 {signum}，正在清理...", file=sys.stderr)
    cleanup_arm()
    sys.exit(0)


# 注册退出处理函数
atexit.register(cleanup_arm)
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def initialize_arm():
    """初始化机械臂连接"""
    global arm_controller
    if arm_controller is None:
        arm_controller = get_arm_controller()
        try:
            # 使用TestSo101目录下的配置
            os.chdir(testso101_path)
            success = arm_controller.connect()
            if success:
                print("[skill.py] ✓ SO101机械臂连接成功", file=sys.stderr)
            else:
                print("[skill.py] ✗ SO101机械臂连接失败", file=sys.stderr)
        except Exception as e:
            print(f"[skill.py] ✗ 机械臂初始化异常: {e}", file=sys.stderr)
            arm_controller = None


@mcp.tool()
async def move_joint_relative(joint_name: str, angle: float) -> tuple[str, dict]:
    """Move robot arm joint by relative angle.

    This function controls the SO101 robotic arm joints by adjusting them relative to their current position.
    For example, if you specify joint_name="wrist_flex" and angle=10, the wrist will rotate 10 degrees
    from its current position.

    Args:
        joint_name: The name of the joint to move. Available joints:
                   - "shoulder_pan": Shoulder rotation (left/right)
                   - "shoulder_lift": Shoulder lift (up/down)
                   - "elbow_flex": Elbow flexion (forward/backward)
                   - "wrist_flex": Wrist flexion (up/down)
                   - "wrist_roll": Wrist rotation (left/right rotation)
                   - "gripper": Gripper open/close (0-100 range)
        angle: Relative angle in degrees to move the joint.
               Positive values rotate in one direction, negative in the opposite direction.
               For gripper: -100 to 100 (negative=open, positive=close)
               For other joints: typically -180 to 180 degrees, but limited by safety limits

    Returns:
        A tuple containing the result message and updated robot state.

    Examples:
        move_joint_relative(joint_name="wrist_flex", angle=10.0)  # Move wrist flex up by 10 degrees
        move_joint_relative(joint_name="shoulder_pan", angle=-5.0)  # Rotate shoulder left by 5 degrees
        move_joint_relative(joint_name="gripper", angle=50.0)  # Close gripper by 50 units
    """
    global arm_controller

    # 确保机械臂已初始化
    if arm_controller is None:
        initialize_arm()

    if arm_controller is None or arm_controller.arm_bus is None:
        error_msg = "机械臂未连接,无法执行命令"
        print(f"[move_joint_relative] {error_msg}", file=sys.stderr)
        return error_msg, {"error": "arm_not_connected", "joint_name": joint_name, "angle": angle}

    # 执行关节运动
    result = arm_controller.move_joint(joint_name, angle)

    # 记录日志
    print(f"[move_joint_relative] joint={joint_name}, angle={angle}°, result: {result['message']}", file=sys.stderr)

    # 构建返回的状态
    state_update = {
        "joint_name": joint_name,
        "angle_delta": angle,
        "success": result["success"]
    }

    if result["success"]:
        state_update.update({
            "current_angle": result.get("current_angle"),
            "previous_angle": result.get("previous_angle")
        })

    return result["message"], state_update


@mcp.tool()
async def move_joint_absolute(joint_name: str, angle: float) -> tuple[str, dict]:
    """Move robot arm joint to an absolute angle position.

    This function controls the SO101 robotic arm by moving a joint to a specific absolute angle.
    Unlike move_joint_relative which adjusts from the current position, this function moves
    the joint to an exact angle regardless of current position.

    Args:
        joint_name: The name of the joint to move. Available joints:
                   - "shoulder_pan": Shoulder rotation (left/right)
                   - "shoulder_lift": Shoulder lift (up/down)
                   - "elbow_flex": Elbow flexion (forward/backward)
                   - "wrist_flex": Wrist flexion (up/down)
                   - "wrist_roll": Wrist rotation (left/right rotation)
                   - "gripper": Gripper position (0-100 range, 0=open, 100=closed)
        angle: Absolute target angle in degrees.
               Typical ranges:
               - shoulder_pan: -90 to 90 degrees
               - shoulder_lift: -45 to 90 degrees
               - elbow_flex: -90 to 90 degrees
               - wrist_flex: -90 to 90 degrees
               - wrist_roll: -180 to 180 degrees
               - gripper: 0 to 100 (0=open, 100=closed)
               Actual limits are enforced by safety limits configuration

    Returns:
        A tuple containing the result message and updated robot state.

    Examples:
        move_joint_absolute(joint_name="wrist_flex", angle=45.0)  # Move wrist to exactly 45 degrees
        move_joint_absolute(joint_name="shoulder_pan", angle=0.0)  # Center shoulder rotation
        move_joint_absolute(joint_name="gripper", angle=0.0)  # Fully open gripper
    """
    global arm_controller

    # 确保机械臂已初始化
    if arm_controller is None:
        initialize_arm()

    if arm_controller is None or arm_controller.arm_bus is None:
        error_msg = "机械臂未连接,无法执行命令"
        print(f"[move_joint_absolute] {error_msg}", file=sys.stderr)
        return error_msg, {"error": "arm_not_connected", "joint_name": joint_name, "angle": angle}

    # 执行关节运动
    result = arm_controller.move_joint_absolute(joint_name, angle)

    # 记录日志
    print(f"[move_joint_absolute] joint={joint_name}, target_angle={angle}°, result: {result['message']}", file=sys.stderr)

    # 构建返回的状态
    state_update = {
        "joint_name": joint_name,
        "target_angle": angle,
        "success": result["success"]
    }

    if result["success"]:
        state_update.update({
            "current_angle": result.get("current_angle")
        })

    return result["message"], state_update


@mcp.tool()
async def get_joint_position(joint_name: str) -> tuple[str, dict]:
    """Get the current angle position of a robot arm joint.

    Args:
        joint_name: The name of the joint to query. Available joints:
                   - "shoulder_pan": Shoulder rotation (left/right)
                   - "shoulder_lift": Shoulder lift (up/down)
                   - "elbow_flex": Elbow flexion (forward/backward)
                   - "wrist_flex": Wrist flexion (up/down)
                   - "wrist_roll": Wrist rotation (left/right rotation)
                   - "gripper": Gripper position (0-100 range)

    Returns:
        A tuple containing the result message and current joint position.

    Examples:
        get_joint_position(joint_name="wrist_flex")  # Get current wrist flex angle
        get_joint_position(joint_name="gripper")  # Get current gripper opening
    """
    global arm_controller

    # 确保机械臂已初始化
    if arm_controller is None:
        initialize_arm()

    if arm_controller is None or arm_controller.arm_bus is None:
        error_msg = "机械臂未连接,无法读取位置"
        print(f"[get_joint_position] {error_msg}", file=sys.stderr)
        return error_msg, {"error": "arm_not_connected", "joint_name": joint_name}

    # 读取关节位置
    result = arm_controller.get_joint_position(joint_name)

    # 记录日志
    if result["success"]:
        print(f"[get_joint_position] {joint_name} = {result['current_angle']:.2f}°", file=sys.stderr)
    else:
        print(f"[get_joint_position] {result['message']}", file=sys.stderr)

    return result["message"], result


@mcp.tool()
async def get_all_joint_positions() -> tuple[str, dict]:
    """Get current angle positions of all robot arm joints.

    This function returns the current position of all 6 joints of the SO101 robotic arm,
    providing a complete snapshot of the arm's current configuration.

    Returns:
        A tuple containing the result message and current positions of all joints.

    Examples:
        get_all_joint_positions()  # Returns all joint positions
    """
    global arm_controller

    # 确保机械臂已初始化
    if arm_controller is None:
        initialize_arm()

    if arm_controller is None or arm_controller.arm_bus is None:
        error_msg = "机械臂未连接,无法读取位置"
        print(f"[get_all_joint_positions] {error_msg}", file=sys.stderr)
        return error_msg, {"error": "arm_not_connected"}

    # 读取所有关节位置
    result = arm_controller.get_all_positions()

    # 记录日志
    if result["success"]:
        pos_str = ", ".join([
            f"{name}: {data['angle']:.1f}°"
            for name, data in result["positions"].items()
        ])
        print(f"[get_all_joint_positions] {pos_str}", file=sys.stderr)
    else:
        print(f"[get_all_joint_positions] {result['message']}", file=sys.stderr)

    return result["message"], result


@mcp.tool()
async def reset_arm_to_zero() -> tuple[str, dict]:
    """Reset all robot arm joints to zero position.

    This function moves all joints of the SO101 robotic arm to their zero (home) position.
    This is useful for homing the arm or returning to a known safe position.

    Returns:
        A tuple containing the result message and updated robot state.

    Examples:
        reset_arm_to_zero()  # Reset all joints to zero
    """
    global arm_controller

    # 确保机械臂已初始化
    if arm_controller is None:
        initialize_arm()

    if arm_controller is None or arm_controller.arm_bus is None:
        error_msg = "机械臂未连接,无法执行复位"
        print(f"[reset_arm_to_zero] {error_msg}", file=sys.stderr)
        return error_msg, {"error": "arm_not_connected"}

    # 执行复位
    result = arm_controller.reset_to_zero()

    # 记录日志
    print(f"[reset_arm_to_zero] {result['message']}", file=sys.stderr)

    return result["message"], {"reset": result["success"]}


@mcp.tool()
async def navigate_to_target(target: str) -> tuple[str, dict]:
    """Navigate to a target location.

    Args:
        target: The name of the navigation destination (e.g., "kitchenTable", "trashCan").
    """
    # In a real robot, this would contain navigation logic.
    # For simulation, we just confirm the action is "done".
    result = f"Navigation to {target} has been successfully performed."

    # Log to stderr for debugging (visible in terminal)
    print(f"[navigate_to_target] Called with target='{target}', result: {result}", file=sys.stderr)

    # The returned dictionary updates the robot's state.
    return result, {"position": f"{target}"}


@mcp.tool()
async def move(direction: float, speed: float, duration: float) -> tuple[str, dict]:
    """Move the robot in a specific direction with given speed and duration.

    Args:
        direction: Movement direction in robot coordinate system (0-360 degrees).
                   0 degrees = forward (positive direction of robot's coordinate system),
                   90 degrees = left, 180 degrees = backward, 270 degrees = right.
        speed: Movement speed in meters per second (e.g., 0.5 m/s).
        duration: Movement duration in seconds (e.g., 2.0 seconds).

    Returns:
        A tuple containing the result message and updated robot state.

    Example:
        move(direction=0.0, speed=1.0, duration=2.0)  # Move forward at 1 m/s for 2 seconds
        move(direction=90.0, speed=0.5, duration=3.0)  # Move left at 0.5 m/s for 3 seconds
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
    print(f"[move] Called with direction={direction}°, speed={speed} m/s, duration={duration} s, result: {result}", file=sys.stderr)

    # The returned dictionary updates the robot's state.
    # We record the movement parameters for potential future use.
    return result, {
        "last_movement": {
            "direction": direction_normalized,
            "speed": speed,
            "duration": duration,
            "distance": distance
        }
    }


if __name__ == "__main__":
    # Initialize and run the MCP server to listen for tool calls.
    print("[skill.py] Starting MCP server for SO101 arm control...", file=sys.stderr)
    print(f"[skill.py] TestSo101 path: {testso101_path}", file=sys.stderr)
    mcp.run(transport="stdio")
