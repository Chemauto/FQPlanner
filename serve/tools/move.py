"""
move.py - 机器人底座移动控制

动作空间（12维）：
  action[7]  → forward（body X 轴，前进/后退）
  action[8]  → side（body Y 轴，左/右平移，正=左）
  action[9]  → yaw（原地旋转，正=逆时针）
  action[11] → 模式（正=底座模式）

body 坐标系随 yaw 旋转：
  yaw=0°:  body_X = 世界+X,  body_Y = 世界+Y
  yaw=90°: body_X = 世界+Y,  body_Y = 世界-X
"""

import json
import urllib.request
import urllib.error
import numpy as np

# Nav2 桥接节点地址（Docker 容器内）
NAV2_BRIDGE_URL = "http://127.0.0.1:5002"


def _normalize_angle_deg(angle):
    """角度归一化到 [-180, 180]"""
    while angle > 180:
        angle -= 360
    while angle < -180:
        angle += 360
    return angle


def _world_to_body(Vx_world, Vy_world, yaw_rad):
    """
    世界坐标系速度 → body 坐标系速度

    yaw=0° 时: body_X = 世界+X, body_Y = 世界+Y
    """
    c = np.cos(yaw_rad)
    s = np.sin(yaw_rad)
    Vx_body = Vx_world * c + Vy_world * s
    Vy_body = -Vx_world * s + Vy_world * c
    return Vx_body, Vy_body


def get_base_info(env):
    """
    获取底座全部运动相关数据

    Returns:
        dict:
            pos:       世界坐标 [x, y, z]
            yaw_deg:   朝向（度，0-360）
            yaw_rad:   朝向（弧度）
            qpos:      关节值 [forward, side, yaw]
            qvel:      关节速度 [forward, side, yaw]
            ctrl:      控制信号 [forward, side, yaw]
    """
    base_id = env.sim.model.body_name2id("mobilebase0_base")

    # 世界坐标
    pos = env.sim.data.body_xpos[base_id].copy()
    quat = env.sim.data.body_xquat[base_id]  # [w, x, y, z]
    w, x, y, z = quat
    yaw_rad = np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    yaw_deg = np.rad2deg(yaw_rad)

    # 关节值
    qpos = env.sim.data.qpos[0:3].copy()
    qvel = env.sim.data.qvel[0:3].copy()
    ctrl = env.sim.data.ctrl[7:10].copy()

    return {
        "pos": pos.tolist(),
        "yaw_deg": round(float(yaw_deg), 2),
        "yaw_rad": round(float(yaw_rad), 4),
        "qpos": qpos.tolist(),
        "qvel": qvel.tolist(),
        "ctrl": ctrl.tolist(),
    }


def move(env, Vx=0.0, Vy=0.0, Vw=0.0):
    """
    底座速度控制（一步）

    Args:
        env: 环境对象
        Vx:  前进速度 [-1, 1]，body X 轴方向（前进为正）
        Vy:  侧移速度 [-1, 1]，body Y 轴方向（左移为正）
        Vw:  旋转速度 [-1, 1]，逆时针为正

    Returns:
        dict: 执行后的底座状态（同 get_base_info）
    """
    Vx = np.clip(Vx, -1.0, 1.0)
    Vy = np.clip(Vy, -1.0, 1.0)
    Vw = np.clip(Vw, -1.0, 1.0)

    action = np.zeros(env.action_dim)
    action[7] = Vx
    action[8] = Vy
    action[9] = Vw
    action[11] = 1.0  # 底座模式

    env.step(action)

    return get_base_info(env)


