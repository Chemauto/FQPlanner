"""
move.py - 机器人底座移动控制

XLeRobot 差速驱动模型：2 个 motor actuator 通过 tendon 控制轮子。
ctrl[0] = forward (前进/后退), ctrl[1] = turn (左转/右转)
与 MuJoCo-GS-Web 实物接口一致。
"""

import sys

import numpy as np
import mujoco


def _normalize_angle(angle):
    """角度归一化到 [-pi, pi]"""
    return float(np.arctan2(np.sin(angle), np.cos(angle)))


def _normalize_angle_deg(angle):
    """角度归一化到 [-180, 180]"""
    while angle > 180:
        angle -= 360
    while angle < -180:
        angle += 360
    return angle


def get_base_info(env):
    """
    获取底座全部运动相关数据

    Returns:
        dict:
            pos:       世界坐标 [x, y, z]
            yaw_deg:   朝向（度）
            yaw_rad:   朝向（弧度）
            qpos:      关节值 [x, y, yaw]
            qvel:      关节速度 [vx, vy, vyaw]
            ctrl:      控制信号 [forward, turn, ...]
    """
    model = env.sim.model
    data = env.sim.data
    base_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "chassis")

    pos = data.xpos[base_id].copy()
    quat = data.xquat[base_id]
    w, x, y, z = quat
    yaw_rad = np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    yaw_deg = np.rad2deg(yaw_rad)

    qpos = [float(pos[0]), float(pos[1]), float(yaw_rad)]
    qvel = [0.0, 0.0, 0.0]
    if getattr(env, "base_free_joint_id", -1) >= 0:
        dadr = model.jnt_dofadr[env.base_free_joint_id]
        qvel = data.qvel[dadr:dadr + 3].copy().tolist()
    ctrl = data.ctrl[:min(env.model.nu, data.ctrl.size)].copy().tolist()

    return {
        "pos": pos.tolist(),
        "yaw_deg": round(float(yaw_deg), 2),
        "yaw_rad": round(float(yaw_rad), 4),
        "qpos": qpos,
        "qvel": qvel,
        "ctrl": ctrl,
    }


def move(env, Vx=0.0, Vy=0.0, Vw=0.0):
    """
    底座速度控制（一步）

    差速驱动：ctrl[0]=forward, ctrl[1]=turn
    Vy 被忽略（差速驱动物理上不能侧移）

    Args:
        env: 环境对象
        Vx:  前进速度 [-1, 1]，body X 轴方向（前进为正）
        Vy:  忽略（差速驱动不支持侧移）
        Vw:  旋转速度 [-1, 1]，逆时针为正

    Returns:
        dict: 执行后的底座状态
    """
    forward = np.clip(Vx, -1.0, 1.0)
    # MuJoCo tendon sign is opposite to the public Vw convention.
    turn = -np.clip(Vw, -1.0, 1.0)

    env.data.ctrl[0] = forward
    env.data.ctrl[1] = turn
    env.step()

    return get_base_info(env)


def stop_base(env):
    """Stop commanded base motion and clear residual chassis/wheel velocity."""
    env.data.ctrl[0] = 0.0
    env.data.ctrl[1] = 0.0

    if getattr(env, "base_free_joint_id", -1) >= 0:
        dadr = env.model.jnt_dofadr[env.base_free_joint_id]
        env.data.qvel[dadr:dadr + 6] = 0.0

    for joint_name in ("left_wheel_joint", "right_wheel_joint"):
        joint_id = mujoco.mj_name2id(env.model, mujoco.mjtObj.mjOBJ_JOINT, joint_name)
        if joint_id >= 0:
            dadr = env.model.jnt_dofadr[joint_id]
            env.data.qvel[dadr] = 0.0

    env.sim.forward()
    return get_base_info(env)


