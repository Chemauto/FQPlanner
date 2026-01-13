#!/usr/bin/env python3
"""简单读取机械臂关节数据并实时打印"""

import time
import signal
import sys
from pathlib import Path

# 使用本地 motors 模块
from motors.feetech.feetech import FeetechMotorsBus, OperatingMode
from motors import Motor, MotorCalibration, MotorNormMode
import draccus

# 配置
PORT = "/dev/ttyACM0"
ARM_NAME = "SO101-arm"
CALIBRATION_DIR = "./.calibration/"
USE_DEGRESES = True

_arm_bus = None


def cleanup():
    global _arm_bus
    if _arm_bus is not None:
        try:
            _arm_bus.disconnect(disable_torque=False)  # 读取时不需要禁用扭矩
            print(f"\n[{ARM_NAME}] 已断开连接")
        except Exception as e:
            print(f"\n[{ARM_NAME}] 断开连接时出错: {e}")
        _arm_bus = None


def signal_handler(signum, frame):
    print(f"\n收到信号 {signum}, 正在清理...")
    cleanup()
    sys.exit(0)


def main():
    global _arm_bus

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
        print(f"  请确保校准文件存在，或先运行校准程序")
        sys.exit(1)

    # 配置电机（使用角度模式）
    norm_mode = MotorNormMode.DEGREES if USE_DEGRESES else MotorNormMode.RANGE_M100_100

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

    print("\n" + "="*60)
    print("关节数据实时显示 (按 Ctrl+C 退出)")
    print("="*60)

    try:
        while True:
            # 读取当前位置
            present_pos = arm_bus.sync_read("Present_Position")

            # 清屏并打印（使用 \r 来刷新同一行）
            joint_values = []
            print("\r" + " " * 100 + "\r", end="", flush=False)

            output = []
            output.append(f"[{ARM_NAME}] 关节角度:")
            for motor_name, value in present_pos.items():
                joint_values.append(value)
                output.append(f"  {motor_name:15s}: {value:7.2f}°")

            print("\n".join(output), end="", flush=True)

            # 打印完整列表格式
            print(f"\n完整列表: {joint_values}")

            time.sleep(0.1)  # 10Hz 刷新率

    except KeyboardInterrupt:
        print(f"\n\n用户中断，正在退出...")
    finally:
        cleanup()


if __name__ == "__main__":
    main()
