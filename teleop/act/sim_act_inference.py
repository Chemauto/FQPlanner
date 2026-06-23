"""
ACT Policy Inference in Simulation for BlueThink Dual-Arm Robot.

Loads a LeRobot ACT policy checkpoint and runs it with the MotrixSim
simulation environment. Renders 3 camera views (base, left wrist, right wrist)
and controls 14 joint actuators based on policy output.

Usage:
    python teleop/act/sim_act_inference.py \
        --policy-path "/media/fangqi/HP USB321FD/scrips/outputs/train/act_clear_table/checkpoints/060000/pretrained_model" \
        --device cuda
"""

from __future__ import annotations

import argparse
import importlib
import sys
import time
from pathlib import Path
from typing import Dict, Optional, Sequence

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from serve_3dgs.backend.gs_config import GSConfig
from serve_3dgs.backend.sim_env import SimEnv

BLUETHINK_LEFT_JOINTS = [
    "Left_Shoulder_Pitch_Joint",
    "Left_Shoulder_Roll_Joint",
    "Left_Shoulder_Yaw_Joint",
    "Left_Elbow_Pitch_Joint",
    "Left_Wrist_Yaw_Joint",
    "Left_Wrist_Pitch_Joint",
    "Left_Wrist_Roll_Joint",
]

BLUETHINK_RIGHT_JOINTS = [
    "Right_Shoulder_Pitch_Joint",
    "Right_Shoulder_Roll_Joint",
    "Right_Shoulder_Yaw_Joint",
    "Right_Elbow_Pitch_Joint",
    "Right_Wrist_Yaw_Joint",
    "Right_Wrist_Pitch_Joint",
    "Right_Wrist_Roll_Joint",
]

BLUETHINK_JOINTS = BLUETHINK_LEFT_JOINTS + BLUETHINK_RIGHT_JOINTS
NUM_JOINTS = len(BLUETHINK_JOINTS)

CAMERA_NAMES = ["base_cam", "left_ee_cam", "right_ee_cam"]
POLICY_IMAGE_KEYS = [
    "observation.images.top",
    "observation.images.left_wrist",
    "observation.images.right_wrist",
]

INIT_QPOS_LEFT = [-0.5035, 0.6527, 1.1747, 1.65, -0.7471, 0.2444, 0.9295]
INIT_QPOS_RIGHT = [0.3455, -0.5776, -0.9003, 1.6831, 0.6373, -0.0942, -0.7968]
INIT_QPOS = np.array(INIT_QPOS_LEFT + INIT_QPOS_RIGHT, dtype=np.float64)


def _find_actuator(env, name: str):
    for i in range(env.model.num_actuators):
        act = env.model.get_actuator(i)
        if act.name == name:
            return act
    return None


def get_qpos(env) -> np.ndarray:
    """Read current joint positions from sim data."""
    dof_pos = np.asarray(env.data.dof_pos, dtype=np.float64).reshape(-1)
    if dof_pos.size >= NUM_JOINTS:
        return dof_pos[:NUM_JOINTS].copy()
    return dof_pos.copy()


def set_qpos(env, qpos: np.ndarray):
    """Set target joint positions via actuator controls."""
    for i, name in enumerate(BLUETHINK_JOINTS):
        act = _find_actuator(env, name)
        if act is not None:
            lo, hi = act.ctrl_range
            val = float(np.clip(qpos[i], lo, hi))
            act.set_ctrl(env.data, val)


def build_camera_name_to_id(env) -> Dict[str, int]:
    """Build name -> index map for all cameras in the model."""
    name_to_id: Dict[str, int] = {}
    for idx in range(len(env.model.cameras)):
        cam = env.model.cameras[idx]
        if cam.name:
            name_to_id[cam.name] = idx
    return name_to_id


