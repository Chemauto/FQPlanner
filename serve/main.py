"""
main.py - RoboCasa 固定场景仿真主程序(robosuite PandaOmron 真机器人)
加载 scene/config 场景,创建 robosuite MyKitchen(真臂 OSC + 真控制器),启动 Flask API。

使用方式:
    python main.py [--no-viewer]
    API 地址: http://localhost:5001
"""

import argparse
import os
import sys
import time

import numpy as np
from termcolor import colored

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.utils import create_scene
from service.server import (
    start_server,
    process_commands,
    try_record_frame,
    get_lock,
)


def _init_belief(env):
    """初始化 belief(机器人的场景记忆/scene graph)。

    按物体真实位置生成 belief(工作点→fixture→物体)= 上帝视角。
    这是有意为之:坐标组负责"进新房间跑一趟,拿到所有家具/物体坐标与 on/inside 关系,东西被
    移动后再看一眼更新关系",所以感知/建图那层可直接假设已知真值,机器人开局就有完整 scene graph。
    """
    from scene import scene_memory
    try:
        state = scene_memory.build_initial_state(env)
        import yaml
        with open(scene_memory.INITIAL_PATH, "w") as f:
            yaml.dump(state, f, allow_unicode=True, default_flow_style=False)
        scene_memory.reset_to_initial()   # belief = 真值(上帝视角)
    except Exception as e:
        print(f"[main] belief 初始化失败(非致命): {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-viewer", action="store_true",
                        help="headless(默认就是无 viewer;此 flag 保留兼容旧启动命令)")
    args = parser.parse_args()

    print(colored("正在从 scene/ 加载 robosuite PandaOmron 厨房场景...", "yellow"))
    env = create_scene(scene_dir="scene", seed=42)
    env.reset()
    _init_belief(env)

    # 调试信息
    print(f"[debug] action_dim = {env.action_dim}")
    print(f"[debug] 底座位置 = {env.get_body_pos('mobilebase0_base').round(3).tolist()}")
    print(f"[debug] 末端位置 = {env.get_body_pos('robot0_right_hand').round(3).tolist()}")
    print(f"[debug] objects = {list(env.obj_body_id.keys())}")

    start_server(env, port=5001)

    print(colored("\n仿真器已就绪(真臂 OSC + PD 导航)。", "green"))
    print("API 地址: http://localhost:5001")
    print("按 Ctrl+C 退出\n")

    # 主循环:process_commands 同步执行命令(nav/grasp/place 内部自己 env.step),
    # 空闲时用零动作步进保持物理活跃(OSC 控制器会 hold 住臂当前位姿)。
    idle_action = np.zeros(env.action_dim)
    idle_action[-1] = -1.0  # 手臂模式,零 delta = 保持当前臂位姿
    try:
        while True:
            with get_lock():
                process_commands(env)
                try_record_frame()
                env.step(idle_action)
            time.sleep(0.002)
    except KeyboardInterrupt:
        pass

    env.close()
    print(colored("场景已关闭。", "yellow"))
