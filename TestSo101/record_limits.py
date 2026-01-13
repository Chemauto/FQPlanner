#!/usr/bin/env python3
"""记录机械臂关节限位

使用说明:
  1. 运行此脚本
  2. 按 B 开始记录
  3. 手动移动机械臂到各个位置
  4. 按 S 保存限位并退出程序

记录的内容：
  - 每个关节的最小值和最大值
  - 保存到 limits.json
"""

import time
import signal
import sys
import json
from pathlib import Path

# 使用本地 motors 模块
from motors.feetech.feetech import FeetechMotorsBus
from motors import Motor, MotorCalibration, MotorNormMode
import draccus

# 配置
PORT = "/dev/ttyACM0"
ARM_NAME = "SO101-arm"
CALIBRATION_DIR = "./.calibration/"
LIMITS_FILE = "limits.json"

_arm_bus = None
_recording = False
_joint_limits = {
    "shoulder_pan": {"min": float('inf'), "max": float('-inf')},
    "shoulder_lift": {"min": float('inf'), "max": float('-inf')},
    "elbow_flex": {"min": float('inf'), "max": float('-inf')},
    "wrist_flex": {"min": float('inf'), "max": float('-inf')},
    "wrist_roll": {"min": float('inf'), "max": float('-inf')},
    "gripper": {"min": float('inf'), "max": float('-inf')},
}


def cleanup():
    global _arm_bus
    if _arm_bus is not None:
        try:
            _arm_bus.disconnect(disable_torque=False)
            print(f"\n[{ARM_NAME}] 已断开连接")
        except Exception as e:
            print(f"\n[{ARM_NAME}] 断开连接时出错: {e}")
        _arm_bus = None


def signal_handler(signum, frame):
    print(f"\n收到信号 {signum}, 正在清理...")
    cleanup()
    sys.exit(0)


def getch():
    """读取单个字符（非阻塞）"""
    import tty
    import termios
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch


def kbhit():
    """检测是否有按键输入（非阻塞）"""
    import select
    return select.select([sys.stdin], [], [], 0)[0]


def update_limits(present_pos):
    """更新关节数据的限位"""
    for motor_name, value in present_pos.items():
        if motor_name in _joint_limits:
            _joint_limits[motor_name]["min"] = min(_joint_limits[motor_name]["min"], value)
            _joint_limits[motor_name]["max"] = max(_joint_limits[motor_name]["max"], value)


def display_limits():
    """显示当前限位"""
    print("\n" + "="*70)
    print("当前关节限位:")
    print("="*70)
    for motor_name, limits in _joint_limits.items():
        if limits["min"] != float('inf') and limits["max"] != float('-inf'):
            print(f"  {motor_name:15s}: [{limits['min']:7.2f}°, {limits['max']:7.2f}°]")
        else:
            print(f"  {motor_name:15s}: [未记录]")
    print("="*70)


def save_limits():
    """保存限位到文件"""
    # 将未记录的限位设置为默认值
    final_limits = {}
    for motor_name, limits in _joint_limits.items():
        if limits["min"] == float('inf'):
            final_limits[motor_name] = {"min": -180.0, "max": 180.0}
            print(f"  警告: {motor_name} 未记录，使用默认值 [-180, 180]")
        else:
            final_limits[motor_name] = {
                "min": round(limits["min"], 2),
                "max": round(limits["max"], 2)
            }

    with open(LIMITS_FILE, 'w') as f:
        json.dump(final_limits, f, indent=2)

    print(f"\n✓ 限位已保存到 {LIMITS_FILE}")
    return True


def main():
    global _arm_bus, _recording

    # 注册清理函数
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 加载校准文件
    calibration_dir = Path(CALIBRATION_DIR).resolve()
    calibration_fpath = calibration_dir / f"{ARM_NAME}.json"

    try:
        with open(calibration_fpath) as f, draccus.config_type("json"):
            arm_calibration = draccus.load(dict[str, MotorCalibration], f)
        print(f"✓ 已加载校准文件: {calibration_fpath}")
    except FileNotFoundError:
        print(f"✗ 校准文件不存在: {calibration_fpath}")
        sys.exit(1)

    # 配置电机
    norm_mode = MotorNormMode.DEGREES

    # 创建机械臂总线
    arm_bus = FeetechMotorsBus(
        port=PORT,
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
    print(f"\n正在连接 {ARM_NAME} (端口: {PORT})...")
    arm_bus.connect()
    _arm_bus = arm_bus
    print(f"✓ 已连接到 {ARM_NAME}")

    print("\n" + "="*70)
    print("关节限位记录程序")
    print("="*70)
    print(__doc__)
    print("="*70)
    print("\n等待按键... (按 B 开始记录, 按 S 保存, 按 ESC 退出)")

    try:
        # 设置终端为非阻塞模式
        import tty
        import termios
        import fcntl
        import os

        fd = sys.stdin.fileno()
        old_flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, old_flags | os.O_NONBLOCK)

        while True:
            try:
                # 非阻塞读取按键
                ch = sys.stdin.read(1)

                if ch == '\x1b':  # ESC
                    print("\n退出程序...")
                    break

                elif ch.lower() == 'b':
                    _recording = not _recording
                    if _recording:
                        print("\n[开始记录] 正在记录关节位置范围...")
                    else:
                        print("\n[暂停记录]")
                    display_limits()

                elif ch.lower() == 's':
                    if save_limits():
                        display_limits()
                        print("\n保存成功，正在退出...")
                        break
                    else:
                        print("\n保存失败！")

            except IOError:
                # 没有输入时继续
                pass

            # 如果正在记录，读取并更新关芽数据
            if _recording:
                present_pos = arm_bus.sync_read("Present_Position")
                update_limits(present_pos)

                # 每秒显示一次当前状态
                print(f"\r记录中... 关节位置: ", end="")
                for motor_name, value in present_pos.items():
                    print(f"{motor_name[:8]}={value:6.2f}° ", end="", flush=True)

            time.sleep(0.1)

    except KeyboardInterrupt:
        print(f"\n\n用户中断，正在退出...")
    finally:
        cleanup()


if __name__ == "__main__":
    main()
