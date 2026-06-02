"""
arm.py - PandaOmron 机械臂控制工具

动作空间（12 维）：
  action[0:3]   → 末端位置增量 [dx, dy, dz]（归一化到 [-1, 1]）
  action[3:6]   → 末端旋转增量
  action[6:7]   → 夹爪 [负数=打开, 正数=关闭]
  action[11:12] → 控制模式 [负数=手臂模式, 正数=底座模式]
"""

import numpy as np

from scene.scene_memory import move_object, coords_to_waypoint

# ============================================================
# 状态查询
# ============================================================

def get_arm_info(env):
    """
    获取机械臂全部状态数据

    Returns:
        dict:
            ee_pos:        末端执行器世界坐标 [x, y, z]
            ee_quat:       末端执行器四元数 [w, x, y, z]
            gripper_pos:   夹爪关节位置 [finger1, finger2]
            gripper_closed: 夹爪是否闭合
            arm_qpos:      手臂关节位置 [j0~j6]
            arm_qvel:      手臂关节速度 [j0~j6]
            base_qpos:     底座关节位置 [forward, side, yaw]
            torso_qpos:    躯干关节位置 [height]
    """
    robot = env.robots[0]
    ee_id = env.sim.model.body_name2id("robot0_right_hand")

    # 末端执行器位姿
    ee_pos = env.sim.data.body_xpos[ee_id].copy()
    ee_quat = env.sim.data.body_xquat[ee_id].copy()

    # 夹爪状态
    gripper_joints = ["gripper0_right_finger_joint1", "gripper0_right_finger_joint2"]
    gripper_pos = [
        env.sim.data.qpos[env.sim.model.get_joint_qpos_addr(j)]
        for j in gripper_joints
    ]
    gripper_closed = all(p < 0.035 for p in gripper_pos)

    # 关节状态（使用动态索引）
    arm_qpos = env.sim.data.qpos[robot._ref_arm_joint_pos_indexes].copy()
    arm_qvel = env.sim.data.qvel[robot._ref_arm_joint_vel_indexes].copy()
    base_qpos = env.sim.data.qpos[robot._ref_base_joint_pos_indexes].copy()
    torso_qpos = env.sim.data.qpos[robot._ref_torso_joint_pos_indexes].copy()

    return {
        "ee_pos": ee_pos.tolist(),
        "ee_quat": ee_quat.tolist(),
        "gripper_pos": [round(p, 4) for p in gripper_pos],
        "gripper_closed": gripper_closed,
        "arm_qpos": arm_qpos.tolist(),
        "arm_qvel": arm_qvel.tolist(),
        "base_qpos": base_qpos.tolist(),
        "torso_qpos": torso_qpos.tolist(),
    }


def move_arm(env, target_pos, max_steps=200, pos_threshold=0.03, gain=1.5):
    """
    移动机械臂末端到目标位置（delta 控制模式）

    Args:
        env: 环境对象
        target_pos: 目标位置 [x, y, z]（世界坐标）
        max_steps: 最大仿真步数
        pos_threshold: 到达判定阈值（米）
        gain: 控制增益

    Returns:
        bool: 是否到达目标
    """
    target_pos = np.array(target_pos, dtype=float)
    max_delta = 0.05  # 每步最大位置增量

    for step in range(max_steps):
        # 获取当前末端位置
        ee_id = env.sim.model.body_name2id("robot0_right_hand")
        ee_pos = env.sim.data.body_xpos[ee_id].copy()

        # 计算误差（世界坐标）
        error_world = target_pos - ee_pos
        dist = np.linalg.norm(error_world)

        # 到达目标
        if dist < pos_threshold:
            print(f"[move_arm] 到达目标，步数={step}，距离={dist:.4f}m")
            return True

        # 转换到基座坐标系
        base_site_id = env.sim.model.site_name2id("robot0_right_center")
        base_ori = env.sim.data.site_xmat[base_site_id].reshape(3, 3)
        error_base = base_ori.T @ error_world

        # 计算 delta 动作（归一化到 [-1, 1]）
        delta_pos = np.clip(error_base * gain / max_delta, -1.0, 1.0)

        # 构建 12 维动作向量
        action = np.zeros(12)
        action[0:3] = delta_pos  # 位置增量
        action[3:6] = 0.0        # 旋转增量（保持当前姿态）
        action[11] = -1.0        # 手臂模式

        # 执行动作
        env.step(action)

        # 调试输出
        if step % 50 == 0 or step == max_steps - 1:
            print(f"[move_arm] step={step} ee={ee_pos.round(3)} "
                  f"err={error_world.round(3)} dist={dist:.3f}")

    print(f"[move_arm] 超时，步数={max_steps}，距离={dist:.3f}m")
    return False


