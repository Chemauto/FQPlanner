"""
move.py - 机器人底座移动控制

BlueThink 差速驱动：4 个 wheel velocity actuator
ctrl[14:18] = ZQL(FR), ZHL(RR), YQL(FL), YHL(RL)
"""

import math
import numpy as np
import mujoco


def _normalize_angle(angle):
    return float(np.arctan2(np.sin(angle), np.cos(angle)))


def _normalize_angle_deg(angle):
    while angle > 180:
        angle -= 360
    while angle < -180:
        angle += 360
    return angle


def base_link_yaw_from_chassis_yaw(yaw_rad):
    """Convert MuJoCo chassis yaw to the public ROS/base_link heading."""
    return _normalize_angle(float(yaw_rad) + math.pi)


def base_link_yaw_deg_from_chassis_yaw_deg(yaw_deg):
    """Convert MuJoCo chassis yaw degrees to the public ROS/base_link heading."""
    return _normalize_angle_deg(float(yaw_deg) + 180.0)


def _get_chassis_body_id(model):
    return mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "YD_link")


def get_base_info(env):
    """获取底座全部运动相关数据"""
    model = env.sim.model
    data = env.sim.data
    base_id = _get_chassis_body_id(model)

    pos = data.xpos[base_id].copy()
    quat = data.xquat[base_id]
    w, x, y, z = quat
    yaw_rad = np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    yaw_deg = np.rad2deg(yaw_rad)
    base_link_yaw_rad = base_link_yaw_from_chassis_yaw(yaw_rad)
    base_link_yaw_deg = base_link_yaw_deg_from_chassis_yaw_deg(yaw_deg)

    qpos = [float(pos[0]), float(pos[1]), float(yaw_rad)]
    qvel = [0.0, 0.0, 0.0]
    qvel_raw = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    if getattr(env, "base_free_joint_id", -1) >= 0:
        dadr = model.jnt_dofadr[env.base_free_joint_id]
        full = data.qvel[dadr:dadr + 6].tolist()
        cos_y = math.cos(base_link_yaw_rad)
        sin_y = math.sin(base_link_yaw_rad)
        vx_world = full[0]
        vy_world = full[1]
        body_vx = vx_world * cos_y + vy_world * sin_y
        body_vy = -vx_world * sin_y + vy_world * cos_y
        qvel = [body_vx, body_vy, full[5]]
        qvel_raw = full
    ctrl = data.ctrl[:min(env.model.nu, data.ctrl.size)].copy().tolist()

    return {
        "pos": pos.tolist(),
        "yaw_deg": round(float(yaw_deg), 2),
        "yaw_rad": round(float(yaw_rad), 4),
        "base_link_yaw_deg": round(float(base_link_yaw_deg), 2),
        "base_link_yaw_rad": round(float(base_link_yaw_rad), 4),
        "qpos": qpos,
        "qvel": qvel,
        "qvel_raw": qvel_raw,
        "ctrl": ctrl,
    }


def _set_wheels(data, vx, wz):
    """BlueThink differential drive: ctrl[14:18]"""
    scale = 10.0
    right = vx * scale + wz * scale
    left  = vx * scale - wz * scale
    data.ctrl[14] = right
    data.ctrl[15] = right
    data.ctrl[16] = left
    data.ctrl[17] = left


def move(env, Vx=0.0, Vy=0.0, Vw=0.0):
    """底座速度控制（一步）"""
    _set_wheels(env.data, np.clip(Vx, -1, 1), np.clip(Vw, -1, 1))
    env.step()
    return get_base_info(env)


def stop_base(env):
    """Stop base motion."""
    _set_wheels(env.data, 0.0, 0.0)
    if getattr(env, "base_free_joint_id", -1) >= 0:
        dadr = env.model.jnt_dofadr[env.base_free_joint_id]
        env.data.qvel[dadr:dadr + 6] = 0.0
    for name in ("ZQL", "ZHL", "YQL", "YHL"):
        jid = mujoco.mj_name2id(env.model, mujoco.mjtObj.mjOBJ_JOINT, name)
        if jid >= 0:
            env.data.qvel[env.model.jnt_dofadr[jid]] = 0.0
    env.sim.forward()
    return get_base_info(env)


def nav(env, x, y, target_yaw=None, Kp=2.5, Kd=0.3, pos_threshold=0.1, yaw_threshold=3.0, max_steps=800):
    """导航到世界坐标系目标点（差速驱动 PD 控制）"""
    prev_heading_err = 0.0
    prev_pos_err = 0.0

    for _ in range(max_steps):
        info = get_base_info(env)
        x_now, y_now = info["pos"][0], info["pos"][1]
        yaw_now = info.get("base_link_yaw_rad", base_link_yaw_from_chassis_yaw(info["yaw_rad"]))

        err_x = x - x_now
        err_y = y - y_now
        pos_err = float(np.hypot(err_x, err_y))

        if pos_err < pos_threshold:
            if target_yaw is None:
                break
            current_yaw_deg = info.get(
                "base_link_yaw_deg",
                base_link_yaw_deg_from_chassis_yaw_deg(info["yaw_deg"]),
            )
            yaw_err_deg = _normalize_angle_deg(target_yaw - current_yaw_deg)
            if abs(yaw_err_deg) < yaw_threshold:
                break
            Vw = np.clip(Kp * (yaw_err_deg / 90.0), -1.0, 1.0)
            move(env, Vx=0.0, Vw=Vw)
            continue

        angle_to_target = np.arctan2(err_y, err_x)
        heading_err = _normalize_angle(angle_to_target - yaw_now)

        d_heading = heading_err - prev_heading_err
        prev_heading_err = heading_err
        d_pos = pos_err - prev_pos_err
        prev_pos_err = pos_err

        turn = np.clip(Kp * heading_err + Kd * d_heading, -1.0, 1.0)
        forward = np.clip(Kp * pos_err, -1.0, 1.0)
        forward *= max(0.0, np.cos(heading_err))
        forward = np.clip(forward + Kd * d_pos * 0.1, -1.0, 1.0)

        move(env, Vx=forward, Vw=turn)

    if target_yaw is not None:
        for _ in range(200):
            info = get_base_info(env)
            current_yaw_deg = info.get(
                "base_link_yaw_deg",
                base_link_yaw_deg_from_chassis_yaw_deg(info["yaw_deg"]),
            )
            yaw_err_deg = _normalize_angle_deg(target_yaw - current_yaw_deg)
            if abs(yaw_err_deg) < yaw_threshold:
                break
            Vw = np.clip(Kp * (yaw_err_deg / 90.0), -1.0, 1.0)
            move(env, Vx=0.0, Vw=Vw)

    return get_base_info(env)
