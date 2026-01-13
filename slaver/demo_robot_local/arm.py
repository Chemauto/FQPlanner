"""
机械臂控制模块 (Arm Control Module)

负责 SO101 机械臂的运动控制功能。

Functions:
    - move_joint_relative: 相对角度移动关节
    - move_joint_absolute: 绝对角度移动关节
    - get_joint_position: 获取单个关节位置
    - get_all_joint_positions: 获取所有关节位置
    # - reset_arm_to_zero: 复位到零点（这个函数先不用）
"""

import sys
import os
from typing import Tuple, Dict

# 添加TestSo101路径到sys.path
testso101_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../TestSo101'))
sys.path.insert(0, testso101_path)

# 导入机械臂控制器
from arm_controller import get_arm_controller

# 获取机械臂控制器实例
arm_controller = None


def cleanup_arm():
    """清理机械臂连接 - 禁用扭矩使机械臂松弛"""
    global arm_controller
    if arm_controller is not None:
        try:
            print("[arm.py] 正在断开机械臂连接并禁用扭矩...", file=sys.stderr)
            arm_controller.disconnect()
            print("[arm.py] ✓ 机械臂已断电，可以自由移动", file=sys.stderr)
        except Exception as e:
            print(f"[arm.py] ✗ 断开机械臂时出错: {e}", file=sys.stderr)
        finally:
            arm_controller = None


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
                print("[arm.py] ✓ SO101机械臂连接成功", file=sys.stderr)
            else:
                print("[arm.py] ✗ SO101机械臂连接失败", file=sys.stderr)
        except Exception as e:
            print(f"[arm.py] ✗ 机械臂初始化异常: {e}", file=sys.stderr)
            arm_controller = None