# ============================================================
# OSC_POSE absolute 模式
# ============================================================

def get_osc_pose_controller_config():
    """
    获取 OSC_POSE absolute 模式的控制器配置

    Returns:
        dict: 控制器配置，用于创建环境时传入 controller_configs
    """
    return {
        "type": "BASIC",
        "body_parts": {
            "arms": {
                "right": {
                    "type": "OSC_POSE",
                    "input_type": "absolute",
                    "input_ref_frame": "world",
                    "input_max": 1,
                    "input_min": -1,
                    "output_max": [0.05, 0.05, 0.05, 0.5, 0.5, 0.5],
                    "output_min": [-0.05, -0.05, -0.05, -0.5, -0.5, -0.5],
                    "kp": 150,
                    "damping_ratio": 1,
                    "impedance_mode": "fixed",
                    "uncouple_pos_ori": True,
                    "gripper": {"type": "GRIP"},
                }
            },
            "base": {
                "type": "JOINT_VELOCITY",
                "input_type": "delta",
            },
            "torso": {
                "type": "JOINT_POSITION",
                "input_type": "delta",
            }
        }
    }


def move_arm_OSC_POSE(env, target_pos, target_rot=None):
    """
    移动机械臂末端到目标位置（OSC_POSE absolute 模式）

    注意：需要在创建环境时使用 get_osc_pose_controller_config() 配置控制器

    Args:
        env: 环境对象（必须配置为 OSC_POSE absolute 模式）
        target_pos: 目标位置 [x, y, z]（世界坐标）
        target_rot: 目标旋转 [rx, ry, rz]（轴角表示），None 则保持当前姿态

    Returns:
        dict: 执行后的机械臂状态（同 get_arm_info）
    """
    target_pos = np.array(target_pos, dtype=float)

    # 如果没有指定旋转，使用当前姿态
    if target_rot is None:
        ee_id = env.sim.model.body_name2id("robot0_right_hand")
        ee_quat = env.sim.data.body_xquat[ee_id]  # [w, x, y, z]
        # 四元数转轴角
        from scipy.spatial.transform import Rotation
        target_rot = Rotation.from_quat([ee_quat[1], ee_quat[2], ee_quat[3], ee_quat[0]]).as_rotvec()
    else:
        target_rot = np.array(target_rot, dtype=float)

    # 构建 12 维动作向量
    action = np.zeros(12)
    action[0:3] = target_pos   # 绝对位置
    action[3:6] = target_rot   # 轴角旋转
    action[6] = -1.0           # 夹爪（保持不变）
    action[11] = -1.0          # 手臂模式

    # 执行动作
    env.step(action)

    return get_arm_info(env)


# ============================================================
# 夹爪控制
# ============================================================

def open_gripper(env, steps=10):
    """打开夹爪"""
    for _ in range(steps):
        action = np.zeros(12)
        action[6] = -1.0    # 负数=打开
        action[11] = -1.0   # 手臂模式
        env.step(action)


def close_gripper(env, steps=10):
    """关闭夹爪"""
    for _ in range(steps):
        action = np.zeros(12)
        action[6] = 1.0     # 正数=关闭
        action[11] = -1.0   # 手臂模式
        env.step(action)