def nav(env, x, y, target_yaw=None, Kp=2.5, Kd=0.3, pos_threshold=0.1, yaw_threshold=3.0, max_steps=800):
    """
    导航到世界坐标系目标点（差速驱动 PD 控制）

    差速驱动不能侧移，策略：
    1. 计算到目标的方向偏差 (heading_error)
    2. 同时输出 forward 和 turn，大偏差时衰减前进速度先转向

    Args:
        env:            环境对象
        x:              目标世界坐标 x
        y:              目标世界坐标 y
        target_yaw:     目标偏航角（度），None 表示不调整朝向
        Kp:             比例增益
        Kd:             微分增益
        pos_threshold:  位置误差阈值（米），默认 0.1
        yaw_threshold:  偏航角误差阈值（度），默认 3.0
        max_steps:      最大步数

    Returns:
        dict: 最终底座状态，含 "reached" 字段表示是否真正到达目标
    """
    prev_heading_err = 0.0
    prev_pos_err = 0.0
    reached = False

    for _ in range(max_steps):
        info = get_base_info(env)
        x_now, y_now = info["pos"][0], info["pos"][1]
        yaw_now = info["yaw_rad"]

        err_x = x - x_now
        err_y = y - y_now
        pos_err = float(np.hypot(err_x, err_y))

        # 到位后检查朝向
        if pos_err < pos_threshold:
            if target_yaw is None:
                reached = True
                break
            yaw_err_deg = _normalize_angle_deg(target_yaw - info["yaw_deg"])
            if abs(yaw_err_deg) < yaw_threshold:
                reached = True
                break
            # 原地转向到目标朝向
            Vw = np.clip(Kp * (yaw_err_deg / 90.0), -1.0, 1.0)
            move(env, Vx=0.0, Vw=Vw)
            continue

        # 计算到目标的世界方向
        angle_to_target = np.arctan2(err_y, err_x)
        heading_err = _normalize_angle(angle_to_target - yaw_now)

        # PD 控制
        d_heading = heading_err - prev_heading_err
        prev_heading_err = heading_err
        d_pos = pos_err - prev_pos_err
        prev_pos_err = pos_err

        turn = np.clip(Kp * heading_err + Kd * d_heading, -1.0, 1.0)

        # 前进速度：距离越远越快，朝向偏差大时衰减
        forward = np.clip(Kp * pos_err, -1.0, 1.0)
        forward *= max(0.0, np.cos(heading_err))
        forward = np.clip(forward + Kd * d_pos * 0.1, -1.0, 1.0)

        move(env, Vx=forward, Vw=turn)

    # 最终朝向对齐
    if target_yaw is not None:
        for _ in range(200):
            info = get_base_info(env)
            yaw_err_deg = _normalize_angle_deg(target_yaw - info["yaw_deg"])
            if abs(yaw_err_deg) < yaw_threshold:
                break
            Vw = np.clip(Kp * (yaw_err_deg / 90.0), -1.0, 1.0)
            move(env, Vx=0.0, Vw=Vw)

    info = get_base_info(env)
    info["reached"] = reached
    return info


def follow_path(
    env,
    path,
    w=None,
    waypoint_threshold=0.18,
    goal_threshold=0.12,
    yaw_threshold=5.0,
    max_steps=3000,
    Kp_xy=1.4,
    Kd_xy=0.15,
    Kp_yaw=1.0,
    max_speed=0.45,
    max_turn=0.25,
):
    """
    Follow a global path with an omnidirectional PD controller.

    Converts path waypoints in world coordinates into MuJoCo body-frame
    velocity actions.
    """
    if not path:
        return {"success": False, "result": "空路径"}

    points = [(float(p["x"]), float(p["y"])) for p in path]
    index = 0
    prev_err_x = 0.0
    prev_err_y = 0.0

    for _ in range(max_steps):
        info = get_base_info(env)
        x_now, y_now = info["pos"][0], info["pos"][1]

        while index < len(points) - 1:
            dist = float(np.hypot(points[index][0] - x_now, points[index][1] - y_now))
            if dist > waypoint_threshold:
                break
            index += 1

        target_x, target_y = points[index]
        err_x = target_x - x_now
        err_y = target_y - y_now
        goal_err = float(np.hypot(points[-1][0] - x_now, points[-1][1] - y_now))

        if index == len(points) - 1 and goal_err < goal_threshold:
            break

        d_err_x = err_x - prev_err_x
        d_err_y = err_y - prev_err_y
        prev_err_x = err_x
        prev_err_y = err_y

        Vx_world = Kp_xy * err_x + Kd_xy * d_err_x
        Vy_world = Kp_xy * err_y + Kd_xy * d_err_y
        speed = float(np.hypot(Vx_world, Vy_world))
        if speed > max_speed:
            Vx_world = Vx_world / speed * max_speed
            Vy_world = Vy_world / speed * max_speed

        Vx_body, Vy_body = _world_to_body(Vx_world, Vy_world, info["yaw_rad"])
        move(env, Vx=Vx_body, Vy=Vy_body, Vw=0.0)

    # Final alignment: combined position+yaw using nav() so there is no
    # drift from a separate spin-then-correct sequence.
    target_yaw = float(w) if w is not None else None
    final_info = nav(
        env,
        points[-1][0], points[-1][1],
        target_yaw=target_yaw,
        Kp=2.0, Kd=0.2,
        pos_threshold=goal_threshold,
        yaw_threshold=yaw_threshold,
        max_steps=600,
    )
    final_err = float(np.hypot(
        points[-1][0] - final_info["pos"][0],
        points[-1][1] - final_info["pos"][1],
    ))
    if target_yaw is not None:
        yaw_err = abs(_normalize_angle_deg(target_yaw - final_info["yaw_deg"]))
        success = final_err < 0.30 and yaw_err < 15.0
    else:
        success = final_err < 0.30
    print(
        f"[follow_path] 到达误差={final_err:.3f}m yaw_err={abs(_normalize_angle_deg(target_yaw - final_info['yaw_deg'])):.1f}° 成功={success}"
        if target_yaw is not None else
        f"[follow_path] 到达误差={final_err:.3f}m 成功={success}",
        file=sys.stderr,
    )
    return {
        "success": success,
        "pos": final_info["pos"],
        "yaw": final_info["yaw_deg"],
        "goal_error": final_err,
        "waypoints": len(points),
    }