def register_tools(mcp):
    """
    注册机械臂相关的所有工具函数到 MCP 服务器

    Args:
        mcp: FastMCP 服务器实例
    """

    @mcp.tool()
    async def move_joint_relative(joint_name: str, angle: float) -> Tuple[str, Dict]:
        """Control robot arm joint by relative angle (机械臂关节相对角度运动).

        控制机械臂关节相对当前角度转动。这是控制机械臂，不是底盘移动。
        For base movement, use navigate_to_target or move instead.

        此函数控制SO101机械臂的关节相对当前位置转动。
        例如：指定joint_name="wrist_flex"和angle=10，腕部将在当前位置基础上转动10度。

        Args:
            joint_name: The name of the joint to move. Available joints:
                       - "shoulder_pan": 肩部旋转 (左右旋转)
                       - "shoulder_lift": 肩部升降 (上下运动)
                       - "elbow_flex": 肘部弯曲 (前后弯曲)
                       - "wrist_flex": 腕部弯曲 (上下弯曲)
                       - "wrist_roll": 腕部旋转 (左右旋转)
                       - "gripper": 夹爪 (0-100范围，0=张开，100=闭合)
            angle: Relative angle in degrees to move the joint.
                   正值向一个方向转动，负值向相反方向转动。
                   对于夹爪：-100到100（负数=张开，正数=闭合）
                   对于其他关节：通常-180到180度，但受安全限制约束

        Returns:
            A tuple containing the result message and updated robot state.

        Examples:
            move_joint_relative(joint_name="wrist_flex", angle=10.0)  # 腕部向上转10度
            move_joint_relative(joint_name="shoulder_pan", angle=-5.0)  # 肩部向左转5度
            move_joint_relative(joint_name="gripper", angle=50.0)  # 夹爪闭合50
        """
        global arm_controller

        # 确保机械臂已初始化
        if arm_controller is None:
            initialize_arm()

        if arm_controller is None or arm_controller.arm_bus is None:
            error_msg = "机械臂未连接,无法执行命令"
            print(f"[arm.move_joint_relative] {error_msg}", file=sys.stderr)
            return error_msg, {"error": "arm_not_connected", "joint_name": joint_name, "angle": angle}

        # 执行关节运动
        result = arm_controller.move_joint(joint_name, angle)

        # 记录日志
        print(f"[arm.move_joint_relative] joint={joint_name}, angle={angle}°, result: {result['message']}", file=sys.stderr)

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
    async def move_joint_absolute(joint_name: str, angle: float) -> Tuple[str, Dict]:
        """Control robot arm joint to absolute angle (机械臂关节绝对角度运动).

        控制机械臂关节移动到指定的绝对角度位置。这是控制机械臂，不是底盘移动。
        For base movement, use navigate_to_target or move instead.

        此函数将机械臂关节移动到精确的绝对角度，不考虑当前位置。
        与move_joint_relative不同，此函数会移动到确切的角度。

        Args:
            joint_name: The name of the joint to move. Available joints:
                       - "shoulder_pan": 肩部旋转 (左右旋转)
                       - "shoulder_lift": 肩部升降 (上下运动)
                       - "elbow_flex": 肘部弯曲 (前后弯曲)
                       - "wrist_flex": 腕部弯曲 (上下弯曲)
                       - "wrist_roll": 腕部旋转 (左右旋转)
                       - "gripper": 夹爪位置 (0-100范围，0=张开，100=闭合)
            angle: Absolute target angle in degrees.
                   典型范围：
                   - shoulder_pan: -90到90度
                   - shoulder_lift: -45到90度
                   - elbow_flex: -90到90度
                   - wrist_flex: -90到90度
                   - wrist_roll: -180到180度
                   - gripper: 0到100 (0=张开，100=闭合)
                   实际限制由安全配置强制执行

        Returns:
            A tuple containing the result message and updated robot state.

        Examples:
            move_joint_absolute(joint_name="wrist_flex", angle=45.0)  # 腕部移动到45度
            move_joint_absolute(joint_name="shoulder_pan", angle=0.0)  # 肩部居中
            move_joint_absolute(joint_name="gripper", angle=0.0)  # 夹爪完全张开
        """
        global arm_controller

        # 确保机械臂已初始化
        if arm_controller is None:
            initialize_arm()

        if arm_controller is None or arm_controller.arm_bus is None:
            error_msg = "机械臂未连接,无法执行命令"
            print(f"[arm.move_joint_absolute] {error_msg}", file=sys.stderr)
            return error_msg, {"error": "arm_not_connected", "joint_name": joint_name, "angle": angle}

        # 执行关节运动
        result = arm_controller.move_joint_absolute(joint_name, angle)

        # 记录日志
        print(f"[arm.move_joint_absolute] joint={joint_name}, target_angle={angle}°, result: {result['message']}", file=sys.stderr)

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
    async def get_joint_position(joint_name: str) -> Tuple[str, Dict]:
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
            print(f"[arm.get_joint_position] {error_msg}", file=sys.stderr)
            return error_msg, {"error": "arm_not_connected", "joint_name": joint_name}

        # 读取关节位置
        result = arm_controller.get_joint_position(joint_name)

        # 记录日志
        if result["success"]:
            print(f"[arm.get_joint_position] {joint_name} = {result['current_angle']:.2f}°", file=sys.stderr)
        else:
            print(f"[arm.get_joint_position] {result['message']}", file=sys.stderr)

        return result["message"], result

    @mcp.tool()
    async def get_all_joint_positions() -> Tuple[str, Dict]:
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
            print(f"[arm.get_all_joint_positions] {error_msg}", file=sys.stderr)
            return error_msg, {"error": "arm_not_connected"}

        # 读取所有关节位置
        result = arm_controller.get_all_positions()

        # 记录日志
        if result["success"]:
            pos_str = ", ".join([
                f"{name}: {data['angle']:.1f}°"
                for name, data in result["positions"].items()
            ])
            print(f"[arm.get_all_joint_positions] {pos_str}", file=sys.stderr)
        else:
            print(f"[arm.get_all_joint_positions] {result['message']}", file=sys.stderr)

        return result["message"], result

    # @mcp.tool()
    # async def reset_arm_to_zero() -> Tuple[str, Dict]:
    #     """Reset all robot arm joints to zero position.

    #     This function moves all joints of the SO101 robotic arm to their zero (home) position.
    #     This is useful for homing the arm or returning to a known safe position.

    #     Returns:
    #         A tuple containing the result message and updated robot state.

    #     Examples:
    #         reset_arm_to_zero()  # Reset all joints to zero
    #     """
    #     global arm_controller

    #     # 确保机械臂已初始化
    #     if arm_controller is None:
    #         initialize_arm()

    #     if arm_controller is None or arm_controller.arm_bus is None:
    #         error_msg = "机械臂未连接,无法执行复位"
    #         print(f"[arm.reset_arm_to_zero] {error_msg}", file=sys.stderr)
    #         return error_msg, {"error": "arm_not_connected"}

    #     # 执行复位
    #     result = arm_controller.reset_to_zero()

    #     # 记录日志
    #     print(f"[arm.reset_arm_to_zero] {result['message']}", file=sys.stderr)

    #     return result["message"], {"reset": result["success"]}

    print("[arm.py] 机械臂控制模块已注册", file=sys.stderr)