def get_obj_pos(env, obj_name):
    """获取物体位置 [x, y, z]"""
    return env.sim.data.body_xpos[env.obj_body_id[obj_name]].copy()


def is_grasped(env, obj_name, threshold=0.035):
    """检查是否抓住物体"""
    gripper_joints = ["gripper0_right_finger_joint1", "gripper0_right_finger_joint2"]
    gripper_pos = [
        env.sim.data.qpos[env.sim.model.get_joint_qpos_addr(j)]
        for j in gripper_joints
    ]
    # 夹爪闭合且物体在夹爪附近
    gripper_closed = all(p < threshold for p in gripper_pos)
    if not gripper_closed:
        return False

    ee_id = env.sim.model.body_name2id("robot0_right_hand")
    ee_pos = env.sim.data.body_xpos[ee_id]
    obj_pos = get_obj_pos(env, obj_name)
    dist = np.linalg.norm(ee_pos - obj_pos)
    return bool(dist < 0.1)  # 物体在夹爪 10cm 范围内


# ============================================================
# 高级操作
# ============================================================

def grasp(env, obj_name, snap_threshold=0.15):
    """
    抓取物体：移到物体附近 → 吸附 → 关夹爪 → 提起

    Args:
        env: 环境对象
        obj_name: 物体名称
        snap_threshold: 吸附触发距离（米）

    Returns:
        bool: 是否成功抓取
    """
    # 0. 检查物体是否存在
    if obj_name not in env.obj_body_id:
        print(f"[grasp] 错误：物体 {obj_name} 不存在")
        print(f"[grasp] 可用物体: {list(env.obj_body_id.keys())}")
        return False

    # 1. 获取物体位置
    obj_pos = get_obj_pos(env, obj_name)
    ee_id = env.sim.model.body_name2id("robot0_right_hand")
    ee_pos = env.sim.data.body_xpos[ee_id].copy()
    print(f"[grasp] 目标物体 {obj_name} 位置: {obj_pos.round(3)}")
    print(f"[grasp] 当前末端位置: {ee_pos.round(3)}")
    print(f"[grasp] 初始距离: {np.linalg.norm(obj_pos - ee_pos):.3f}m")

    # 2. 打开夹爪
    open_gripper(env, steps=10)

    # 3. 移到物体附近
    reached = move_arm(env, obj_pos, max_steps=300, pos_threshold=snap_threshold)
    ee_pos = env.sim.data.body_xpos[ee_id].copy()
    dist = np.linalg.norm(obj_pos - ee_pos)
    print(f"[grasp] 移动后距离: {dist:.3f}m, reached={reached}")

    if not reached:
        print(f"[grasp] 无法到达 {obj_name}，距离 {dist:.3f}m > 阈值 {snap_threshold}m")
        return False

    # 4. 吸附：物体瞬移到夹爪位置
    ee_pos = env.sim.data.body_xpos[ee_id].copy()
    obj_body_id = env.obj_body_id[obj_name]
    print(f"[grasp] 吸附前物体位置: {get_obj_pos(env, obj_name).round(3)}")
    print(f"[grasp] 吸附到末端位置: {ee_pos.round(3)}")

    try:
        # 获取物体的 joint 信息
        obj_joint_id = env.sim.model.body_jntadr[obj_body_id]
        print(f"[grasp] 物体 joint id: {obj_joint_id}")

        # 获取 joint 名称
        obj_joint_name = env.sim.model.joint_id2name(obj_joint_id)
        print(f"[grasp] 物体 joint 名称: {obj_joint_name}")

        # 设置物体位置和朝向 [x, y, z, qw, qx, qy, qz]
        env.sim.data.set_joint_qpos(obj_joint_name, np.concatenate([ee_pos, [1, 0, 0, 0]]))
        env.sim.forward()
        print(f"[grasp] 吸附后物体位置: {get_obj_pos(env, obj_name).round(3)}")
    except Exception as e:
        print(f"[grasp] 吸附失败: {e}")
        # 备用方案：直接修改 qpos
        print(f"[grasp] 尝试备用方案...")
        obj_joint_id = env.sim.model.body_jntadr[obj_body_id]
        env.sim.data.qpos[obj_joint_id:obj_joint_id + 3] = ee_pos
        env.sim.data.qpos[obj_joint_id + 3:obj_joint_id + 7] = [1, 0, 0, 0]
        env.sim.forward()
        print(f"[grasp] 备用方案后物体位置: {get_obj_pos(env, obj_name).round(3)}")

    # 5. 关夹爪
    close_gripper(env, steps=10)

    # 6. 提起
    lift_pos = ee_pos.copy()
    lift_pos[2] += 0.2
    print(f"[grasp] 提起目标位置: {lift_pos.round(3)}")
    move_arm(env, lift_pos, max_steps=50, pos_threshold=0.05)

    # 7. 检查是否成功
    success = is_grasped(env, obj_name)
    final_obj_pos = get_obj_pos(env, obj_name)
    final_ee_pos = env.sim.data.body_xpos[ee_id].copy()
    print(f"[grasp] 最终物体位置: {final_obj_pos.round(3)}")
    print(f"[grasp] 最终末端位置: {final_ee_pos.round(3)}")
    print(f"[grasp] 最终距离: {np.linalg.norm(final_obj_pos - final_ee_pos):.3f}m")
    print(f"[grasp] {'成功' if success else '失败'}抓取 {obj_name}")
    # 在 return success 之前
    if success:
        try:
            move_object(obj_name, 'robot_hand')
        except Exception as e:
            print(f"[SceneMemory] 更新失败: {e}")
    return success

