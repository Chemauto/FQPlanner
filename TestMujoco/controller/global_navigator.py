"""
全局导航控制器 - 支持点到点位置控制
使用PID控制器实现精确的位置和姿态控制
"""

import sys
import mujoco
import numpy as np
from scipy.spatial.transform import Rotation as R


class PIDController:
    """简单的PID控制器 (带抗饱和)"""

    def __init__(self, kp, ki, kd, output_limits=None, integral_limits=None):
        """
        初始化PID控制器

        参数:
            kp: 比例增益
            ki: 积分增益
            kd: 微分增益
            output_limits: 输出限制 (min, max), None表示不限制
            integral_limits: 积分项限制 (min, max), 防止积分饱和
        """
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.output_limits = output_limits
        self.integral_limits = integral_limits

        self.integral = 0.0
        self.last_error = 0.0
        self.last_time = None

    def compute(self, error, dt):
        """
        计算PID输出

        参数:
            error: 当前误差
            dt: 时间步长

        返回:
            控制输出
        """
        # 比例项
        p_term = self.kp * error

        # 积分项 (带抗饱和限制)
        self.integral += error * dt
        if self.integral_limits is not None:
            self.integral = np.clip(self.integral, self.integral_limits[0], self.integral_limits[1])
        i_term = self.ki * self.integral

        # 微分项
        if self.last_error is not None:
            d_term = self.kd * (error - self.last_error) / dt
        else:
            d_term = 0.0

        self.last_error = error

        # 计算输出
        output = p_term + i_term + d_term

        # 限制输出范围
        if self.output_limits is not None:
            output = np.clip(output, self.output_limits[0], self.output_limits[1])

        return output

    def reset(self):
        """重置PID控制器状态"""
        self.integral = 0.0
        self.last_error = 0.0
        self.last_time = None


