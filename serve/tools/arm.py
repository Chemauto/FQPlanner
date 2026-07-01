"""
arm.py - PandaOmron 纯 MuJoCo 高层抓放工具

当前版本保留原 API 形状，使用虚拟末端点驱动高层任务测试。
机器人模型是 robosuite PandaOmron；抓放通过物体 freejoint 吸附到虚拟末端(夹爪)实现。
"""

import numpy as np

from scene.scene_memory import coords_to_waypoint, move_object


# PandaOmron 右臂 7 关节 + 夹爪指(用于 /status 汇报臂状态)
RIGHT_ARM_JOINTS = [
    "robot0_joint1",
    "robot0_joint2",
    "robot0_joint3",
    "robot0_joint4",
    "robot0_joint5",
    "robot0_joint6",
    "robot0_joint7",
    "gripper0_right_finger_joint1",
]


def get_arm_info(env):
    ee_pos = np.asarray(env.virtual_ee_pos, dtype=float)
    ee_quat = env.get_body_quat("gripper0_right_eef", fallback="robot0_right_hand")
    arm_qpos = []
    arm_qvel = []
    for joint_name in RIGHT_ARM_JOINTS:
        joint_id = _joint_id(env, joint_name)
        if joint_id < 0:
            continue
        qadr = env.model.jnt_qposadr[joint_id]
        dadr = env.model.jnt_dofadr[joint_id]
        arm_qpos.append(float(env.data.qpos[qadr]))
        arm_qvel.append(float(env.data.qvel[dadr]))

    gripper_pos = arm_qpos[-1:] if arm_qpos else [0.0]
    gripper_closed = bool(env.grasped_object)
    return {
        "ee_pos": ee_pos.tolist(),
        "ee_quat": ee_quat.tolist(),
        "gripper_pos": [round(float(p), 4) for p in gripper_pos],
        "gripper_closed": gripper_closed,
        "arm_qpos": arm_qpos,
        "arm_qvel": arm_qvel,
        "base_qpos": env.data.qpos[0:3].copy().tolist(),
        "torso_qpos": [],
    }


def move_arm(env, target_pos, max_steps=200, pos_threshold=0.03, gain=1.5):
    target_pos = np.asarray(target_pos, dtype=float)
    env.virtual_ee_pos = target_pos.copy()
    if env.grasped_object:
        env.set_object_pos(env.grasped_object, target_pos)
    for _ in range(min(int(max_steps), 20)):
        env.step()
    return True


def open_gripper(env, steps=10):
    if env.grasped_object:
        env.grasped_object = None
    _set_joint_ctrl(env, "Jaw_R", -0.2)
    for _ in range(steps):
        env.step()


def close_gripper(env, steps=10):
    _set_joint_ctrl(env, "Jaw_R", 1.2)
    for _ in range(steps):
        env.step()


def get_obj_pos(env, obj_name):
    return env.get_object_pos(obj_name)


def is_grasped(env, obj_name, threshold=0.035):
    return env.grasped_object == obj_name


def grasp(env, obj_name, snap_threshold=0.15):
    if obj_name not in env.obj_body_id:
        print(f"[grasp] 错误：物体 {obj_name} 不存在")
        print(f"[grasp] 可用物体: {list(env.obj_body_id.keys())}")
        return False

    obj_pos = get_obj_pos(env, obj_name)
    ee_pos = np.asarray(env.virtual_ee_pos, dtype=float)
    dist = float(np.linalg.norm(obj_pos - ee_pos))
    print(f"[grasp] {obj_name} pos={obj_pos.round(3)} ee={ee_pos.round(3)} dist={dist:.3f}")

    if dist > snap_threshold:
        move_arm(env, obj_pos, max_steps=50, pos_threshold=snap_threshold)

    close_gripper(env, steps=5)
    env.grasped_object = obj_name
    env.virtual_ee_pos = env.get_object_pos(obj_name).copy()
    lift_pos = env.virtual_ee_pos.copy()
    lift_pos[2] += 0.2
    move_arm(env, lift_pos, max_steps=20, pos_threshold=0.05)

    try:
        move_object(obj_name, "robot_hand")
    except Exception as e:
        print(f"[SceneMemory] 更新失败: {e}")
    return True


def place(env, obj_name, target_pos, snap_threshold=0.15):
    if obj_name not in env.obj_body_id:
        print(f"[place] 错误：物体 {obj_name} 不存在")
        return False

    target_pos = np.asarray(target_pos, dtype=float)
    print(f"[place] {obj_name} target={target_pos.round(3)}")
    move_arm(env, target_pos, max_steps=50, pos_threshold=snap_threshold)
    env.set_object_pos(obj_name, target_pos)
    if env.grasped_object == obj_name:
        env.grasped_object = None
    open_gripper(env, steps=5)

    lift_pos = target_pos.copy()
    lift_pos[2] += 0.2
    move_arm(env, lift_pos, max_steps=20, pos_threshold=0.05)

    try:
        waypoint_name = coords_to_waypoint(target_pos.tolist())
        move_object(obj_name, waypoint_name)
    except Exception as e:
        print(f"[SceneMemory] 更新失败: {e}")
    return True


def _joint_id(env, joint_name):
    import mujoco

    return mujoco.mj_name2id(env.model, mujoco.mjtObj.mjOBJ_JOINT, joint_name)


def _set_joint_ctrl(env, actuator_or_joint_name, value):
    import mujoco

    actuator_id = mujoco.mj_name2id(env.model, mujoco.mjtObj.mjOBJ_ACTUATOR, actuator_or_joint_name)
    if actuator_id >= 0:
        env.data.ctrl[actuator_id] = float(value)