def place(env, obj_name, target_pos, snap_threshold=0.15):
    """
    放置物体：移到目标附近 → 瞬移物体到目标 → 开夹爪 → 提起

    Args:
        env: 环境对象
        obj_name: 物体名称
        target_pos: 目标位置 [x, y, z]（世界坐标）
        snap_threshold: 瞬移触发距离（米）

    Returns:
        bool: 是否成功放置
    """
    target_pos = np.array(target_pos, dtype=float)
    print(f"[place] 目标位置: {target_pos.round(3)}")

    # 1. 移到目标附近
    reached = move_arm(env, target_pos, max_steps=300, pos_threshold=snap_threshold)
    if not reached:
        ee_id = env.sim.model.body_name2id("robot0_right_hand")
        ee_pos = env.sim.data.body_xpos[ee_id]
        dist = np.linalg.norm(target_pos - ee_pos)
        print(f"[place] 无法到达目标点，距离 {dist:.3f}m > 阈值 {snap_threshold}m")
        return False

    # 2. 瞬移物体到目标位置
    try:
        obj_body_id = env.obj_body_id[obj_name]
        obj_joint_id = env.sim.model.body_jntadr[obj_body_id]
        obj_joint_name = env.sim.model.joint_id2name(obj_joint_id)
        print(f"[place] 瞬移物体 {obj_name} 到目标位置")
        env.sim.data.set_joint_qpos(obj_joint_name, np.concatenate([target_pos, [1, 0, 0, 0]]))
        env.sim.forward()
        print(f"[place] 物体位置: {get_obj_pos(env, obj_name).round(3)}")
    except Exception as e:
        print(f"[place] 瞬移失败: {e}")

    # 3. 开夹爪释放物体
    open_gripper(env, steps=10)
    print(f"[place] 释放物体")

    # 4. 提起
    ee_id = env.sim.model.body_name2id("robot0_right_hand")
    ee_pos = env.sim.data.body_xpos[ee_id].copy()
    lift_pos = ee_pos.copy()
    lift_pos[2] += 0.2
    move_arm(env, lift_pos, max_steps=50, pos_threshold=0.05)

    try:
        waypoint_name = coords_to_waypoint(target_pos.tolist())
        move_object(obj_name, waypoint_name)
    except Exception as e:
        print(f"[SceneMemory] 更新失败: {e}")

    print(f"[place] 放置完成")
    return True
