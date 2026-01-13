#!/usr/bin/env python3
"""简单键盘控制机械臂

控制说明:
  q/w: 肩部旋转 (shoulder_pan)  +/- 5度
  a/s: 肩部抬起 (shoulder_lift)  +/- 5度
  z/x: 肘部弯曲 (elbow_flex)     +/- 5度
  e/r: 手腕弯曲 (wrist_flex)     +/- 5度
  d/f: 手腕旋转 (wrist_roll)     +/- 5度
  c/v: 夹爪     (gripper)       +/- 10
  空格: 复位到零位
  ESC: 退出

按住 Shift 可以加速 (步进 x2)

安全功能:
  - 自动加载 limits.json 限位文件
  - 超出限位时停止运动并警告
"""

import time
import signal
import sys
import tty
import termios
import json
from pathlib import Path

# 使用本地 motors 模块
from motors.feetech.feetech import FeetechMotorsBus, OperatingMode
from motors import Motor, MotorCalibration, MotorNormMode
import draccus

# 配置
PORT = "/dev/ttyACM0"
ARM_NAME = "SO101-arm"
CALIBRATION_DIR = "./.calibration/"
LIMITS_FILE = "limits.json"

# 关节名称映射（索引 -> 名称）
JOINT_NAMES = [
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
]

_arm_bus = None


def cleanup():
    global _arm_bus
    if _arm_bus is not None:
        try:
            # 禁用扭矩，使机械臂松弛
            print(f"\n[{ARM_NAME}] 正在禁用扭矩...")
            _arm_bus.disable_torque()
            time.sleep(0.5)  # 等待扭矩完全禁用

            _arm_bus.disconnect(disable_torque=False)
            print(f"[{ARM_NAME}] 已断开连接，机械臂现在可以自由移动")
        except Exception as e:
            print(f"\n[{ARM_NAME}] 断开连接时出错: {e}")
        _arm_bus = None


def signal_handler(signum, frame):
    print(f"\n收到信号 {signum}, 正在清理...")
    cleanup()
    # 恢复终端设置
    try:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, _old_settings)
    except:
        pass
    sys.exit(0)


def getch():
    """读取单个字符（非阻塞）"""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    global _old_settings
    _old_settings = old_settings
    try:
        tty.setcbreak(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch


def load_limits():
    """加载限位文件"""
    limits_path = Path(LIMITS_FILE)
    if not limits_path.exists():
        print(f"⚠ 警告: 限位文件 {LIMITS_FILE} 不存在")
        print(f"  运行 'python record_limits.py' 来创建限位文件")
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
        print(f"✓ 已加载限位文件: {LIMITS_FILE}")
        for joint, limit in limits.items():
            print(f"  {joint:15s}: [{limit['min']:7.2f}°, {limit['max']:7.2f}°]")
        return limits
    except Exception as e:
        print(f"✗ 加载限位文件失败: {e}")
        return None


def check_limits(new_pos, limits):
    """检查新位置是否超出限位

    返回: (is_safe, clipped_pos, warning_msg)
    """
    clipped = []
    warnings = []

    for i, pos in enumerate(new_pos):
        joint_name = JOINT_NAMES[i]
        if joint_name in limits:
            limit = limits[joint_name]
            if pos < limit['min']:
                clipped.append(limit['min'])
                warnings.append(f"{joint_name} 达到最小限位 {limit['min']:.2f}°")
            elif pos > limit['max']:
                clipped.append(limit['max'])
                warnings.append(f"{joint_name} 达到最大限位 {limit['max']:.2f}°")
            else:
                clipped.append(pos)
        else:
            clipped.append(pos)

    is_safe = len(warnings) == 0
    return is_safe, clipped, warnings


def main():
    global _arm_bus

    # 注册清理函数
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 加载限位文件
    print("\n正在加载限位文件...")
    limits = load_limits()
    if limits is None:
        print("✗ 限位加载失败，无法启动")
        sys.exit(1)

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

    # 配置为 follower 模式（允许位置控制）
    print("配置机械臂为位置控制模式...")
    with arm_bus.torque_disabled():
        arm_bus.configure_motors()
        for motor in arm_bus.motors:
            arm_bus.write("Operating_Mode", motor, OperatingMode.POSITION.value)
            arm_bus.write("P_Coefficient", motor, 16)
            arm_bus.write("I_Coefficient", motor, 0)
            arm_bus.write("D_Coefficient", motor, 32)

    # 读取当前位置作为初始值
    print("读取初始位置...")
    present_pos = arm_bus.sync_read("Present_Position")
    current_pos = [val for _, val in present_pos.items()]

    print("\n" + "="*70)
    print("键盘控制已启动")
    print("="*70)
    print(__doc__)
    print("="*70)
    print(f"\n当前位置: {current_pos}\n")

    try:
        while True:
            # 读取按键
            ch = getch()

            # 检查 Shift 键（加速模式）
            speed_multiplier = 2.0

            # 处理按键
            new_pos = current_pos.copy()

            if ch == '\x1b':  # ESC
                print("\n退出程序...")
                break

            elif ch == ' ':  # 空格复位
                new_pos = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
                print("\n[复位] 回到零位")

            elif ch == 'q':
                new_pos[0] += 5.0
                print(f"[shoulder_pan] +5°")
            elif ch == 'w':
                new_pos[0] -= 5.0
                print(f"[shoulder_pan] -5°")

            elif ch == 'a':
                new_pos[1] += 5.0
                print(f"[shoulder_lift] +5°")
            elif ch == 's':
                new_pos[1] -= 5.0
                print(f"[shoulder_lift] -5°")

            elif ch == 'z':
                new_pos[2] += 5.0
                print(f"[elbow_flex] +5°")
            elif ch == 'x':
                new_pos[2] -= 5.0
                print(f"[elbow_flex] -5°")

            elif ch == 'e':
                new_pos[3] += 5.0
                print(f"[wrist_flex] +5°")
            elif ch == 'r':
                new_pos[3] -= 5.0
                print(f"[wrist_flex] -5°")

            elif ch == 'd':
                new_pos[4] += 5.0
                print(f"[wrist_roll] +5°")
            elif ch == 'f':
                new_pos[4] -= 5.0
                print(f"[wrist_roll] -5°")

            elif ch == 'c':
                new_pos[5] = min(100, new_pos[5] + 10)
                print(f"[gripper] +10")
            elif ch == 'v':
                new_pos[5] = max(0, new_pos[5] - 10)
                print(f"[gripper] -10")

            else:
                continue  # 未知按键，跳过

            # 检查限位
            is_safe, clipped_pos, warnings = check_limits(new_pos, limits)

            if not is_safe:
                # 显示警告
                print(f"\n⚠ 限位警告:")
                for warning in warnings:
                    print(f"  - {warning}")
                # 使用限制后的位置
                new_pos = clipped_pos

            # 发送新位置到机械臂
            goal_pos = {
                key: new_pos[motor.id - 1]
                for key, motor in arm_bus.motors.items()
            }
            arm_bus.sync_write("Goal_Position", goal_pos)
            current_pos = new_pos

            # 显示当前位置
            print(f"  当前位置: {current_pos}")

    except KeyboardInterrupt:
        print(f"\n\n用户中断，正在退出...")
    finally:
        cleanup()


if __name__ == "__main__":
    main()
