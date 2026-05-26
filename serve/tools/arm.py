"""
arm.py - PandaOmron 机械臂控制工具

提供 move_to、grasp、release、pick_and_place 等函数，
通过 env.step(action) 直接控制机械臂，不依赖 ROS2。

动作空间（12 维）：
  action[0:3]   → 末端位置增量 [dx, dy, dz]（归一化到 [-1, 1]）
  action[3:6]   → 末端旋转增量
  action[6:7]   → 夹爪 [负数=打开, 正数=关闭]
  action[11:12] → 控制模式 [负数=手臂模式, 正数=底座模式]
"""

import numpy as np


# ============================================================
# 状态查询
# ============================================================

def get_ee_pos(env):
    """获取末端执行器当前位置 [x, y, z]"""
    ee_id = env.sim.model.body_name2id("robot0_right_hand")
    return env.sim.data.body_xpos[ee_id].copy()


def get_obj_pos(env, obj_name):
    """获取物体位置 [x, y, z]"""
    return env.sim.data.body_xpos[env.obj_body_id[obj_name]].copy()


def get_arm_state(env):
    """获取机械臂状态"""
    ee_id = env.sim.model.body_name2id("robot0_right_hand")

    gripper_joints = ["gripper0_right_finger_joint1", "gripper0_right_finger_joint2"]
    gripper_pos = [
        env.sim.data.qpos[env.sim.model.get_joint_qpos_addr(j)]
        for j in gripper_joints
    ]
    gripper_closed = all(p < 0.035 for p in gripper_pos)

    return {
        "ee_pos": env.sim.data.body_xpos[ee_id].copy(),
        "gripper_closed": gripper_closed,
        "gripper_pos": gripper_pos,
    }


# ============================================================
# 底层控制
# ============================================================

def _make_arm_action(arm_delta=None, gripper=None):
    """
    构建 12 维动作向量（手臂模式）

    Args:
        arm_delta: [dx, dy, dz] 或 [dx, dy, dz, droll, dpitch, dyaw]
        gripper: 夹爪动作（负数=打开, 正数=关闭），None 表示不动
    """
    action = np.zeros(12)

    if arm_delta is not None:
        arm_delta = np.array(arm_delta, dtype=float)
        if len(arm_delta) == 3:
            action[0:3] = np.clip(arm_delta, -1.0, 1.0)
        elif len(arm_delta) == 6:
            action[0:6] = np.clip(arm_delta, -1.0, 1.0)

    if gripper is not None:
        action[6] = np.clip(gripper, -1.0, 1.0)

    action[11] = -1.0  # 手臂模式
    return action


def _step_n(env, action, n=1):
    """执行 n 步相同的动作"""
    for _ in range(n):
        env.step(action)


def _quat_to_rot_matrix(quat):
    """四元数 [w, x, y, z] 转 3x3 旋转矩阵"""
    w, x, y, z = quat
    return np.array([
        [1 - 2*(y*y + z*z), 2*(x*y - w*z),     2*(x*z + w*y)],
        [2*(x*y + w*z),     1 - 2*(x*x + z*z), 2*(y*z - w*x)],
        [2*(x*z - w*y),     2*(y*z + w*x),     1 - 2*(x*x + y*y)],
    ])


# ============================================================
# 移动控制
# ============================================================

def move_to(env, target_pos, steps=300, threshold=0.03, gain=1.5):
    """
    移动末端执行器到目标位置

    Args:
        env: 环境对象
        target_pos: 目标位置 [x, y, z]（世界坐标）
        steps: 最大仿真步数
        threshold: 到达判定阈值（米）
        gain: 控制增益

    Returns:
        bool: 是否到达目标
    """
    target_pos = np.array(target_pos, dtype=float)
    max_step = 0.05

    for _ in range(steps):
        ee_pos = get_ee_pos(env)
        error_world = target_pos - ee_pos
        dist = np.linalg.norm(error_world)

        if dist < threshold:
            return True

        base_id = env.sim.model.body_name2id("robot0_base")
        base_quat = env.sim.data.body_xquat[base_id]
        base_mat = _quat_to_rot_matrix(base_quat)
        error_base = base_mat.T @ error_world

        delta = np.clip(error_base * gain / max_step, -1.0, 1.0)
        action = _make_arm_action(arm_delta=delta)
        env.step(action)

    return False


# ============================================================
# 夹爪控制
# ============================================================

