"""
MuJoCo仿真底盘测试脚本
测试MuJoCo仿真环境中的三麦克纳姆轮底盘控制
"""

import os
import sys

# 添加controller路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../controller')))

import mujoco
import mujoco.viewer
import time
import numpy as np
from omni_controller import OmniWheelController
from global_navigator import GlobalNavigator


def get_model_path():
    """获取模型路径"""
    script_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    return os.path.join(script_dir, 'model/assets/scene.xml')


def test_kinematics():
    """测试基本运动学"""
    print("\n" + "="*60)
    print("MuJoCo三麦克纳姆轮运动学测试")
    print("="*60)
    print("\n请测试以下运动并观察是否有角度偏转:")
    print("1. 前进/后退 - 应该直线运动,不偏转")
    print("2. 左移/右移 - 应该直线运动,不偏转")
    print("3. 原地旋转 - 应该在原地旋转,不位移")
    print("="*60 + "\n")

    model_path = get_model_path()
    model = mujoco.MjModel.from_xml_path(model_path)
    data = mujoco.MjData(model)
    controller = OmniWheelController(model, data)

    with mujoco.viewer.launch_passive(model, data) as viewer:
        while viewer.is_running():
            try:
                print("\n选择测试:")
                print("  1 - 前进测试 (vx=1, vy=0)")
                print("  2 - 后退测试 (vx=-1, vy=0)")
                print("  3 - 左移测试 (vx=0, vy=1)")
                print("  4 - 右移测试 (vx=0, vy=-1)")
                print("  5 - 原地旋转测试 (omega=1)")
                print("  6 - 退出")

                choice = input("\n请选择 (1-6): ").strip()

                if choice == '6':
                    break

                duration = 2.0

                if choice == '1':
                    print("\n[前进测试] 机器人应该向前直线运动...")
                    controller.set_velocity(linear_speed=0.3, vx=1, vy=0, omega=0)
                elif choice == '2':
                    print("\n[后退测试] 机器人应该向后直线运动...")
                    controller.set_velocity(linear_speed=0.3, vx=-1, vy=0, omega=0)
                elif choice == '3':
                    print("\n[左移测试] 机器人应该向左直线运动(不偏转)...")
                    controller.set_velocity(linear_speed=0.3, vx=0, vy=1, omega=0)
                elif choice == '4':
                    print("\n[右移测试] 机器人应该向右直线运动(不偏转)...")
                    controller.set_velocity(linear_speed=0.3, vx=0, vy=-1, omega=0)
                elif choice == '5':
                    print("\n[旋转测试] 机器人应该在原地旋转(不位移)...")
                    controller.set_velocity(linear_speed=0, vx=0, vy=0, omega=0.5)
                else:
                    print("无效选择!")
                    continue

                # 执行测试
                start_time = time.time()
                start_pos = controller.get_robot_position().copy()

                while time.time() - start_time < duration and viewer.is_running():
                    controller.apply_control()
                    mujoco.mj_step(model, data)

                    elapsed = time.time() - start_time
                    pos = controller.get_robot_position()
                    print(f"\r时间: {elapsed:.1f}s/{duration}s | 位置: [{pos[0]:.3f}, {pos[1]:.3f}]", end="")

                    viewer.sync()

                # 停止
                controller.stop()
                controller.apply_control()

                # 显示结果
                end_pos = controller.get_robot_position()
                displacement = end_pos - start_pos

                print(f"\n\n测试完成!")
                print(f"起始位置: [{start_pos[0]:.3f}, {start_pos[1]:.3f}]")
                print(f"结束位置: [{end_pos[0]:.3f}, {end_pos[1]:.3f}]")
                print(f"位移: [{displacement[0]:.3f}, {displacement[1]:.3f}]")

                # 检查是否有偏转
                if choice in ['1', '2']:
                    if abs(displacement[1]) > 0.05:
                        print("⚠️  警告: 检测到侧向偏转!")
                elif choice in ['3', '4']:
                    if abs(displacement[0]) > 0.05:
                        print("⚠️  警告: 检测到前后偏转!")
                elif choice == '5':
                    if np.linalg.norm(displacement[:2]) > 0.05:
                        print("⚠️  警告: 旋转时有位移!")

            except KeyboardInterrupt:
                print("\n\n测试中断")
                controller.stop()
                controller.apply_control()
                break
            except Exception as e:
                print(f"\n错误: {e}")
                import traceback
                traceback.print_exc()

    print("\n测试结束!")


