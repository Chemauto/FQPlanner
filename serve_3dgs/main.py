"""
serve_3dgs — MotrixSim + 3DGS simulation backend for FQPlanner.
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CUDA_HOME = os.environ.get("CUDA_HOME", "/usr/local/cuda-12.4")
if os.path.isdir(CUDA_HOME):
    os.environ.setdefault("CUDA_HOME", CUDA_HOME)
    os.environ.setdefault("PATH", os.path.join(CUDA_HOME, "bin") + os.pathsep + os.environ.get("PATH", ""))
    os.environ.setdefault("LD_LIBRARY_PATH", os.path.join(CUDA_HOME, "lib64") + os.pathsep + os.environ.get("LD_LIBRARY_PATH", ""))

LOOP_SLEEP_SEC = 0.01


def main():
    parser = argparse.ArgumentParser(description="serve_3dgs - MotrixSim + 3DGS backend")
    parser.add_argument("--port", type=int,
                        default=int(os.environ.get("SERVE_3DGS_PORT", 5002)))
    parser.add_argument("--gs_assets", type=str,
                        default="/home/fangqi/WorkXCJ/gs_playground/demo/live_demo/assets")
    parser.add_argument("--no-viewer", action="store_true")
    parser.add_argument("--gs_w", type=int, default=640)
    parser.add_argument("--gs_h", type=int, default=480)
    parser.add_argument("--physics_steps_per_loop", type=int, default=10)
    parser.add_argument("--scene", type=str, default="xlerobot",
                        help="Scene: xlerobot (default), franka, or path to MJCF XML")
    args = parser.parse_args()

    from backend.gs_config import GSConfig
    from backend.sim_env import SimEnv
    from service.server import (
        start_server, process_commands, apply_base_velocity, get_lock,
    )

    gs_cfg = GSConfig(assets_dir=args.gs_assets, scene=args.scene)
    print(f"Loading scene: {gs_cfg.scene_xml}")
    env = SimEnv(gs_cfg.scene_xml, gs_cfg)
    print(f"Model loaded: {env.model.num_links} links, {env.model.num_dof_pos} DOFs")

    start_server(env, port=args.port)
    print(f"API: http://localhost:{args.port}")

    try:
        from motrixsim.render import RenderApp

        if not args.no_viewer:
            print("Starting viewer (close window to exit)...")
            with RenderApp() as render:
                render.launch(env.model)
                render.sync(env.data)
                while not render.is_closed:
                    with get_lock():
                        process_commands(env)
                        apply_base_velocity(env)
                    for _ in range(args.physics_steps_per_loop):
                        env.step()
                    env.forward_kinematic()
                    render.sync(env.data)
                    time.sleep(LOOP_SLEEP_SEC)
        else:
            print("Running headless (Ctrl+C to stop)...")
            while True:
                process_commands(env)
                apply_base_velocity(env)
                for _ in range(args.physics_steps_per_loop):
                    env.step()
                time.sleep(LOOP_SLEEP_SEC)
    except ImportError:
        print("RenderApp not available, running headless...")
        while True:
            process_commands(env)
            apply_base_velocity(env)
            for _ in range(args.physics_steps_per_loop):
                env.step()
            time.sleep(LOOP_SLEEP_SEC)
    except KeyboardInterrupt:
        pass

    print("Shutdown.")


if __name__ == "__main__":
    main()