def image_hwc_to_tensor(image: np.ndarray, device: str) -> 'torch.Tensor':
    """Convert HWC uint8 RGB image to batched CHW float tensor for LeRobot."""
    import torch
    arr = np.asarray(image, dtype=np.uint8)
    if arr.shape[-1] == 4:
        arr = arr[..., :3]
    tensor = torch.from_numpy(arr.copy()).permute(2, 0, 1).float().div_(255.0)
    return tensor.unsqueeze(0).to(device=device, non_blocking=True)


def import_act_policy_class():
    candidates = (
        "lerobot.policies.act.modeling_act.ACTPolicy",
        "lerobot.common.policies.act.modeling_act.ACTPolicy",
    )
    errors = []
    for dotted in candidates:
        module_name, class_name = dotted.rsplit(".", 1)
        try:
            module = importlib.import_module(module_name)
            return getattr(module, class_name)
        except BaseException as e:
            errors.append(f"{dotted}: {e!r}")
    raise ImportError("Could not import ACTPolicy. Tried:\n  " + "\n  ".join(errors))


def load_act_policy(policy_path: str, device: str):
    ACTPolicy = import_act_policy_class()
    try:
        policy = ACTPolicy.from_pretrained(policy_path, device=device)
    except TypeError:
        policy = ACTPolicy.from_pretrained(policy_path)
    policy.to(device)
    policy.eval()
    if hasattr(policy, "reset"):
        policy.reset()
    return policy


def step_policy(policy, state: np.ndarray, images: Dict[str, np.ndarray], device: str) -> np.ndarray:
    import torch

    state_t = torch.as_tensor(state, dtype=torch.float32, device=device).unsqueeze(0)

    batch = {"observation.state": state_t}
    for name, sim_name in zip(POLICY_IMAGE_KEYS, CAMERA_NAMES):
        img = images.get(sim_name)
        if img is not None:
            batch[name] = image_hwc_to_tensor(img, device)

    if hasattr(policy, "normalize_inputs"):
        batch = policy.normalize_inputs(batch)
    elif hasattr(policy, "preprocessor"):
        batch = policy.preprocessor(batch)

    with torch.inference_mode():
        action = policy.select_action(batch)
        out_dict = {"action": action}
        if hasattr(policy, "unnormalize_outputs"):
            out_dict = policy.unnormalize_outputs(out_dict)
        elif hasattr(policy, "postprocessor"):
            out_dict = policy.postprocessor(out_dict)
        action = out_dict["action"]

    if device.startswith("cuda"):
        torch.cuda.synchronize()

    arr = action.detach().float().cpu().numpy()
    if arr.ndim == 3:
        arr = arr[0, 0]  # (1, T, dim) -> (dim,)
    elif arr.ndim == 2:
        arr = arr[0]  # (1, dim) -> (dim,)
    return arr.astype(np.float64).reshape(-1)


