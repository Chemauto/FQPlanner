"""act_grasp.py — ACT-based grasp via remote inference service.

Orchestrates: render cameras → POST to ACT service → set qpos → step sim.
Called by server.py during act_grasp command processing.

Two-phase API (like nav command):
    act_grasp_init(env, ...)  → state dict for incremental stepping
    act_grasp_step(env, state) → None, modifies state in-place; state["done"] = True when finished
"""
from __future__ import annotations

import base64
import io
from typing import Dict, Optional

import numpy as np
from PIL import Image

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
CAMERA_CLIENT_KEYS = ["top", "left_wrist", "right_wrist"]

# Init pose (arms folded up, ready for grasping)
INIT_QPOS_LEFT = [-0.5035, 0.6527, 1.1747, 1.65, -0.7471, 0.2444, 0.9295]
INIT_QPOS_RIGHT = [0.3455, -0.5776, -0.9003, 1.6831, 0.6373, -0.0942, -0.7968]
INIT_QPOS = np.array(INIT_QPOS_LEFT + INIT_QPOS_RIGHT, dtype=np.float64)


def _find_actuator(env, joint_name: str):
    for i in range(env.model.num_actuators):
        act = env.model.get_actuator(i)
        if act.target_name == joint_name:
            return act
    return None


def get_act_state(env) -> np.ndarray:
    """Read 14 joint positions from sim."""
    dof_pos = np.asarray(env.data.dof_pos, dtype=np.float64).reshape(-1)
    if dof_pos.size >= NUM_JOINTS:
        return dof_pos[:NUM_JOINTS].copy()
    return dof_pos.copy()


def set_act_qpos(env, qpos: np.ndarray):
    """Set 14 joint targets via position actuators."""
    for i, name in enumerate(BLUETHINK_JOINTS):
        act = _find_actuator(env, name)
        if act is not None:
            act.set_ctrl(env.data, float(qpos[i]))


def move_to_init_pose(env, hold_steps=200):
    """Move arms to init pose and hold."""
    set_act_qpos(env, INIT_QPOS)
    for _ in range(hold_steps):
        env.step()
    env.forward_kinematic()


def render_camera(env, cam_id: int, w: int = 640, h: int = 480) -> np.ndarray:
    """Render a camera frame as HWC uint8 numpy array."""
    frame = env.render_frame(cam_id=cam_id, width=w, height=h)
    return np.asarray(frame, dtype=np.uint8)


def image_to_base64(img: np.ndarray) -> str:
    """HWC uint8 → base64 string."""
    pil = Image.fromarray(img)
    buf = io.BytesIO()
    pil.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def build_camera_name_to_id(env) -> Dict[str, int]:
    """Build camera name -> index map from model cameras."""
    name_to_id: Dict[str, int] = {}
    for idx in range(len(env.model.cameras)):
        cam = env.model.cameras[idx]
        name = getattr(cam, "name", "")
        if name:
            name_to_id[name] = idx
    return name_to_id


def get_camera_images_b64(env, cam_ids: Dict[str, int], w: int = 640, h: int = 480) -> Dict[str, str]:
    """Render all 3 cameras, return dict of base64 images."""
    images = {}
    for name in CAMERA_NAMES:
        cid = cam_ids.get(name)
        if cid is None:
            continue
        img = render_camera(env, cid, w, h)
        images[CAMERA_CLIENT_KEYS[CAMERA_NAMES.index(name)]] = image_to_base64(img)
    return images


def call_act_service(act_url: str, state: np.ndarray, images_b64: Dict[str, str],
                        timeout: float = 5.0) -> np.ndarray:
    """POST state+images to ACT service, return 14-dim actions."""
    import requests
    try:
        resp = requests.post(
            f"{act_url}/act_step",
            json={"state": state.tolist(), "images": images_b64},
            timeout=timeout,
        )
        resp.raise_for_status()
        return np.array(resp.json()["actions"], dtype=np.float64)
    except Exception as e:
        print(f"[act_grasp] ACT service error: {e}")
        return np.zeros(NUM_JOINTS, dtype=np.float64)


def get_object_z(env, obj_name: str) -> float:
    """Get object z position."""
    try:
        pos = env.get_body_xpos(obj_name)
        return float(pos[2])
    except Exception:
        return 0.0


# ── Two-phase API (init + step per main-loop iteration) ──────────

