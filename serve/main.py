"""
main.py - RoboCasa 固定场景仿真主程序
加载 layout=7, style=1 的厨房场景，支持键盘遥操作

使用方式:
    python main.py               
"""

import argparse
import sys
import termios
import numpy as np
from termcolor import colored
from utils.utils import create_scene, init_device, run_interactive, print_fixtures, print_summary

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RoboCasa 固定厨房场景")
    parser.add_argument("--info", action="store_true", help="仅打印场景信息，不进入交互")
    parser.add_argument("--device", type=str, default="keyboard", choices=["keyboard", "spacemouse"], help="控制设备")
    args = parser.parse_args()

    # 1. 创建固定场景
    print(colored("正在从 scene/ 加载厨房场景...", "yellow"))
    env = create_scene(scene_dir="scene", seed=42)

    # 2. 打印场景信息
    env.reset()
    # 以下为打印的场景信息，可以注释
    # print(f"\n共加载 {len(env.fixtures)} 个家具")
    # print_fixtures(env)
    # print_summary(env)

    # 仅查看模式：打印信息后退出
    if args.info:
        env.close()
        print("场景已关闭。")
        sys.exit(0)

    # 3. 初始化控制设备
    device = init_device(env, device_type=args.device)


    # 4. 交互式遥操作
    print(colored("\n场景已加载，进入交互模式。", "green"))
    print("键盘操作说明:")
    print("  W/S/A/D/Q/E  - 移动机械臂（前后左右上下）")
    print("  方向键        - 旋转机械臂")
    print("  Z/X           - 关闭/打开夹爪")
    print("  Q             - 退出当前回合")
    print("  鼠标拖拽      - 旋转相机视角")
    print("  滚轮          - 缩放")
    print()

    while True:
        print(colored("按任意键开始遥操作，Q 退出...", "yellow"))
        run_interactive(env, device)

        # 清除键盘缓冲区
        termios.tcflush(sys.stdin, termios.TCIFLUSH)

        choice = input(colored("继续？(y/n): ", "yellow"))
        if choice.lower() != "y":
            break

    env.close()
    print(colored("场景已关闭。", "yellow"))