def open_gripper(env, steps=10):
    """打开夹爪"""
    action = _make_arm_action(gripper=-1.0)
    _step_n(env, action, steps)


def close_gripper(env, steps=10):
    """关闭夹爪"""
    action = _make_arm_action(gripper=1.0)
    _step_n(env, action, steps)


def is_grasped(env, obj_name, threshold=0.035):
    """检查是否抓住物体"""
    from robocasa.utils.object_utils import check_obj_grasped
    return check_obj_grasped(env, obj_name, threshold=threshold)


# ============================================================
# 高级操作
# ============================================================

def grasp(env, obj_name, approach_height=0.15, snap_threshold=0.2,
          grasp_steps=20, lift_height=0.2):
    """
    抓取物体：移到物体上方 → 受控下降 → 吸附修正 → 关夹爪 → 提起

    Args:
        env: 环境对象
        obj_name: 物体名称
        approach_height: 接近高度（物体上方多少米）
        snap_threshold: 吸附阈值（米）
        grasp_steps: 关夹爪步数
        lift_height: 提起高度

    Returns:
        bool: 是否成功抓取
    """
    obj_pos = get_obj_pos(env, obj_name)

    # 阶段 1：移到物体正上方
    above_pos = obj_pos.copy()
    above_pos[2] += approach_height
    reached = move_to(env, above_pos, steps=300, threshold=0.03)
    if not reached:
        print("[grasp] 警告：未能到达物体上方位置")

    # 阶段 2：受控下降
    obj_pos = get_obj_pos(env, obj_name)
    ee_pos = get_ee_pos(env)
    current_z = ee_pos[2]
    target_z = obj_pos[2] + 0.02

    while current_z > target_z:
        current_z -= 0.02
        step_target = np.array([obj_pos[0], obj_pos[1], max(current_z, target_z)])
        move_to(env, step_target, steps=30, threshold=0.02)
        obj_pos = get_obj_pos(env, obj_name)

    # 阶段 3：吸附修正
    ee_pos = get_ee_pos(env)
    obj_pos = get_obj_pos(env, obj_name)
    dist = np.linalg.norm(ee_pos - obj_pos)

    if dist < snap_threshold:
        obj_body_id = env.obj_body_id[obj_name]
        obj_joint_id = env.sim.model.body_jntadr[obj_body_id]
        env.sim.data.qpos[obj_joint_id:obj_joint_id + 3] = ee_pos
        env.sim.data.qpos[obj_joint_id + 3:obj_joint_id + 7] = [1, 0, 0, 0]
        env.sim.forward()
        print(f"[grasp] 吸附修正：距离 {dist:.3f}m < {snap_threshold}m")
    else:
        print(f"[grasp] 距离 {dist:.3f}m > {snap_threshold}m，吸附失败")
        return False

    # 阶段 4：关闭夹爪
    close_gripper(env, steps=grasp_steps)

    # 阶段 5：提起
    lift_pos = get_ee_pos(env)
    lift_pos[2] += lift_height
    move_to(env, lift_pos, steps=50, threshold=0.03)

    return is_grasped(env, obj_name)


def release(env, lift_height=0.1, steps=20):
    """
    释放物体：打开夹爪 → 可选提起

    Args:
        env: 环境对象
        lift_height: 释放后提起高度
        steps: 打开夹爪的步数
    """
    open_gripper(env, steps=steps)

    if lift_height > 0:
        ee_pos = get_ee_pos(env)
        ee_pos[2] += lift_height
        move_to(env, ee_pos, steps=30, threshold=0.03)


def pick_and_place(env, obj_name, target_pos, approach_height=0.15):
    """
    抓取并放置物体

    Args:
        env: 环境对象
        obj_name: 物体名称
        target_pos: 放置目标位置 [x, y, z]
        approach_height: 接近高度

    Returns:
        bool: 是否成功
    """
    success = grasp(env, obj_name, approach_height=approach_height)
    if not success:
        print(f"[pick_and_place] 抓取 {obj_name} 失败")
        return False

    above_target = np.array(target_pos, dtype=float)
    above_target[2] += approach_height
    move_to(env, above_target, steps=150, threshold=0.03)

    ee_pos = get_ee_pos(env)
    current_z = ee_pos[2]
    target_z = target_pos[2] + 0.02
    while current_z > target_z:
        current_z -= 0.02
        step_target = np.array([target_pos[0], target_pos[1], max(current_z, target_z)])
        move_to(env, step_target, steps=30, threshold=0.02)

    release(env, lift_height=approach_height)

    return True
