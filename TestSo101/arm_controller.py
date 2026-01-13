#!/usr/bin/env python3
"""SO101机械臂控制封装模块

为RoboOS提供机械臂控制接口,支持:
- 单关节控制
- 限位保护
- 状态查询
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 使用本地 motors 模块
from motors.feetech.feetech import FeetechMotorsBus, OperatingMode
from motors import Motor, MotorCalibration, MotorNormMode
import draccus


class SO101ArmController:
    """SO101机械臂控制器

    提供安全的机械臂控制接口,包含限位保护和状态管理
    """

    # 关节名称映射
    JOINT_NAMES = [
        "shoulder_pan",
        "shoulder_lift",
        "elbow_flex",
        "wrist_flex",
        "wrist_roll",
        "gripper",
    ]

    # 关节描述(中文)
    JOINT_DESCRIPTIONS = {
        "shoulder_pan": "肩部旋转",
        "shoulder_lift": "肩部抬起",
        "elbow_flex": "肘部弯曲",
        "wrist_flex": "手腕弯曲",
        "wrist_roll": "手腕旋转",
        "gripper": "夹爪"
    }

    def __init__(
        self,
        port: str = "/dev/ttyACM0",
        arm_name: str = "SO101-arm",
        calibration_dir: str = "./.calibration/",
        limits_file: str = "limits.json"
    ):
        """初始化机械臂控制器

        Args:
            port: 串口端口
            arm_name: 机械臂名称
            calibration_dir: 校准文件目录
            limits_file: 限位文件路径
        """
        self.port = port
        self.arm_name = arm_name
        self.calibration_dir = Path(calibration_dir)
        self.limits_file = limits_file
        self.arm_bus = None
        self.current_pos = None
        self.limits = None

    def connect(self) -> bool:
        """连接机械臂

        Returns:
            连接成功返回True,否则返回False
        """
        try:
            # 加载限位文件
            self.limits = self._load_limits()
            if self.limits is None:
                print("⚠ 警告: 限位加载失败,使用默认限位")

            # 加载校准文件
            calibration_fpath = self.calibration_dir / f"{self.arm_name}.json"
            with open(calibration_fpath) as f, draccus.config_type("json"):
                arm_calibration = draccus.load(dict[str, MotorCalibration], f)

            # 配置电机
            norm_mode = MotorNormMode.DEGREES

            # 创建机械臂总线
            self.arm_bus = FeetechMotorsBus(
                port=self.port,
                motors={
                    "shoulder_pan": Motor(1, "sts3215", norm_mode),
                    "shoulder_lift": Motor(2, "sts3215", norm_mode),
                    "elbow_flex": Motor(3, "sts3215", norm_mode),
                    "wrist_flex": Motor(4, "sts3215", norm_mode),
                    "wrist_roll": Motor(5, "sts3215", norm_mode),
                    "gripper": Motor(6, "sts3215", MotorNormMode.RANGE_0_100),
                },
                calibration=arm_calibration,
            )

            # 连接机械臂
            self.arm_bus.connect()
            print(f"✓ 已连接到 {self.arm_name}")

            # 配置为位置控制模式
            with self.arm_bus.torque_disabled():
                self.arm_bus.configure_motors()
                for motor in self.arm_bus.motors:
                    self.arm_bus.write("Operating_Mode", motor, OperatingMode.POSITION.value)
                    self.arm_bus.write("P_Coefficient", motor, 16)
                    self.arm_bus.write("I_Coefficient", motor, 0)
                    self.arm_bus.write("D_Coefficient", motor, 32)

            # 读取当前位置
            present_pos = self.arm_bus.sync_read("Present_Position")
            self.current_pos = [val for _, val in present_pos.items()]

            return True

        except Exception as e:
            print(f"✗ 连接失败: {e}")
            return False

    def disconnect(self):
        """断开机械臂连接"""
        if self.arm_bus is not None:
            try:
                self.arm_bus.disable_torque()
                time.sleep(0.5)
                self.arm_bus.disconnect(disable_torque=False)
                print(f"✓ 已断开 {self.arm_name}")
            except Exception as e:
                print(f"✗ 断开连接时出错: {e}")
            finally:
                self.arm_bus = None

    def _load_limits(self):
        """加载限位文件"""
        limits_path = Path(self.limits_file)
        if not limits_path.exists():
            print(f"⚠ 限位文件 {self.limits_file} 不存在")
            print(f"  使用默认限位: ±180°")
            return {
                "shoulder_pan": {"min": -180.0, "max": 180.0},
                "shoulder_lift": {"min": -180.0, "max": 180.0},
                "elbow_flex": {"min": -180.0, "max": 180.0},
                "wrist_flex": {"min": -180.0, "max": 180.0},
                "wrist_roll": {"min": -180.0, "max": 180.0},
                "gripper": {"min": 0.0, "max": 100.0},
            }

        try:
            with open(limits_path, 'r') as f:
                limits = json.load(f)
            print(f"✓ 已加载限位文件: {self.limits_file}")
            return limits
        except Exception as e:
            print(f"✗ 加载限位文件失败: {e}")
            return None

    def _check_limits(self, joint_name: str, angle: float) -> Tuple[bool, float, Optional[str]]:
        """检查单个关节是否超出限位

        Args:
            joint_name: 关节名称
            angle: 目标角度

        Returns:
            (is_safe, clipped_angle, warning_msg)
        """
        if self.limits and joint_name in self.limits:
            limit = self.limits[joint_name]
            if angle < limit['min']:
                return False, limit['min'], f"{joint_name} 达到最小限位 {limit['min']:.2f}°"
            elif angle > limit['max']:
                return False, limit['max'], f"{joint_name} 达到最大限位 {limit['max']:.2f}°"

        return True, angle, None

    def move_joint(self, joint_name: str, angle: float) -> Dict:
        """移动单个关节

        Args:
            joint_name: 关节名称 (shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_roll, gripper)
            angle: 目标角度

        Returns:
            执行结果字典
        """
        if self.arm_bus is None:
            return {
                "success": False,
                "message": "机械臂未连接",
                "joint_name": joint_name,
                "target_angle": angle
            }

        if joint_name not in self.JOINT_NAMES:
            return {
                "success": False,
                "message": f"未知关节: {joint_name}",
                "joint_name": joint_name,
                "target_angle": angle
            }

        try:
            # 获取关节索引
            joint_idx = self.JOINT_NAMES.index(joint_name)

            # 获取当前角度
            current_angle = self.current_pos[joint_idx]

            # 计算目标角度
            target_angle = current_angle + angle

            # 检查限位
            is_safe, clipped_angle, warning = self._check_limits(joint_name, target_angle)

            if not is_safe:
                # 超出限位,使用限制后的角度
                target_angle = clipped_angle
                print(f"⚠ 限位警告: {warning}")

            # 更新位置
            new_pos = self.current_pos.copy()
            new_pos[joint_idx] = target_angle

            # 发送命令
            goal_pos = {
                key: new_pos[motor.id - 1]
                for key, motor in self.arm_bus.motors.items()
            }
            self.arm_bus.sync_write("Goal_Position", goal_pos)
            self.current_pos = new_pos

            # 等待运动完成(简单等待,实际可以根据需要调整)
            time.sleep(0.1)

            description = self.JOINT_DESCRIPTIONS.get(joint_name, joint_name)

            return {
                "success": True,
                "message": f"{description}({joint_name}) 已调整 {angle:+.1f}°, 当前角度: {target_angle:.2f}°",
                "joint_name": joint_name,
                "description": description,
                "angle_delta": angle,
                "current_angle": target_angle,
                "previous_angle": current_angle,
                "warning": warning if not is_safe else None
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"控制失败: {str(e)}",
                "joint_name": joint_name,
                "target_angle": angle
            }

    def move_joint_absolute(self, joint_name: str, angle: float) -> Dict:
        """移动关节到绝对角度

        Args:
            joint_name: 关节名称
            angle: 绝对角度

        Returns:
            执行结果字典
        """
        if self.arm_bus is None:
            return {
                "success": False,
                "message": "机械臂未连接",
                "joint_name": joint_name,
                "target_angle": angle
            }

        if joint_name not in self.JOINT_NAMES:
            return {
                "success": False,
                "message": f"未知关节: {joint_name}",
                "joint_name": joint_name,
                "target_angle": angle
            }

        try:
            # 获取关节索引
            joint_idx = self.JOINT_NAMES.index(joint_name)

            # 检查限位
            is_safe, clipped_angle, warning = self._check_limits(joint_name, angle)

            if not is_safe:
                # 超出限位,使用限制后的角度
                angle = clipped_angle
                print(f"⚠ 限位警告: {warning}")

            # 更新位置
            new_pos = self.current_pos.copy()
            new_pos[joint_idx] = angle

            # 发送命令
            goal_pos = {
                key: new_pos[motor.id - 1]
                for key, motor in self.arm_bus.motors.items()
            }
            self.arm_bus.sync_write("Goal_Position", goal_pos)
            self.current_pos = new_pos

            # 等待运动完成
            time.sleep(0.1)

            description = self.JOINT_DESCRIPTIONS.get(joint_name, joint_name)

            return {
                "success": True,
                "message": f"{description}({joint_name}) 已移动到 {angle:.2f}°",
                "joint_name": joint_name,
                "description": description,
                "current_angle": angle,
                "warning": warning if not is_safe else None
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"控制失败: {str(e)}",
                "joint_name": joint_name,
                "target_angle": angle
            }

    def get_joint_position(self, joint_name: str) -> Dict:
        """获取关节当前位置

        Args:
            joint_name: 关节名称

        Returns:
            当前位置信息
        """
        if self.arm_bus is None:
            return {
                "success": False,
                "message": "机械臂未连接",
                "joint_name": joint_name
            }

        if joint_name not in self.JOINT_NAMES:
            return {
                "success": False,
                "message": f"未知关节: {joint_name}",
                "joint_name": joint_name
            }

        try:
            joint_idx = self.JOINT_NAMES.index(joint_name)
            current_angle = self.current_pos[joint_idx]
            description = self.JOINT_DESCRIPTIONS.get(joint_name, joint_name)

            return {
                "success": True,
                "joint_name": joint_name,
                "description": description,
                "current_angle": current_angle,
                "unit": "degrees"
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"读取失败: {str(e)}",
                "joint_name": joint_name
            }

    def get_all_positions(self) -> Dict:
        """获取所有关节位置

        Returns:
            所有关节位置信息
        """
        if self.arm_bus is None:
            return {
                "success": False,
                "message": "机械臂未连接"
            }

        try:
            positions = {}
            for i, joint_name in enumerate(self.JOINT_NAMES):
                positions[joint_name] = {
                    "description": self.JOINT_DESCRIPTIONS.get(joint_name, joint_name),
                    "angle": self.current_pos[i],
                    "unit": "degrees"
                }

            return {
                "success": True,
                "positions": positions,
                "timestamp": time.time()
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"读取失败: {str(e)}"
            }

    def reset_to_zero(self) -> Dict:
        """复位所有关节到零位

        Returns:
            执行结果
        """
        if self.arm_bus is None:
            return {
                "success": False,
                "message": "机械臂未连接"
            }

        try:
            # 所有关节归零
            zero_pos = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

            goal_pos = {
                key: zero_pos[motor.id - 1]
                for key, motor in self.arm_bus.motors.items()
            }
            self.arm_bus.sync_write("Goal_Position", goal_pos)
            self.current_pos = zero_pos

            # 等待运动完成
            time.sleep(1.0)

            return {
                "success": True,
                "message": "机械臂已复位到零位",
                "positions": zero_pos
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"复位失败: {str(e)}"
            }


# 全局控制器实例
_arm_controller: Optional[SO101ArmController] = None


def get_arm_controller() -> SO101ArmController:
    """获取全局机械臂控制器实例

    Returns:
        机械臂控制器实例
    """
    global _arm_controller
    if _arm_controller is None:
        _arm_controller = SO101ArmController()
    return _arm_controller