def act_grasp_init(env, act_url: str, obj_name: str, max_steps: int = 300,
                   physics_steps: int = 10, camera_w: int = 240, camera_h: int = 180,
                   lift_threshold: float = 0.05, policy_fps: float = 30.0,
                   init_hold_steps: int = 100, render_interval: int = 10) -> dict:
    """Initialize ACT grasp state. Call act_grasm_step() each main-loop iteration."""
    import time
    cam_ids = build_camera_name_to_id(env)
    obj_z_before = get_object_z(env, obj_name)

    # Set init pose (target only, don't step yet)
    set_act_qpos(env, INIT_QPOS)
    print(f"[act_grasp] Init pose target set. Object '{obj_name}' z_before={obj_z_before:.4f}")

    return {
        "done": False,
        "success": False,
        "phase": "init",  # "init" → hold init pose, "run" → ACT inference
        "init_remaining": init_hold_steps,
        "step": 0,
        "steps_run": 0,
        "max_steps": max_steps,
        "physics_steps": physics_steps,
        "camera_w": camera_w,
        "camera_h": camera_h,
        "lift_threshold": lift_threshold,
        "obj_name": obj_name,
        "obj_z_before": obj_z_before,
        "act_url": act_url,
        "cam_ids": cam_ids,
        "dt": 1.0 / policy_fps,  # min seconds between steps
        "last_step_time": 0.0,
        "render_interval": render_interval,  # re-render cameras every N steps
        "cached_images": None,
    }


def act_grasp_step(env, state: dict) -> dict:
    """Execute one ACT inference step. Modifies state in-place.

    Sets state["done"] = True when finished (success, failure, or max steps).
    Returns the same state dict for convenience.
    """
    if state["done"]:
        return state

    import time

    # Phase 1: hold init pose (incremental, not blocking)
    if state["phase"] == "init":
        set_act_qpos(env, INIT_QPOS)
        env.step()
        state["init_remaining"] -= 1
        if state["init_remaining"] <= 0:
            env.forward_kinematic()
            state["phase"] = "run"
            state["last_step_time"] = 0.0  # trigger first step immediately
            print(f"[act_grasp] Init complete, starting ACT inference", flush=True)
        return state

    # Phase 2: ACT inference (rate-limited)
    now = time.time()
    if now - state["last_step_time"] < state["dt"]:
        return state  # too early, skip
    state["last_step_time"] = now

    step = state["step"]
    act_url = state["act_url"]

    # 1. Get state
    qpos = get_act_state(env)

    # 2. Render cameras (only every render_interval steps to save time)
    ri = state["render_interval"]
    if state["cached_images"] is None or step % ri == 0:
        state["cached_images"] = get_camera_images_b64(env, state["cam_ids"], state["camera_w"], state["camera_h"])
    images_b64 = state["cached_images"]
    actions = call_act_service(act_url, qpos, images_b64)

    # 3. Apply actions
    set_act_qpos(env, actions)

    # 4. Physics steps
    for _ in range(state["physics_steps"]):
        env.step()

    state["step"] += 1
    state["steps_run"] += 1

    # Debug log every 10 steps
    if state["step"] % 10 == 0:
        ctrl_vals = []
        for name in BLUETHINK_JOINTS[:3]:
            act = _find_actuator(env, name)
            if act:
                ctrl_vals.append(float(act.get_ctrl(env.data)[0]))
        print(f"[act_grasp] step={state['step']}/{state['max_steps']}  ctrl[:3]={ctrl_vals}  action[:3]={actions[:3]}", flush=True)

    # 5. Check if object lifted
    if step % 30 == 0:
        obj_z = get_object_z(env, state["obj_name"])
        lifted = obj_z - state["obj_z_before"]
        if lifted > state["lift_threshold"]:
            print(f"[act_grasp] ✓ Object lifted! dz={lifted:.3f}m after {state['steps_run']} steps")
            state["success"] = True
            state["done"] = True
            return state

    # 6. Check max steps
    if state["step"] >= state["max_steps"]:
        obj_z_after = get_object_z(env, state["obj_name"])
        lifted = obj_z_after - state["obj_z_before"]
        state["success"] = lifted > state["lift_threshold"]
        print(f"[act_grasp] Finished. dz={lifted:.3f}m, steps={state['steps_run']}, success={state['success']}")
        state["done"] = True

    return state


# ── Blocking API (for standalone use) ──────────────────────────

def act_grasp(env, act_url: str, obj_name: str, max_steps: int = 300,
              physics_steps: int = 10, camera_w: int = 640, camera_h: int = 480,
              lift_threshold: float = 0.05) -> dict:
    """Blocking version: runs full ACT grasp loop. Returns result dict."""
    state = act_grasp_init(env, act_url, obj_name, max_steps, physics_steps, camera_w, camera_h, lift_threshold)
    while not state["done"]:
        act_grasp_step(env, state)

    from tools.move import get_base_info
    info = get_base_info(env)
    return {"success": state["success"], "steps_run": state["steps_run"], **info}
