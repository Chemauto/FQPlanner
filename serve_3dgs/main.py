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
    parser.add_argument("--gs_assets", type=str, default="")
    parser.add_argument("--robot_gs_dir", type=str, default="")
    parser.add_argument("--scene_config", type=str,
                        default=os.environ.get("SERVE_3DGS_SCENE_CONFIG", ""))
    parser.add_argument("--no-viewer", action="store_true")
    parser.add_argument("--gs_w", type=int, default=320)
    parser.add_argument("--gs_h", type=int, default=240)
    parser.add_argument("--viewer_gs_fps", type=float, default=5.0)
    parser.add_argument("--viewer_cameras", type=str,
                        default=os.environ.get("SERVE_3DGS_VIEWER_CAMERAS", ""))
    parser.add_argument("--no-gs-screens", action="store_true")
    parser.add_argument("--physics_steps_per_loop", type=int, default=10)
    parser.add_argument("--scene", type=str, default="xlerobot_nav",
                        help="Scene: xlerobot_nav (default), xlerobot, path to MJCF XML, or path to navigation JSON")
    args = parser.parse_args()

    from backend.gs_config import GSConfig
    from backend.sim_env import SimEnv
    from backend.viewer_screens import (
        camera_screen_bindings,
        create_viewer_screen_images,
        update_viewer_screen_images,
    )
    from service.server import (
        start_server, process_commands, apply_base_velocity, get_lock,
    )

    gs_cfg = GSConfig(
        assets_dir=args.gs_assets,
        scene=args.scene,
        robot_gs_dir=args.robot_gs_dir or None,
        scene_config=args.scene_config or None,
    )
    viewer_camera_names = (
        tuple(name.strip() for name in args.viewer_cameras.split(",") if name.strip())
        if args.viewer_cameras
        else gs_cfg.default_viewer_cameras
    )
    print(f"Loading scene: {gs_cfg.scene_xml}")
    env = SimEnv(gs_cfg.scene_xml, gs_cfg)
    print(f"Model loaded: {env.model.num_links} links, {env.model.num_dof_pos} DOFs")

    start_server(env, port=args.port)
    print(f"API: http://localhost:{args.port}")

    try:
        from motrixsim.render import RenderApp

        if not args.no_viewer:
            print("Starting viewer (close window to exit)...")
            gs_screen_bindings = ()
            if not args.no_gs_screens and viewer_camera_names:
                try:
                    gs_screen_bindings = camera_screen_bindings(env.model, viewer_camera_names)
                    print(
                        "3DGS viewer screens: "
                        + ", ".join(f"{b.camera_name}->cam{b.camera_id}" for b in gs_screen_bindings),
                        flush=True,
                    )
                except ValueError as exc:
                    print(f"3DGS viewer screens disabled: {exc}", flush=True)

            gs_update_interval = 1.0 / max(float(args.viewer_gs_fps), 0.1)
            next_gs_update_at = 0.0
            gs_screen_warning_reported = False
            with RenderApp() as render:
                render.launch(env.model)
                render.sync(env.data)
                gs_screen_images = {}
                if gs_screen_bindings:
                    gs_screen_images = create_viewer_screen_images(
                        render,
                        gs_screen_bindings,
                        width=args.gs_w,
                        height=args.gs_h,
                    )
                if gs_screen_images:
                    try:
                        update_viewer_screen_images(
                            env,
                            gs_screen_bindings,
                            gs_screen_images,
                            width=args.gs_w,
                            height=args.gs_h,
                        )
                        render.sync(env.data)
                        next_gs_update_at = time.perf_counter() + gs_update_interval
                    except Exception as exc:
                        gs_screen_warning_reported = True
                        print(f"3DGS viewer screen update failed: {exc}", flush=True)
                while not render.is_closed:
                    with get_lock():
                        process_commands(env)
                        apply_base_velocity(env)
                    for _ in range(args.physics_steps_per_loop):
                        env.step()
                    env.forward_kinematic()
                    now = time.perf_counter()
                    if gs_screen_images and now >= next_gs_update_at:
                        try:
                            update_viewer_screen_images(
                                env,
                                gs_screen_bindings,
                                gs_screen_images,
                                width=args.gs_w,
                                height=args.gs_h,
                            )
                        except Exception as exc:
                            if not gs_screen_warning_reported:
                                print(f"3DGS viewer screen update failed: {exc}", flush=True)
                                gs_screen_warning_reported = True
                        next_gs_update_at = now + gs_update_interval
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
