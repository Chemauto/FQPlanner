"""
三麦克纳姆轮底盘快速参考
"""

# ============================================
# 基本用法
# ============================================

import mujoco
from omni_controller import OmniWheelController

# 初始化
model = mujoco.MjModel.from_xml_path("scene.xml")
data = mujoco.MjData(model)
controller = OmniWheelController(model, data)

# ============================================
# 控制函数原型
# ============================================

# 方法1: 速度大小 + 方向 + 旋转 (推荐)
controller.set_velocity(linear_speed, vx, vy, omega=0)
# 参数说明:
#   linear_speed: 速度大小 (m/s), 例如 0.5
#   vx: x方向分量 (-1到1), 1=向前, -1=向后
#   vy: y方向分量 (-1到1), 1=向左, -1=向右
#   omega: 旋转角速度 (rad/s), 正值=逆时针, 负值=顺时针, 默认=0

# 方法2: 直接指定速度分量
controller.set_velocity_raw(vx, vy, omega=0)
# 参数说明:
#   vx: x方向速度 (m/s), 例如 0.3
#   vy: y方向速度 (m/s), 例如 0.2
#   omega: 旋转角速度 (rad/s), 例如 1.0

# ============================================
# 常用运动示例
# ============================================

# 1. 前进 (速度0.5 m/s)
controller.set_velocity(linear_speed=0.5, vx=1, vy=0, omega=0)

# 2. 后退 (速度0.5 m/s)
controller.set_velocity(linear_speed=0.5, vx=-1, vy=0, omega=0)

# 3. 左移 (速度0.3 m/s)
controller.set_velocity(linear_speed=0.3, vx=0, vy=1, omega=0)

# 4. 右移 (速度0.3 m/s)
controller.set_velocity(linear_speed=0.3, vx=0, vy=-1, omega=0)

# 5. 右前斜向45度 (速度0.4 m/s)
controller.set_velocity(linear_speed=0.4, vx=1, vy=-1, omega=0)

# 6. 左前斜向45度 (速度0.4 m/s)
controller.set_velocity(linear_speed=0.4, vx=1, vy=1, omega=0)

# 7. 原地逆时针旋转 (1 rad/s)
controller.set_velocity(linear_speed=0, vx=0, vy=0, omega=1)

# 8. 原地顺时针旋转 (1 rad/s)
controller.set_velocity(linear_speed=0, vx=0, vy=0, omega=-1)

# 9. 前进同时旋转 (前进0.3 m/s, 逆时针旋转0.5 rad/s)
controller.set_velocity(linear_speed=0.3, vx=1, vy=0, omega=0.5)

# 10. 后退同时旋转 (后退0.3 m/s, 顺时针旋转0.5 rad/s)
controller.set_velocity(linear_speed=0.3, vx=-1, vy=0, omega=-0.5)

# ============================================
# 仿真循环
# ============================================

while True:
    # 设置速度
    controller.set_velocity(linear_speed=0.5, vx=1, vy=0, omega=0)

    # 应用控制
    controller.apply_control()

    # 仿真步进
    mujoco.mj_step(model, data)

# ============================================
# 其他实用函数
# ============================================

# 停止机器人
controller.stop()

# 获取轮子速度 (返回: left, right, back)
left, right, back = controller.get_wheel_velocities()

# 获取机器人位置 [x, y, z]
position = controller.get_robot_position()

# 获取机器人姿态 [w, x, y, z] 四元数
orientation = controller.get_robot_orientation()

# ============================================
# 旋转角度计算示例
# ============================================

# 旋转指定角度
import time

def rotate_to_angle(controller, angle_rad, omega=1):
    """
    控制机器人旋转指定角度

    参数:
        controller: 控制器实例
        angle_rad: 目标旋转角度 (弧度), 正值=逆时针, 负值=顺时针
        omega: 旋转角速度 (rad/s), 默认1
    """
    # 计算需要的时间
    duration = abs(angle_rad) / omega
    start_time = time.time()

    # 执行旋转
    while time.time() - start_time < duration:
        controller.set_velocity(linear_speed=0, vx=0, vy=0, omega=omega if angle_rad > 0 else -omega)
        controller.apply_control()
        mujoco.mj_step(model, data)

    # 停止
    controller.stop()
    controller.apply_control()

# 使用示例: 逆时针旋转90度 (π/2弧度)
rotate_to_angle(controller, angle_rad=3.14159/2, omega=1)

# 使用示例: 顺时针旋转45度 (π/4弧度)
rotate_to_angle(controller, angle_rad=-3.14159/4, omega=0.5)

# ============================================
# 限制说明
# ============================================

# - 执行器速度范围: -3.14 到 3.14 rad/s
# - 轮子半径: 0.051 m
# - 轮子到中心距离: 0.09 m
# - 推荐最大线速度: 约 0.16 m/s (避免执行器饱和)
# - 推荐最大旋转速度: 约 3.0 rad/s
