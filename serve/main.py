"""
main.py - RoboCasa 固定场景仿真主程序
加载场景，启动 Flask API 服务，通过 Web UI 控制机器人

使用方式:
    python main.py
    然后打开 service/web.py 或浏览器访问 http://localhost:5001
"""

import time
import numpy as np
from termcolor import colored
from utils.utils import create_scene
from service.server import start_server, process_commands

if __name__ == "__main__":
    # 1. 创建固定场景
    print(colored("正在从 scene/ 加载厨房场景...", "yellow"))
    env = create_scene(scene_dir="scene", seed=42)

    # 2. 初始化场景
    env.reset()

    # 3. 调试信息
    base_id = env.sim.model.body_name2id("mobilebase0_base")
    ee_id = env.sim.model.body_name2id("robot0_right_hand")
    print(f"[debug] action_dim = {env.action_dim}")
    print(f"[debug] 底座位置 = {env.sim.data.body_xpos[base_id].round(3).tolist()}")
    print(f"[debug] 末端位置 = {env.sim.data.body_xpos[ee_id].round(3).tolist()}")

    # 4. 启动 Flask API 服务
    start_server(env, port=5001)

    print(colored("\n仿真器已就绪。", "green"))
    print("API 地址: http://localhost:5001")
    print("按 Ctrl+C 退出\n")

    # 5. 主循环
    idle_action = np.zeros(env.action_dim)
    try:
        while True:
            process_commands(env)
            env.step(idle_action)
            time.sleep(0.01)
    except KeyboardInterrupt:
        pass

    env.close()
    print(colored("场景已关闭。", "yellow"))