class GlobalNavigator:
    """全局导航控制器 - 实现点到点移动"""

    def __init__(self, model, data):
        """
        初始化全局导航控制器

        参数:
            model: MuJoCo 模型实例
            data: MuJoCo 数据实例
        """
        self.model = model
        self.data = data

        # 获取机器人body ID
        self.robot_body_id = mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_BODY, 'base_plate_layer_1_link'
        )

        # 坐标系说明:
        # 世界坐标系: MuJoCo的全局坐标系,固定不动
        # 机器人坐标系: 原点在机器人底盘中心,z轴指向上方
        #   x轴: 机器人正前方
        #   y轴: 机器人左侧
        #   z轴: 垂直向上

        # PID控制器参数
        # 位置控制 (x, y)
        self.pid_x = PIDController(
            kp=1.5,    # 位置比例增益 (增大以提高响应速度)
            ki=0.05,   # 位置积分增益 (增大以消除稳态误差)
            kd=0.05,   # 位置微分增益 (减小以减少振荡)
            output_limits=(-0.8, 0.8),  # 速度限制 m/s
            integral_limits=(-2.0, 2.0)  # 积分限制,防止饱和
        )

        self.pid_y = PIDController(
            kp=1.5,
            ki=0.05,
            kd=0.05,
            output_limits=(-0.8, 0.8),
            integral_limits=(-2.0, 2.0)
        )

        # 姿态控制 (yaw角)
        self.pid_yaw = PIDController(
            kp=3.0,    # 角度比例增益 (增大以提高响应)
            ki=0.02,   # 角度积分增益
            kd=0.1,    # 角度微分增益
            output_limits=(-2.0, 2.0),  # 角速度限制 rad/s
            integral_limits=(-1.0, 1.0)  # 积分限制
        )

        # 容差阈值
        self.position_tolerance = 0.05  # 位置容差 5cm (放宽以提高成功率)
        self.angle_tolerance = 0.05     # 角度容差 ~3度

        # 目标状态
        self.target_position = None
        self.target_yaw = None
        self.is_navigating = False

    def get_robot_state(self):
        """
        获取机器人当前状态

        返回:
            position: [x, y, z] 世界坐标系位置
            yaw: 机器人朝向角度 (弧度), 0指向x轴正向
        """
        # 获取位置
        position = self.data.xpos[self.robot_body_id].copy()

        # 获取四元数姿态 [w, x, y, z]
        quat = self.data.xquat[self.robot_body_id].copy()

        # 转换为欧拉角
        rotation = R.from_quat(quat)
        euler = rotation.as_euler('xyz', degrees=False)
        yaw = euler[2]  # z轴旋转角

        return position, yaw

    def set_target(self, x, y, z=0, yaw=None):
        """
        设置目标位置和姿态

        参数:
            x: 目标x坐标 (米)
            y: 目标y坐标 (米)
            z: 目标z坐标 (米), 默认0 (平面运动)
            yaw: 目标朝向角度 (弧度), None表示不控制姿态
                0 = 指向+x方向 (机器人前方)
                π/2 = 指向+y方向 (机器人左侧)
                -π/2 = 指向-y方向 (机器人右侧)
                π = 指向-x方向 (机器人后方)
        """
        self.target_position = np.array([x, y, z])
        self.target_yaw = yaw
        self.is_navigating = True

        # 重置PID控制器
        self.pid_x.reset()
        self.pid_y.reset()
        self.pid_yaw.reset()

        yaw_str = f"{yaw:.3f}" if yaw is not None else "不控制"
        print(f"设置目标: 位置=({x:.3f}, {y:.3f}, {z:.3f}), 姿态={yaw_str}", file=sys.stderr)

    def compute_control(self, dt):
        """
        计算控制输出 (在世界坐标系下)

        采用分阶段控制策略：
        1. 先移动到目标位置（不控制姿态）
        2. 位置到达后，再旋转到目标姿态

        返回:
            (vx_world, vy_world, omega) 世界坐标系下的速度
        """
        if not self.is_navigating:
            return 0.0, 0.0, 0.0

        # 获取当前状态
        current_pos, current_yaw = self.get_robot_state()

        # 计算位置误差 (在世界坐标系)
        error_pos = self.target_position[:2] - current_pos[:2]
        error_distance = np.linalg.norm(error_pos)

        # 检查位置是否到达
        position_reached = error_distance < self.position_tolerance

        # 计算姿态误差
        if self.target_yaw is not None:
            # 角度误差归一化到 [-π, π]
            error_yaw = self.target_yaw - current_yaw
            error_yaw = (error_yaw + np.pi) % (2 * np.pi) - np.pi
            angle_reached = abs(error_yaw) < self.angle_tolerance
        else:
            error_yaw = 0.0
            angle_reached = True

        # 如果都到达,停止导航
        if position_reached and angle_reached:
            self.is_navigating = False
            print(f"到达目标! 位置误差={error_distance*100:.2f}cm, 姿态误差={abs(error_yaw)*180/np.pi:.2f}°", file=sys.stderr)
            return 0.0, 0.0, 0.0

        # 分阶段控制策略
        # 阶段1: 位置未到达时，只控制位置，不控制姿态
        if not position_reached:
            # 位置PID控制 (在世界坐标系)
            vx_world = self.pid_x.compute(error_pos[0], dt)
            vy_world = self.pid_y.compute(error_pos[1], dt)
            omega = 0.0  # 移动阶段不旋转
        # 阶段2: 位置到达后，只控制姿态
        else:
            # 位置到达，停止平移
            vx_world = 0.0
            vy_world = 0.0

            # 姿态PID控制
            if self.target_yaw is not None:
                omega = self.pid_yaw.compute(error_yaw, dt)
            else:
                omega = 0.0

        return vx_world, vy_world, omega

    def world_to_robot_velocity(self, vx_world, vy_world, omega):
        """
        将世界坐标系下的速度转换到机器人坐标系

        参数:
            vx_world: 世界坐标系x方向速度
            vy_world: 世界坐标系y方向速度
            omega: 旋转角速度 (机器人坐标系和世界坐标系相同)

        返回:
            (vx_robot, vy_robot, omega_robot) 机器人坐标系下的速度
        """
        # 获取当前朝向
        _, yaw = self.get_robot_state()

        # 旋转矩阵 (从世界坐标系到机器人坐标系)
        cos_yaw = np.cos(-yaw)  # 负号因为是逆变换
        sin_yaw = np.sin(-yaw)

        vx_robot = cos_yaw * vx_world - sin_yaw * vy_world
        vy_robot = sin_yaw * vx_world + cos_yaw * vy_world

        return vx_robot, vy_robot, omega

    def update(self, dt):
        """
        更新导航控制器,计算并返回机器人坐标系下的速度

        参数:
            dt: 时间步长

        返回:
            (vx_robot, vy_robot, omega) 机器人坐标系下的速度
            如果不在导航模式,返回 (0, 0, 0)
        """
        # 计算世界坐标系下的速度
        vx_world, vy_world, omega = self.compute_control(dt)

        if not self.is_navigating:
            return 0.0, 0.0, 0.0

        # 转换到机器人坐标系
        vx_robot, vy_robot, omega_robot = self.world_to_robot_velocity(
            vx_world, vy_world, omega
        )

        return vx_robot, vy_robot, omega_robot

    def is_target_reached(self):
        """检查是否到达目标"""
        return not self.is_navigating

    def stop_navigation(self):
        """停止导航"""
        self.is_navigating = False
        self.target_position = None
        self.target_yaw = None

    def get_navigation_status(self):
        """
        获取导航状态信息

        返回:
            字典包含当前位置、目标位置、误差等信息
        """
        current_pos, current_yaw = self.get_robot_state()

        status = {
            'current_position': current_pos,
            'current_yaw': current_yaw,
            'is_navigating': self.is_navigating
        }

        if self.is_navigating and self.target_position is not None:
            error_pos = self.target_position[:2] - current_pos[:2]
            error_distance = np.linalg.norm(error_pos)

            status['target_position'] = self.target_position
            status['target_yaw'] = self.target_yaw
            status['position_error'] = error_distance
            status['position_error_vector'] = error_pos

            if self.target_yaw is not None:
                error_yaw = self.target_yaw - current_yaw
                error_yaw = (error_yaw + np.pi) % (2 * np.pi) - np.pi
                status['yaw_error'] = error_yaw

        return status
