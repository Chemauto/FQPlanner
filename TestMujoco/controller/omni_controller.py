"""
三麦克纳姆轮底盘运动控制器
根据LeKiwi官方实现,使用标准的三轮全向轮运动学
轮子配置: 120°间隔 (左轮30°, 右轮150°, 后轮270°)
"""

import mujoco
import numpy as np


class OmniWheelController:
    def __init__(self, model, data):
        """
        初始化三轮全向轮底盘控制器

        参数:
            model: MuJoCo 模型实例
            data: MuJoCo 数据实例
        """
        self.model = model
        self.data = data

        # 获取三个执行器ID
        self.left_wheel_actuator_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_ACTUATOR, 'base_left_wheel'
        )
        self.right_wheel_actuator_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_ACTUATOR, 'base_right_wheel'
        )
        self.back_wheel_actuator_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_ACTUATOR, 'base_back_wheel'
        )

        # 轮子参数
        self.wheel_radius = 0.051  # 轮子半径 (米)
        self.robot_base_radius = 0.0923  # 从中心到轮子的距离 (米)

        # 计算逆运动学矩阵 (用于从机器人速度计算轮子速度)
        # F_matrix将轮子速度映射到机器人速度
        # F_matrix_inv将机器人速度映射到轮子速度
        F_matrix = self.wheel_radius * np.array([
            [np.sqrt(3) / 2, -np.sqrt(3) / 2, 0],
            [-1 / 2, -1 / 2, 1],
            [-1 / (3 * self.robot_base_radius), -1 / (3 * self.robot_base_radius), -1 / (3 * self.robot_base_radius)]
        ])
        self.F_matrix_inv = np.linalg.inv(F_matrix)

        # 当前控制值
        self.left_wheel_ctrl = 0.0
        self.right_wheel_ctrl = 0.0
        self.back_wheel_ctrl = 0.0

    def set_velocity(self, linear_speed, vx, vy, omega=0):
        """
        设置机器人速度

        参数:
            linear_speed: 速度大小 (m/s)
            vx: 机器人坐标系下x方向速度分量 (归一化, -1到1)
            vy: 机器人坐标系下y方向速度分量 (归一化, -1到1)
            omega: 旋转角速度 (rad/s), 正值=逆时针旋转, 负值=顺时针旋转, 默认=0

        说明:
            vx, vy 是方向向量,会被归一化并乘以linear_speed
            omega 直接使用,不进行归一化
            例如:
                vx=1, vy=0 表示向前; vx=0, vy=1 表示向左
                omega=1 表示逆时针旋转 1 rad/s
        """
        # 归一化方向向量并乘以速度大小
        v_norm = np.sqrt(vx**2 + vy**2)
        if v_norm > 0:
            vx = vx / v_norm * linear_speed
            vy = vy / v_norm * linear_speed
        else:
            vx = 0
            vy = 0

        # 使用逆运动学矩阵计算轮子速度
        robot_velocity = np.array([vx, vy, omega])
        wheel_velocities = self.F_matrix_inv @ robot_velocity

        # 轮子速度顺序: [left, right, back]
        self.left_wheel_ctrl = wheel_velocities[0]
        self.right_wheel_ctrl = wheel_velocities[1]
        self.back_wheel_ctrl = wheel_velocities[2]

        # 限制在执行器范围内 (-3.14 到 3.14 rad/s)
        max_omega = 3.14
        self.left_wheel_ctrl = np.clip(self.left_wheel_ctrl, -max_omega, max_omega)
        self.right_wheel_ctrl = np.clip(self.right_wheel_ctrl, -max_omega, max_omega)
        self.back_wheel_ctrl = np.clip(self.back_wheel_ctrl, -max_omega, max_omega)

    def set_velocity_raw(self, vx, vy, omega=0):
        """
        直接设置速度分量 (带旋转控制)

        参数:
            vx: x方向速度 (m/s)
            vy: y方向速度 (m/s)
            omega: 旋转角速度 (rad/s), 默认0
        """
        # 使用逆运动学矩阵计算轮子速度
        robot_velocity = np.array([vx, vy, omega])
        wheel_velocities = self.F_matrix_inv @ robot_velocity

        # 轮子速度顺序: [left, right, back]
        self.left_wheel_ctrl = wheel_velocities[0]
        self.right_wheel_ctrl = wheel_velocities[1]
        self.back_wheel_ctrl = wheel_velocities[2]

        # 限制在执行器范围内 (-3.14 到 3.14 rad/s)
        max_omega = 3.14
        self.left_wheel_ctrl = np.clip(self.left_wheel_ctrl, -max_omega, max_omega)
        self.right_wheel_ctrl = np.clip(self.right_wheel_ctrl, -max_omega, max_omega)
        self.back_wheel_ctrl = np.clip(self.back_wheel_ctrl, -max_omega, max_omega)

    def get_wheel_velocities(self):
        """
        获取当前轮子控制速度

        返回:
            (left, right, back) 三个轮子的角速度 (rad/s)
        """
        return (self.left_wheel_ctrl, self.right_wheel_ctrl, self.back_wheel_ctrl)

    def stop(self):
        """停止所有轮子"""
        self.left_wheel_ctrl = 0.0
        self.right_wheel_ctrl = 0.0
        self.back_wheel_ctrl = 0.0

    def apply_control(self):
        """
        将控制信号应用到 MuJoCo 执行器

        这个方法应该在每次 mj_step 之前调用
        """
        self.data.ctrl[self.left_wheel_actuator_id] = self.left_wheel_ctrl
        self.data.ctrl[self.right_wheel_actuator_id] = self.right_wheel_ctrl
        self.data.ctrl[self.back_wheel_actuator_id] = self.back_wheel_ctrl

    def get_robot_position(self):
        """
        获取机器人当前位置

        返回:
            numpy数组，包含 [x, y, z] 位置坐标
        """
        robot_body_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, 'base_plate_layer_1_link')
        return self.data.xpos[robot_body_id].copy()

    def get_robot_orientation(self):
        """
        获取机器人当前姿态

        返回:
            numpy数组，包含 [w, x, y, z] 四元数
        """
        robot_body_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, 'base_plate_layer_1_link')
        return self.data.xquat[robot_body_id].copy()
