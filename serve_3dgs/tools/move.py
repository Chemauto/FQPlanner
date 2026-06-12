"""move.py - Robot base movement control (MotrixSim backend)."""

import math
import numpy as np


def _normalize_angle(angle):
    return float(np.arctan2(np.sin(angle), np.cos(angle)))


def _normalize_angle_deg(angle):
    while angle > 180:
        angle -= 360
    while angle < -180:
        angle += 360
    return angle


def base_link_yaw_from_chassis_yaw(yaw_rad):
    return _normalize_angle(float(yaw_rad) + math.pi)


def base_link_yaw_deg_from_chassis_yaw_deg(yaw_deg):
    return _normalize_angle_deg(float(yaw_deg) + 180.0)


def _get_floating_base(env):
    if env.model.floating_bases:
        return env.model.floating_bases[0]
    return None


def get_base_info(env):
    fb = _get_floating_base(env)
    if fb is None:
        return {
            "pos": [0.0, 0.0, 0.0],
            "yaw_deg": 0.0,
            "yaw_rad": 0.0,
            "base_link_yaw_deg": 0.0,
            "base_link_yaw_rad": math.pi,
            "qvel": [0.0, 0.0, 0.0],
        }

    pos = np.asarray(fb.get_translation(env.data), dtype=float).reshape(-1)
    quat = np.asarray(fb.get_rotation(env.data), dtype=float).reshape(-1)
    qi, qj, qk, qw = quat

    yaw_rad = np.arctan2(2.0 * (qw * qk + qi * qj), 1.0 - 2.0 * (qj * qj + qk * qk))
    yaw_deg = np.rad2deg(yaw_rad)
    base_link_yaw_rad = base_link_yaw_from_chassis_yaw(yaw_rad)
    base_link_yaw_deg = base_link_yaw_deg_from_chassis_yaw_deg(yaw_deg)

    vel = np.asarray(fb.get_dof_vel(env.data), dtype=float).reshape(-1)
    cos_y = math.cos(base_link_yaw_rad)
    sin_y = math.sin(base_link_yaw_rad)
    vx_world, vy_world = vel[0], vel[1]
    body_vx = vx_world * cos_y + vy_world * sin_y
    body_vy = -vx_world * sin_y + vy_world * cos_y
    wz = vel[5] if len(vel) > 5 else 0.0

    return {
        "pos": pos.tolist(),
        "yaw_deg": round(float(yaw_deg), 2),
        "yaw_rad": round(float(yaw_rad), 4),
        "base_link_yaw_deg": round(float(base_link_yaw_deg), 2),
        "base_link_yaw_rad": round(float(base_link_yaw_rad), 4),
        "qvel": [float(body_vx), float(body_vy), float(wz)],
    }


def set_base_velocity(env, vx=0.0, vy=0.0, wz=0.0):
    fb = _get_floating_base(env)
    if fb is None:
        return
    info = get_base_info(env)
    bl_yaw = info["base_link_yaw_rad"]
    cos_y = math.cos(bl_yaw)
    sin_y = math.sin(bl_yaw)
    vx_world = vx * cos_y - vy * sin_y
    vy_world = vx * sin_y + vy * cos_y

    data = env.data
    lin_vel = np.array([[vx_world, vy_world, 0.0]], dtype=np.float64)
    ang_vel = np.array([[0.0, 0.0, wz]], dtype=np.float64)
    fb.set_global_linear_velocity(data, lin_vel)
    fb.set_global_angular_velocity(data, ang_vel)


def move(env, Vx=0.0, Vy=0.0, Vw=0.0, steps=1):
    set_base_velocity(env, Vx, Vy, Vw)
    env.step(steps)
    return get_base_info(env)


def stop_base(env):
    set_base_velocity(env, 0.0, 0.0, 0.0)
    return get_base_info(env)


def nav(env, x, y, target_yaw=None, Kp=2.5, Kd=0.3, pos_threshold=0.1, yaw_threshold=3.0, max_steps=800):
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
