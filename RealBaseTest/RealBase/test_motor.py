#!/usr/bin/env python3
"""
3全向轮底盘测试程序
提供交互式菜单测试各种运动模式
"""

import time
from motor_controller import OmniWheelController


def test_movement(controller):
    """测试基本运动"""
    print("\n" + "="*60)
    print("三全向轮运动学测试")
    print("="*60)
    print("\n请测试以下运动并观察是否有角度偏转:")
    print("1. 前进/后退 - 应该直线运动,不偏转")
    print("2. 左移/右移 - 应该直线运动,不偏转")
    print("3. 原地旋转 - 应该在原地旋转,不位移")
    print("="*60 + "\n")

    while True:
        try:
            print("\n选择测试:")
            print("  1 - 前进测试 (vx=1, vy=0)")
            print("  2 - 后退测试 (vx=-1, vy=0)")
            print("  3 - 左移测试 (vx=0, vy=1)")
            print("  4 - 右移测试 (vx=0, vy=-1)")
            print("  5 - 斜向测试 (vx=1, vy=1)")
            print("  6 - 原地旋转测试 (omega=1)")
            print("  7 - 前进+旋转测试 (vx=1, omega=0.5)")
            print("  8 - 单轮控制测试")
            print("  9 - 返回主菜单")

            choice = input("\n请选择 (1-9): ").strip()

            if choice == '9':
                break

            duration = 2.0  # 每个测试2秒

            if choice == '1':
                print("\n[前进测试] 机器人应该向前直线运动...")
                controller.set_velocity(linear_speed=0.2, vx=1, vy=0, omega=0)
            elif choice == '2':
                print("\n[后退测试] 机器人应该向后直线运动...")
                controller.set_velocity(linear_speed=0.2, vx=-1, vy=0, omega=0)
            elif choice == '3':
                print("\n[左移测试] 机器人应该向左直线运动...")
                controller.set_velocity(linear_speed=0.2, vx=0, vy=1, omega=0)
            elif choice == '4':
                print("\n[右移测试] 机器人应该向右直线运动...")
                controller.set_velocity(linear_speed=0.2, vx=0, vy=-1, omega=0)
            elif choice == '5':
                print("\n[斜向测试] 机器人应该向右前方斜向运动...")
                controller.set_velocity(linear_speed=0.2, vx=1, vy=1, omega=0)
            elif choice == '6':
                print("\n[旋转测试] 机器人应该在原地旋转...")
                controller.set_velocity(linear_speed=0, vx=0, vy=0, omega=0.5)
            elif choice == '7':
                print("\n[前进+旋转测试] 机器人应该边前进边旋转...")
                controller.set_velocity(linear_speed=0.2, vx=1, vy=0, omega=0.5)
            elif choice == '8':
                test_single_wheel(controller)
                continue
            else:
                print("无效选择!")
                continue

            # 执行测试
            print(f"\n执行中... ({duration}秒)")
            print("按 Ctrl+C 可提前停止")

            start_time = time.time()
            wheel_vels_start = controller.get_wheel_velocities().copy()

            while time.time() - start_time < duration:
                # 打印进度和轮子速度
                elapsed = time.time() - start_time
                wheel_vels = controller.get_wheel_velocities()

                print(f"\r时间: {elapsed:.1f}s/{duration}s | "
                      f"轮子速度: [{wheel_vels[0]:.2f}, {wheel_vels[1]:.2f}, {wheel_vels[2]:.2f}] rad/s",
                      end="")

                time.sleep(0.1)

            # 停止
            controller.stop()

            # 显示结果
            print(f"\n\n测试完成!")
            print(f"起始轮子速度: [{wheel_vels_start[0]:.2f}, {wheel_vels_start[1]:.2f}, {wheel_vels_start[2]:.2f}] rad/s")
            print(f"结束轮子速度: [{controller.get_wheel_velocities()[0]:.2f}, "
                  f"{controller.get_wheel_velocities()[1]:.2f}, "
                  f"{controller.get_wheel_velocities()[2]:.2f}] rad/s")

        except KeyboardInterrupt:
            print("\n\n测试中断")
            controller.stop()
            break
        except Exception as e:
            print(f"\n错误: {e}")
            import traceback
            traceback.print_exc()


