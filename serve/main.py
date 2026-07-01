"""
main.py - 纯 MuJoCo 固定场景仿真主程序
加载原 scene/config 场景，使用本地 XLeRobot MuJoCo 模型，启动 Flask API 服务。

使用方式:
    python main.py
    API 地址: http://localhost:5001
"""

import argparse
import os
import time
from termcolor import colored
from backend.mujoco_backend import MujocoKitchenEnv
from service.server import (
    start_server,
    process_commands,
    try_record_frame,
    get_lock,
    get_base_action,
    apply_base_velocity,
    has_active_base_command,
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--no-viewer",
        action="store_true",
        help="只启动 API 和仿真循环，不打开 MuJoCo viewer",
    )
    args = parser.parse_args()

    # 1. 创建固定场景
    print(colored("正在从 scene/ 加载 MuJoCo 厨房场景...", "yellow"))
    env = MujocoKitchenEnv(scene_dir="scene", seed=42)

    # 2. 初始化场景
    env.reset()
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from scene.scene_memory import reset_to_initial
    reset_to_initial()

    # 3. 调试信息
    print(f"[debug] action_dim = {env.action_dim}")
    print(f"[debug] scene_xml = {env.scene_xml}")
    print(f"[debug] 底座位置 = {env.get_body_pos('chassis').round(3).tolist()}")
    print(f"[debug] 末端位置 = {env.virtual_ee_pos.round(3).tolist()}")

    # 4. 启动 Flask API 服务
    start_server(env, port=5001)

    print(colored("\n仿真器已就绪。", "green"))
    print("API 地址: http://localhost:5001")
    if args.no_viewer:
        print("MuJoCo viewer: 已关闭 (--no-viewer)")
    else:
        print("MuJoCo viewer: 正在打开窗口")
    print("按 Ctrl+C 退出\n")

    # 5. 主循环
    viewer = None
    try:
        if not args.no_viewer:
            import mujoco.viewer
            viewer = mujoco.viewer.launch_passive(env.model, env.data)
            viewer.cam.distance = 7.5
            viewer.cam.azimuth = 135
            viewer.cam.elevation = -35
            viewer.cam.lookat[:] = [3.2, -2.15, 0.8]
            viewer.opt.geomgroup[:] = 0
            viewer.opt.geomgroup[0] = 1
            viewer.opt.geomgroup[1] = 1
            viewer.opt.geomgroup[2] = 1

        while True:
            with get_lock():
                process_commands(env)
                try_record_frame()
                # 没有活跃底盘命令时，才用 cmd_vel 驱动
                # cmd_vel 过期时 get_base_action() 返回 None，不写 ctrl
                # 这样 MuJoCo viewer 的手动滑块可以正常工作
                if not has_active_base_command():
                    if not apply_base_velocity(env):
                        base = get_base_action()
                        if base is not None:
                            env.data.ctrl[0] = base[0]
                            env.data.ctrl[1] = base[1]
                env.step()
            if viewer is not None:
                if not viewer.is_running():
                    break
                viewer.sync()
                time.sleep(0.01)   # 有 viewer:节流到 ~100Hz 便于人眼观看
            else:
                time.sleep(0.0005)  # headless:几乎全速步进(nav 快 ~10x),仅让出 GIL 给 Flask 线程
    except KeyboardInterrupt:
        pass
    finally:
        if viewer is not None:
            viewer.close()

    env.close()
    print(colored("场景已关闭。", "yellow"))