def nav(env, x, y, w, yaw, Kp=2, Kd=0.3, pos_threshold=0.1, yaw_threshold=3.0, max_steps=500):
    """
    导航到世界坐标系目标点（顺序消除误差：x → y → w）

    Args:
        env:            环境对象
        x:              目标世界坐标 x
        y:              目标世界坐标 y
        w:              目标偏航角（度）
        yaw:            当前偏航角（度）
        Kp:             比例增益
        Kd:             微分增益
        pos_threshold:  位置误差阈值（米），默认 0.1
        yaw_threshold:  偏航角误差阈值（度），默认 3.0
        max_steps:      每个阶段最大步数

    Returns:
        dict: 最终底座状态
    """
    # 阶段 1：消除 x 误差
    prev_err = 0.0
    for step in range(max_steps):
        info = get_base_info(env)
        x_now = info["pos"][0]
        err = x - x_now
        if abs(err) < pos_threshold:
            break
        d_err = err - prev_err
        prev_err = err
        Vx_world = np.clip(Kp * err + Kd * d_err, -1.0, 1.0)
        Vx_body, Vy_body = _world_to_body(Vx_world, 0.0, info["yaw_rad"])
        move(env, Vx=Vx_body, Vy=Vy_body)

    # 阶段 2：消除 y 误差
    prev_err = 0.0
    for step in range(max_steps):
        info = get_base_info(env)
        y_now = info["pos"][1]
        err = y - y_now
        if abs(err) < pos_threshold:
            break
        d_err = err - prev_err
        prev_err = err
        Vy_world = np.clip(Kp * err + Kd * d_err, -1.0, 1.0)
        Vx_body, Vy_body = _world_to_body(0.0, Vy_world, info["yaw_rad"])
        move(env, Vx=Vx_body, Vy=Vy_body)

    # 阶段 3：消除 w 误差
    prev_err = 0.0
    for step in range(max_steps):
        info = get_base_info(env)
        w_now = info["yaw_deg"]
        err = _normalize_angle_deg(w - w_now)
        if abs(err) < yaw_threshold:
            break
        d_err = err - prev_err
        prev_err = err
        Vw = np.clip(Kp * (err / 180.0) + Kd * (d_err / 180.0), -1.0, 1.0)
        move(env, Vw=Vw)

    return get_base_info(env)


def follow_path(
    env,
    path,
    w=0,
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
    Follow a Nav2 global path with an omnidirectional PD controller.

    Nav2 is used only for global planning. This function converts path waypoints
    in map/world coordinates into MuJoCo body-frame velocity actions.
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

    # Final yaw alignment.
    for _ in range(300):
        info = get_base_info(env)
        err_w = _normalize_angle_deg(float(w) - info["yaw_deg"])
        if abs(err_w) < yaw_threshold:
            break
        Vw = np.clip(Kp_yaw * (err_w / 90.0), -max_turn, max_turn)
        move(env, Vw=Vw)

    info = get_base_info(env)
    final_err = float(np.hypot(points[-1][0] - info["pos"][0], points[-1][1] - info["pos"][1]))
    return {
        "success": final_err < max(goal_threshold * 1.5, 0.2),
        "pos": info["pos"],
        "yaw": info["yaw_deg"],
        "goal_error": final_err,
        "waypoints": len(points),
    }


# ============================================================
# Nav2 导航
# ============================================================

def nav2_available():
    """检测 Nav2 桥接节点是否在线"""
    try:
        req = urllib.request.Request(f"{NAV2_BRIDGE_URL}/navigate", method="GET")
        with urllib.request.urlopen(req, timeout=1):
            return True
    except Exception:
        return False


def nav_nav2(x, y, w, timeout=120):
    """
    通过 Nav2 桥接节点导航到目标位置

    Args:
        x:       目标世界坐标 x
        y:       目标世界坐标 y
        w:       目标偏航角（度）
        timeout: 超时时间（秒）

    Returns:
        dict: {"success": bool, "pos": [x,y,z], "yaw": float, "result": str}
    """
    data = json.dumps({"x": x, "y": y, "w": w, "timeout": timeout}).encode("utf-8")
    try:
        req = urllib.request.Request(
            f"{NAV2_BRIDGE_URL}/navigate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout + 10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"success": False, "result": f"Nav2 请求失败: {e}"}