def test_single_wheel(controller):
    """测试单个轮子控制"""
    print("\n" + "="*60)
    print("单轮控制测试")
    print("="*60 + "\n")

    while True:
        try:
            print("\n选择要控制的轮子:")
            print(f"  1 - 轮子1 (ID={controller.WHEEL_IDS[0]})")
            print(f"  2 - 轮子2 (ID={controller.WHEEL_IDS[1]})")
            print(f"  3 - 轮子3 (ID={controller.WHEEL_IDS[2]})")
            print("  4 - 返回")

            choice = input("\n请选择 (1-4): ").strip()

            if choice == '4':
                break

            if choice not in ['1', '2', '3']:
                print("无效选择!")
                continue

            wheel_idx = int(choice) - 1
            wheel_id = controller.WHEEL_IDS[wheel_idx]

            # 选择方向
            direction_choice = input("方向 (1=正转, -1=反转): ").strip()
            try:
                direction = int(direction_choice)
                if direction not in [1, -1]:
                    print("方向必须是1或-1!")
                    continue
            except ValueError:
                print("无效的方向!")
                continue

            # 选择速度
            speed_choice = input("速度 (0-100): ").strip()
            try:
                speed = int(speed_choice)
                if not 0 <= speed <= 100:
                    print("速度必须在0-100之间!")
                    continue
            except ValueError:
                print("无效的速度!")
                continue

            # 执行控制
            print(f"\n控制轮子{wheel_id} {direction}方向, 速度{speed}%...")
            result = controller.control_wheel(wheel_id, direction, speed)
            print(f"结果: {result['message']}")

            # 持续时间
            duration = float(input("持续时间(秒,默认2): ").strip() or "2")
            time.sleep(duration)

            # 停止
            controller.stop_wheel(wheel_id)
            print(f"轮子{wheel_id}已停止")

        except KeyboardInterrupt:
            print("\n\n测试中断")
            controller.stop()
            break
        except Exception as e:
            print(f"\n错误: {e}")
            import traceback
            traceback.print_exc()


def main():
    """主函数"""
    # 创建底盘控制器
    controller = OmniWheelController(port="/dev/ttyACM0")

    print("="*60)
    print("3全向轮底盘测试程序")
    print("="*60)
    print(f"\n电机ID配置: {controller.WHEEL_IDS}")
    print(f"轮子半径: {controller.wheel_radius}m")
    print(f"机器人半径: {controller.robot_radius}m")
    print(f"最大原始速度: {controller.max_raw}")
    print(f"速度缩放因子: {controller.velocity_scale} (所有速度将乘以该值)")

    # 连接
    print("\n正在连接底盘...")
    if not controller.connect():
        print("\n连接失败,请检查:")
        print("  - 串口端口是否正确")
        print("  - 电机是否已连接")
        print(f"  - 电机ID是否正确({controller.WHEEL_IDS})")
        return

    try:
        while True:
            print("\n" + "="*60)
            print("主菜单")
            print("="*60)
            print("  1 - 运动学测试 (前进/后退/横移/旋转)")
            print("  2 - 单轮控制测试")
            print("  3 - 退出程序")

            choice = input("\n请选择 (1-3): ").strip()

            if choice == '1':
                test_movement(controller)
            elif choice == '2':
                test_single_wheel(controller)
            elif choice == '3':
                break
            else:
                print("无效选择!")

    except KeyboardInterrupt:
        print("\n\n程序被中断")

    finally:
        # 断开连接
        print("\n正在断开连接...")
        controller.disconnect()
        print("程序结束")


if __name__ == "__main__":
    main()