def main():
    parser = argparse.ArgumentParser(description="ACT inference in BlueThink simulation")
    parser.add_argument("--policy-path", required=True, help="Path to ACT policy checkpoint directory")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--scene", type=str, default="robot_only",
                        help="Scene override: robot_only, robot_nav, or path to MJCF/XML")
    parser.add_argument("--camera-w", type=int, default=640)
    parser.add_argument("--camera-h", type=int, default=480)
    parser.add_argument("--policy-fps", type=float, default=30.0)
    parser.add_argument("--physics-steps-per-step", type=int, default=10)
    parser.add_argument("--duration", type=float, default=0.0,
                        help="Max execution seconds. <=0 runs until Ctrl+C")
    parser.add_argument("--no-viewer", action="store_true")
    parser.add_argument("--no-init-move", action="store_true",
                        help="Skip moving robot to a neutral starting pose")
    parser.add_argument("--init-hold-steps", type=int, default=50,
                        help="Simulation steps to hold initial pose before inference")
    args = parser.parse_args()

    print(f"Loading BlueThink scene...")
    gs_cfg = GSConfig(scene=args.scene, robot_name="BlueThink")
    env = SimEnv(gs_cfg.scene_xml, gs_cfg, enable_renderers=True)
    print(f"Model loaded: {env.model.num_links} links, {env.model.num_dof_pos} DOFs")
    print(f"Actuators: {env.model.num_actuators}")
    print(f"Cameras: {len(env.model.cameras)}")

    cam_name_to_id = build_camera_name_to_id(env)
    print(f"Camera mapping: {cam_name_to_id}")

    cam_ids = {}
    for name in CAMERA_NAMES:
        if name in cam_name_to_id:
            cam_ids[name] = cam_name_to_id[name]
            print(f"  {name} -> cam_id={cam_name_to_id[name]}")
        else:
            raise RuntimeError(f"Camera '{name}' not found in model. Available: {list(cam_name_to_id.keys())}")

    print(f"\nLoading ACT policy: {args.policy_path}")
    policy = load_act_policy(args.policy_path, device=args.device)
    print(f"Policy loaded. Device: {args.device}")

    qpos = get_qpos(env)
    print(f"\nInitial qpos ({len(qpos)} joints): {np.round(qpos, 3).tolist()}")

    if not args.no_init_move:
        set_qpos(env, INIT_QPOS)
        print(f"Moving to init pose...")
        for _ in range(args.init_hold_steps):
            env.step()
        env.forward_kinematic()
        qpos = get_qpos(env)
        print(f"Init qpos: {np.round(qpos, 3).tolist()}")

    try:
        from motrixsim.render import RenderApp
    except ImportError:
        RenderApp = None

    status_interval = 1.0
    last_status = 0.0
    inference_count = 0

    def inference_loop(env, policy, cam_ids, args, render=None):
        nonlocal last_status, inference_count
        dt = 1.0 / max(1e-3, float(args.policy_fps))
        next_infer = time.perf_counter()
        start_t = next_infer

        while True:
            if render is not None and render.is_closed:
                break
            if args.duration > 0 and time.perf_counter() - start_t >= args.duration:
                print(f"\nDuration reached: {args.duration:.1f}s")
                break

            now = time.perf_counter()
            sleep_time = next_infer - now
            if sleep_time > 0:
                time.sleep(min(0.005, sleep_time))
                continue

            next_infer = max(now, next_infer) + dt

            env.forward_kinematic()
            qpos = get_qpos(env)

            images: Dict[str, np.ndarray] = {}
            for name in CAMERA_NAMES:
                frame = env.render_frame(
                    cam_id=cam_ids[name],
                    width=args.camera_w,
                    height=args.camera_h,
                )
                images[name] = np.asarray(frame)

            try:
                action = step_policy(policy, qpos, images, device=args.device)
                inference_count += 1
            except Exception as e:
                print(f"\nPolicy inference failed: {e}")
                break

            action = np.asarray(action, dtype=np.float64).reshape(-1)
            if action.size != NUM_JOINTS:
                print(f"\nWARNING: policy output dim={action.size}, expected {NUM_JOINTS}")
                if action.size > NUM_JOINTS:
                    action = action[:NUM_JOINTS]
                else:
                    break

            set_qpos(env, action)

            for _ in range(args.physics_steps_per_step):
                env.step()

            if render is not None:
                render.sync(env.data)

            t_now = time.perf_counter()
            if t_now - last_status >= status_interval:
                diff = np.max(np.abs(action - qpos))
                print(f"\rACT #{inference_count} | max dq={diff:.4f} rad | "
                      f"latency={((t_now - now) * 1000):.0f}ms  ", end="", flush=True)
                last_status = t_now

        return inference_count

    if RenderApp is None:
        print("RenderApp not available, running headless...")
        inference_loop(env, policy, cam_ids, args)
        print(f"\nDone. {inference_count} inferences.")
        return

    with RenderApp() as render:
        if not args.no_viewer:
            render.launch(env.model)
            print("\nControls: ESC to exit")
        else:
            print("\nRunning inference (no viewer)")

        inference_loop(env, policy, cam_ids, args, render=None if args.no_viewer else render)

    print(f"\nDone. {inference_count} inferences.")


if __name__ == "__main__":
    main()
