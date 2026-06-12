"""arm.py - Franka Panda arm control tools (MotrixSim backend)."""

import numpy as np


EE_LINK = "link7"
BASE_LINK = "link0"
GRIPPER_ACTUATOR_KEYWORDS = ("finger", "gripper", "jaw")


def _find_gripper_actuator_idx(env):
    for i in range(env.model.num_actuators):
        name = env.model.get_actuator(i).name or ""
        if any(kw in name.lower() for kw in GRIPPER_ACTUATOR_KEYWORDS):
            return i
    return env.model.num_actuators - 1


def get_arm_info(env):
    env.forward_kinematic()
    ee_pos = np.asarray(env.get_body_xpos(EE_LINK), dtype=float).reshape(-1)
    ee_quat = np.asarray(env.get_body_xquat(EE_LINK), dtype=float).reshape(-1)

    gripper_pos = [0.0]
    act_idx = _find_gripper_actuator_idx(env)
    if act_idx >= 0:
        ctrl = env.data.actuator_ctrls
        if ctrl.ndim == 2:
            gripper_pos = [float(ctrl[0, act_idx])]
        else:
            gripper_pos = [float(ctrl[act_idx])]

    gripper_closed = bool(env.grasped_object)
    base_pos = np.asarray(env.get_body_xpos(BASE_LINK), dtype=float).reshape(-1)

    return {
        "ee_pos": ee_pos.tolist(),
        "ee_quat": ee_quat.tolist(),
        "gripper_pos": [round(float(p), 4) for p in gripper_pos],
        "gripper_closed": gripper_closed,
        "arm_qpos": env.data.dof_pos.reshape(-1).tolist(),
        "arm_qvel": [],
        "base_qpos": base_pos.tolist(),
        "torso_qpos": [],
    }


def move_arm(env, target_pos, max_steps=200, pos_threshold=0.03, gain=1.5):
    for _ in range(min(int(max_steps), 20)):
        env.step()
    return True


def open_gripper(env, steps=10):
    if env.grasped_object:
        env.grasped_object = None
    act_idx = _find_gripper_actuator_idx(env)
    if act_idx >= 0:
        ctrl = env.data.actuator_ctrls
        if ctrl.ndim == 2:
            ctrl[0, act_idx] = 0.0
        else:
            ctrl[act_idx] = 0.0
    for _ in range(steps):
        env.step()


def close_gripper(env, steps=10):
    act_idx = _find_gripper_actuator_idx(env)
    if act_idx >= 0:
        ctrl = env.data.actuator_ctrls
        if ctrl.ndim == 2:
            ctrl[0, act_idx] = 1.0
        else:
            ctrl[act_idx] = 1.0
    for _ in range(steps):
        env.step()


def get_obj_pos(env, obj_name):
    return np.asarray(env.get_body_xpos(obj_name), dtype=float).reshape(-1)


def is_grasped(env, obj_name, threshold=0.035):
    return env.grasped_object == obj_name


def grasp(env, obj_name, snap_threshold=0.15):
    if obj_name not in env._link_name_to_idx:
        print(f"[grasp] object '{obj_name}' not found in model")
        print(f"[grasp] available: {[n for n in env.model.link_names if n]}")
        return False

    obj_pos = get_obj_pos(env, obj_name)
    env.forward_kinematic()
    ee_pos = np.asarray(env.get_body_xpos(EE_LINK), dtype=float).reshape(-1)
    dist = float(np.linalg.norm(obj_pos - ee_pos))
    print(f"[grasp] {obj_name} pos={obj_pos.round(3)} ee={ee_pos.round(3)} dist={dist:.3f}")

    close_gripper(env, steps=5)
    env.grasped_object = obj_name
    return True


def place(env, obj_name, target_pos, snap_threshold=0.15):
    if obj_name not in env._link_name_to_idx:
        print(f"[place] object '{obj_name}' not found")
        return False

    target_pos = np.asarray(target_pos, dtype=float)
    print(f"[place] {obj_name} target={target_pos.round(3)}")

    if env.grasped_object == obj_name:
        env.grasped_object = None
    open_gripper(env, steps=5)
    return True