def test_navigation():
    """测试全局导航"""
    print("\n" + "="*60)
    print("全局导航测试")
    print("="*60)

    model_path = get_model_path()
    model = mujoco.MjModel.from_xml_path(model_path)
    data = mujoco.MjData(model)

    omni_controller = OmniWheelController(model, data)
    navigator = GlobalNavigator(model, data)

    print("\n选择测试模式:")
    print("  1 - 单点移动")
    print("  2 - 多点移动(方形路径)")
    print("  3 - 带姿态控制")

    choice = input("\n请选择 (1-3): ").strip()

    if choice == '1':
        # 单点移动
        print("\n测试: 移动到 (0.5, 0.5)")
        navigator.set_target(x=0.5, y=0.5, yaw=None)

        with mujoco.viewer.launch_passive(model, data) as viewer:
            start_time = time.time()
            while viewer.is_running() and time.time() - start_time < 20:
                vx_robot, vy_robot, omega = navigator.update(model.opt.timestep)
                omni_controller.set_velocity_raw(vx_robot, vy_robot, omega)
                omni_controller.apply_control()
                mujoco.mj_step(model, data)
                viewer.sync()

                if int(time.time() * 10) % 10 == 0:
                    status = navigator.get_navigation_status()
                    if navigator.is_navigating:
                        print(f"位置误差: {status['position_error']*100:.2f}cm")

                if not navigator.is_navigating:
                    print("到达目标!")
                    time.sleep(1)
                    break

    elif choice == '2':
        # 多点移动
        waypoints = [
            (0.5, 0.0, None),
            (0.5, 0.5, None),
            (0.0, 0.5, None),
            (0.0, 0.0, None),
        ]

        current_waypoint = 0
        waypoint_set = False

        print(f"\n将访问 {len(waypoints)} 个目标点")

        with mujoco.viewer.launch_passive(model, data) as viewer:
            while viewer.is_running():
                if not waypoint_set and current_waypoint < len(waypoints):
                    x, y, yaw = waypoints[current_waypoint]
                    navigator.set_target(x, y, 0, yaw)
                    waypoint_set = True
                    print(f"\n前往目标点 {current_waypoint + 1}/{len(waypoints)}: ({x}, {y})")

                vx_robot, vy_robot, omega = navigator.update(model.opt.timestep)
                omni_controller.set_velocity_raw(vx_robot, vy_robot, omega)
                omni_controller.apply_control()
                mujoco.mj_step(model, data)
                viewer.sync()

                if waypoint_set and not navigator.is_navigating:
                    waypoint_set = False
                    current_waypoint += 1
                    print(f"到达目标点 {current_waypoint}!")

                    if current_waypoint >= len(waypoints):
                        print("\n所有目标点已访问完成!")
                        time.sleep(1)
                        break

    elif choice == '3':
        # 带姿态控制
        waypoints = [
            (0.5, 0.0, 0.0),
            (0.5, 0.5, np.pi/2),
            (0.0, 0.5, np.pi),
            (0.0, 0.0, -np.pi/2),
        ]

        current_waypoint = 0
        waypoint_set = False

        print(f"\n将访问 {len(waypoints)} 个目标点 (带姿态控制)")

        with mujoco.viewer.launch_passive(model, data) as viewer:
            while viewer.is_running():
                if not waypoint_set and current_waypoint < len(waypoints):
                    x, y, yaw = waypoints[current_waypoint]
                    navigator.set_target(x, y, 0, yaw)
                    waypoint_set = True
                    yaw_deg = yaw * 180 / np.pi
                    print(f"\n前往目标点 {current_waypoint + 1}/{len(waypoints)}: "
                          f"位置({x}, {y}), 姿态{yaw_deg:.1f}°")

                vx_robot, vy_robot, omega = navigator.update(model.opt.timestep)
                omni_controller.set_velocity_raw(vx_robot, vy_robot, omega)
                omni_controller.apply_control()
                mujoco.mj_step(model, data)
                viewer.sync()

                if waypoint_set and not navigator.is_navigating:
                    waypoint_set = False
                    current_waypoint += 1
                    print(f"到达目标点 {current_waypoint}!")

                    if current_waypoint >= len(waypoints):
                        print("\n所有目标点已访问完成!")
                        time.sleep(1)
                        break


def main():
    """主函数"""
    print("="*60)
    print("MuJoCo仿真底盘测试程序")
    print("="*60)

    print("\n请选择测试模式:")
    print("  1 - 运动学测试")
    print("  2 - 导航测试")

    try:
        choice = input("\n请输入选择 (1-2): ").strip()

        if choice == '1':
            test_kinematics()
        elif choice == '2':
            test_navigation()
        else:
            print("无效的选择!")
    except KeyboardInterrupt:
        print("\n\n程序已退出")


if __name__ == "__main__":
    main()
