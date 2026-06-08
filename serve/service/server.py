"""
server.py - Flask API 服务
通过命令队列与仿真器主循环通信，避免多线程同时调用 env.step()
"""

import os
import sys
import time
import threading
import numpy as np
import mujoco
import yaml
from pathlib import Path
from flask import Flask, request, jsonify, Response, send_file
from flask_cors import CORS

from tools.arm import (
    get_arm_info, get_obj_pos,
    move_arm,
    open_gripper, close_gripper, is_grasped,
)
from tools.move import get_base_info, nav, move, stop_base, follow_path
from scene.scene_memory import coords_to_waypoint, get_all_locations, move_object

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from serve_real.base_bridge import start_move_duration, stop_real_base
except Exception as e:
    print(f"[real_base] bridge 未启用: {e}", flush=True)

    def start_move_duration(vx, duration, vw=0.0):
        return None

    def stop_real_base():
        return None

app = Flask(__name__)
CORS(app)

_env_holder = {"env": None}
_cmd_queue = []      # 命令队列
_results = {}        # 命令结果缓存
_active_command = None
_queue_lock = threading.Lock()
_env_lock = threading.RLock()
_base_cmd = {
    "Vx": 0.0,
    "Vy": 0.0,
    "Vw": 0.0,
    "expires_at": 0.0,
    "last_log_at": 0.0,
    "was_active": False,
}
_base_status_cache = {}

NAV_SUBSTEPS = 5  # 每主循环迭代执行 5 步，提高导航响应速度
ARM_STEP = 0.025

# 右臂预设姿态: [Rotation_R, Pitch_R, Elbow_R, Wrist_Pitch_R, Wrist_Roll_R, Jaw_R]
_ARM_POSE_NEUTRAL = [0.0, 2.0, 0.5, -0.3, 0.0, 0.0]   # 待机
_ARM_POSE_REACH   = [0.0, 2.5, 1.5, -0.8, 0.0, 0.0]   # 伸手抓取（夹爪张开）
_ARM_POSE_HOLD    = [0.0, 2.0, 0.8, -0.4, 0.0, 1.2]   # 持物（夹爪闭合）
_R_ARM_ACT_NAMES  = ["Rotation_R", "Pitch_R", "Elbow_R", "Wrist_Pitch_R", "Wrist_Roll_R", "Jaw_R"]

# 录制状态
_recording = {
    "active": False,
    "frames": [],
    "fps": 1,
    "view_height": 240,
    "view_width": 320,
    "last_capture": 0,
    "interval": 1.0,
}

RECORD_CAMERAS = [
    ("overhead_cam",   "Top",         False),
    ("head_cam",       "Head",        False),
    ("right_arm_cam",  "Right wrist", False),
    ("left_arm_cam",   "Left wrist",  False),
]

_video_dir = os.path.join(os.path.dirname(__file__), "..", "videos")
_camera_config_cache = None


def _camera_config():
    global _camera_config_cache
    if _camera_config_cache is None:
        scene_dir = "scene"
        env = _get_env()
        if env is not None:
            scene_dir = env.scene_dir
        path = os.path.join(os.path.abspath(scene_dir), "config", "camera.yaml")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                _camera_config_cache = yaml.safe_load(f) or {}
        else:
            _camera_config_cache = {}
    return _camera_config_cache


def _screenshot_defaults():
    return (_camera_config().get("screenshot", {}) or {})


def _preview_config():
    return (_camera_config().get("preview", {}) or {})


def _camera_labels():
    return {
        name: values.get("label", name)
        for name, values in (_camera_config().get("cameras", {}) or {}).items()
        if isinstance(values, dict)
    }


def _render_combined_frame(env, view_w, view_h):
    from PIL import Image, ImageDraw
    panels = []
    for cam_name, label, flip in RECORD_CAMERAS:
        try:
            img = env.sim.render(view_w, view_h, camera_name=cam_name)
            if img is None:
                img = np.zeros((view_h, view_w, 3), dtype=np.uint8)
            elif flip:
                img = np.flipud(img)
        except Exception:
            img = np.zeros((view_h, view_w, 3), dtype=np.uint8)
        pil_img = Image.fromarray(img)
        draw = ImageDraw.Draw(pil_img)
        draw.rectangle([0, 0, len(label) * 8 + 12, 18], fill=(0, 0, 0))
        draw.text((5, 2), label, fill=(255, 255, 255))
        panels.append(np.array(pil_img))
    top = np.hstack([panels[0], panels[1]])
    bottom = np.hstack([panels[2], panels[3]])
    return np.vstack([top, bottom])


def _render_camera_preview(env, camera_names, width, height):
    from PIL import Image, ImageDraw
    labels = _camera_labels()
    panels = []
    for name in camera_names:
        try:
            img = env.sim.render(width, height, camera_name=name)
        except Exception:
            img = np.zeros((height, width, 3), dtype=np.uint8)
        panel = Image.fromarray(img)
        label = labels.get(name, name)
        draw = ImageDraw.Draw(panel)
        draw.rectangle([0, 0, len(label) * 8 + 12, 20], fill=(0, 0, 0))
        draw.text((5, 3), label, fill=(255, 255, 255))
        panels.append(panel)
    return panels


def try_record_frame():
    if not _recording["active"]:
        return
    now = time.time()
    if now - _recording["last_capture"] < _recording["interval"]:
        return
    env = _get_env()
    if env is None:
        return
    try:
        combined = _render_combined_frame(
            env, _recording["view_width"], _recording["view_height"]
        )
        _recording["frames"].append(combined)
        _recording["last_capture"] = now
        if len(_recording["frames"]) == 1:
            print(f"[record] 首帧捕获成功: shape={combined.shape}", flush=True)
    except Exception as e:
        print(f"[record] 渲染帧失败: {e}", flush=True)


def get_lock():
    return _env_lock


def has_active_base_command():
    """当前是否有正在执行的底盘命令 (nav/cmd_vel/move_duration)"""
    return _active_command is not None and _active_command.get("type") in ("nav", "cmd_vel", "move_duration")


def set_base_velocity(Vx=0.0, Vy=0.0, Vw=0.0, timeout=0.25):
    """Store the latest velocity command for the main simulation loop."""
    print(f"[set_base_velocity] Vx={Vx}, Vw={Vw}, timeout={timeout}", flush=True)
    with _queue_lock:
        _base_cmd["Vx"] = float(Vx)
        _base_cmd["Vy"] = float(Vy)
        _base_cmd["Vw"] = float(Vw)
        _base_cmd["expires_at"] = time.time() + timeout
        now = time.time()
        if now - _base_cmd["last_log_at"] > 1.0:
            print(
                f"[cmd_vel] Vx={_base_cmd['Vx']:.3f}, Vy={_base_cmd['Vy']:.3f}, Vw={_base_cmd['Vw']:.3f}",
                flush=True,
            )
            _base_cmd["last_log_at"] = now


def get_base_action():
    """返回当前底座速度命令 [forward, turn]，不包含手臂 ctrl。

    cmd_vel 过期后返回 None，主循环不写 ctrl，保留 viewer 手动控制值。
    过期瞬间返回一次 [0, 0] 以确保机器人停止。
    """
    with _queue_lock:
        if time.time() > _base_cmd["expires_at"]:
            if _base_cmd["was_active"]:
                _base_cmd["was_active"] = False
                print("[get_base_action] cmd_vel 过期，返回停止信号 [0,0]", flush=True)
                return np.zeros(2)
            return None
        _base_cmd["was_active"] = True
        action = np.zeros(2)
        action[0] = np.clip(_base_cmd["Vx"], -1.0, 1.0)   # forward
        action[1] = -np.clip(_base_cmd["Vw"], -1.0, 1.0)   # turn
        return action


def _get_env():
    return _env_holder["env"]


def _read_base_info(env):
    info = get_base_info(env)
    _base_status_cache.clear()
    _base_status_cache.update(_np_to_list(info))
    return info


def _is_body_descendant(model, body_id, ancestor_id):
    current = int(body_id)
    ancestor_id = int(ancestor_id)
    while current > 0:
        if current == ancestor_id:
            return True
        current = int(model.body_parentid[current])
    return False


def _np_to_list(obj):
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, dict):
        return {k: _np_to_list(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_np_to_list(v) for v in obj]
    return obj


def submit_command(cmd_type, params):
    """
    提交命令到队列，等待执行结果
    Returns: dict 结果
    """
    event = threading.Event()
    cmd_id = id(event)
    cmd = {
        "id": cmd_id,
        "type": cmd_type,
        "params": params,
        "event": event,
    }
    with _queue_lock:
        _cmd_queue.append(cmd)
    event.wait(timeout=120)  # 最多等 120 秒
    with _queue_lock:
        result = _results.pop(cmd_id, {"error": "超时"})
    return result


def _finish_command(cmd, result):
    global _active_command
    if cmd.get("type") in ("nav", "cmd_vel", "move_duration"):
        env = _get_env()
        if env is not None:
            try:
                _read_base_info(env)
            except Exception:
                pass
    with _queue_lock:
        _results[cmd["id"]] = result
    cmd["event"].set()
    _active_command = None


def _normalize_angle_deg(angle):
    return (float(angle) + 180.0) % 360.0 - 180.0


def _step_active_command(env):
    cmd = _active_command
    if cmd is None:
        return False
    try:
        cmd_type = cmd["type"]
        state = cmd["state"]
        if cmd_type == "nav":
            for _ in range(NAV_SUBSTEPS):
                info = get_base_info(env)
                x_now, y_now = info["pos"][0], info["pos"][1]
                yaw_now = info["yaw_rad"]
                err_x = state["x"] - x_now
                err_y = state["y"] - y_now
                pos_err = float(np.hypot(err_x, err_y))
                yaw_err = 0.0
                yaw_done = state["target_yaw"] is None
                if state["target_yaw"] is not None:
                    yaw_err = _normalize_angle_deg(state["target_yaw"] - info["yaw_deg"])
                    yaw_done = abs(yaw_err) < state["yaw_threshold"]
                if pos_err < state["pos_threshold"] and yaw_done:
                    final = get_base_info(env)
                    _finish_command(cmd, {"success": True, "pos": final["pos"], "yaw": final["yaw_deg"]})
                    return True
                if state["step"] >= state["max_steps"]:
                    final = get_base_info(env)
                    _finish_command(cmd, {"success": False, "pos": final["pos"], "yaw": final["yaw_deg"], "result": "导航超时"})
                    return True
                # 差速驱动 PD 控制（含 Kd 阻尼，防止航向抖动）
                if pos_err >= state["pos_threshold"]:
                    angle_to_target = np.arctan2(err_y, err_x)
                    heading_err = float(np.arctan2(
                        np.sin(angle_to_target - yaw_now),
                        np.cos(angle_to_target - yaw_now),
                    ))
                    Kp = state["kp"]
                    Kd = state.get("kd", 0.25)
                    d_h = heading_err - state["prev_heading_err"]
                    state["prev_heading_err"] = heading_err
                    turn = float(np.clip(Kp * heading_err + Kd * d_h, -1.0, 1.0))
                    forward = float(np.clip(Kp * pos_err, -0.8, 0.8))
                    forward *= max(0.0, float(np.cos(heading_err)))
                    move(env, Vx=forward, Vw=turn)
                else:
                    Vw = float(np.clip(1.5 * (yaw_err / 90.0), -1.0, 1.0))
                    move(env, Vx=0.0, Vw=Vw)
                _sync_ee_to_base(env)
                state["step"] += 1
            return True

        if cmd_type == "move_duration":
            now = time.time()
            if now >= state["end_time"]:
                print(f"[move_duration] 时间到，发送停止信号", flush=True)
                # timeout 需要 >0，让主循环 get_base_action 有机会设置 was_active=True
                # 然后返回 [0,0] 停止信号；过期后自动变 None 不再干预
                set_base_velocity(Vx=0.0, Vw=0.0, timeout=1.0)
                stop_base(env)
                stop_real_base()
                final = get_base_info(env)
                _finish_command(cmd, {"success": True, "pos": final["pos"], "yaw": final["yaw_deg"]})
                return True
            move(env, Vx=state["vx"], Vw=state["vw"])
            return True

        if cmd_type == "grasp":
            obj_name = state["obj_name"]
            if obj_name not in env.obj_body_id:
                _finish_command(cmd, {"success": False, "result": f"物体 {obj_name} 不存在"})
                return True
            if state["phase"] == "approach":
                target = env.get_object_pos(obj_name).copy()
                target[2] += 0.04
                _apply_right_arm_pose(env, _ARM_POSE_REACH)
                if _move_virtual_ee(env, target):
                    env.grasped_object = obj_name
                    state["phase"] = "lift"
                    state["lift_target"] = target + np.array([0.0, 0.0, 0.20])
                return True
            if state["phase"] == "lift":
                _apply_right_arm_pose(env, _ARM_POSE_HOLD)
                if _move_virtual_ee(env, state["lift_target"]):
                    try:
                        move_object(obj_name, "robot_hand")
                    except Exception as e:
                        print(f"[SceneMemory] 更新失败: {e}", flush=True)
                    _finish_command(cmd, {"success": True, "result": f"成功抓取 {obj_name}"})
                return True

        if cmd_type == "place":
            obj_name = state["obj_name"]
            if obj_name not in env.obj_body_id:
                _finish_command(cmd, {"success": False, "result": f"物体 {obj_name} 不存在"})
                return True
            if state["phase"] == "move":
                _apply_right_arm_pose(env, _ARM_POSE_HOLD)
                if env.grasped_object != obj_name:
                    env.grasped_object = obj_name
                if _move_virtual_ee(env, state["target_pos"]):
                    env.set_object_pos(obj_name, state["target_pos"])
                    env.grasped_object = None
                    state["phase"] = "retreat"
                    state["retreat_target"] = state["target_pos"] + np.array([0.0, 0.0, 0.20])
                return True
            if state["phase"] == "retreat":
                _apply_right_arm_pose(env, _ARM_POSE_NEUTRAL)
                if _move_virtual_ee(env, state["retreat_target"]):
                    try:
                        waypoint_name = coords_to_waypoint(state["target_pos"].tolist())
                        move_object(obj_name, waypoint_name)
                    except Exception as e:
                        print(f"[SceneMemory] 更新失败: {e}", flush=True)
                    _finish_command(cmd, {"success": True, "result": f"成功放置 {obj_name}"})
                return True

        if cmd_type == "nav_path":
            points = state["points"]
            if not points:
                _finish_command(cmd, {"success": False, "result": "空路径"})
                return True
            target_yaw = state.get("target_yaw")
            wpt_thresh  = 0.22
            goal_thresh = 0.25
            yaw_thresh  = 5.0

            for _ in range(NAV_SUBSTEPS):
                info  = get_base_info(env)
                x_now = info["pos"][0]
                y_now = info["pos"][1]
                index = state["index"]

                while index < len(points) - 1:
                    if np.hypot(points[index][0]-x_now, points[index][1]-y_now) > wpt_thresh:
                        break
                    index += 1
                state["index"] = index

                goal_err = float(np.hypot(points[-1][0]-x_now, points[-1][1]-y_now))

                if index == len(points) - 1 and goal_err < goal_thresh:
                    if target_yaw is not None:
                        yaw_err = _normalize_angle_deg(target_yaw - info["yaw_deg"])
                        if abs(yaw_err) > yaw_thresh:
                            Vw = float(np.clip(1.0 * (yaw_err / 90.0), -1.0, 1.0))
                            move(env, Vx=0.0, Vw=Vw)
                            _sync_ee_to_base(env)
                            state["step"] += 1
                            continue
                    stop_base(env)
                    final = get_base_info(env)
                    final_err = float(np.hypot(
                        points[-1][0]-final["pos"][0], points[-1][1]-final["pos"][1]))
                    _finish_command(cmd, {
                        "success": True,
                        "pos": final["pos"],
                        "yaw": final["yaw_deg"],
                        "goal_error": final_err,
                        "waypoints": len(points),
                    })
                    return True

                if state["step"] >= state["max_steps"]:
                    stop_base(env)
                    final = get_base_info(env)
                    final_err = float(np.hypot(
                        points[-1][0]-final["pos"][0], points[-1][1]-final["pos"][1]))
                    _finish_command(cmd, {
                        "success": final_err < 0.30,
                        "pos": final["pos"],
                        "yaw": final["yaw_deg"],
                        "goal_error": final_err,
                        "waypoints": len(points),
                        "result": "路径跟踪超时",
                    })
                    return True

                tx, ty = points[index]
                ex, ey = tx - x_now, ty - y_now
                dist    = float(np.hypot(ex, ey))
                angle_to_next = np.arctan2(ey, ex)
                heading_err   = float(np.arctan2(
                    np.sin(angle_to_next - info["yaw_rad"]),
                    np.cos(angle_to_next - info["yaw_rad"]),
                ))
                d_heading = heading_err - state["prev_heading_err"]
                state["prev_heading_err"] = heading_err

                turn    = float(np.clip(1.4 * heading_err + 0.15 * d_heading, -0.85, 0.85))
                forward = float(np.clip(1.4 * dist, 0.0, 0.45))
                forward *= max(0.0, float(np.cos(heading_err)))

                move(env, Vx=forward, Vw=turn)
                _sync_ee_to_base(env)
                state["step"] += 1

            return True

    except Exception as e:
        if cmd is not None and cmd.get("type") == "move_duration":
            stop_real_base()
        _finish_command(cmd, {"success": False, "error": str(e)})
        return True
    return False


def _move_virtual_ee(env, target):
    target = np.asarray(target, dtype=float)
    delta = target - env.virtual_ee_pos
    dist = float(np.linalg.norm(delta))
    if dist <= ARM_STEP:
        env.virtual_ee_pos = target.copy()
        if env.grasped_object:
            env.set_object_pos(env.grasped_object, env.virtual_ee_pos)
        return True
    env.virtual_ee_pos = env.virtual_ee_pos + delta / dist * ARM_STEP
    if env.grasped_object:
        env.set_object_pos(env.grasped_object, env.virtual_ee_pos)
    return False


def _apply_right_arm_pose(env, pose):
    """设置右臂目标角度，MuJoCo 位置控制器会平滑跟踪。"""
    for name, val in zip(_R_ARM_ACT_NAMES, pose):
        act_id = mujoco.mj_name2id(env.model, mujoco.mjtObj.mjOBJ_ACTUATOR, name)
        if act_id >= 0:
            env.data.ctrl[act_id] = float(val)


def _sync_ee_to_base(env):
    """持物时让虚拟末端（及物体）随底盘一起移动。
    Z 保持不变（由 lift 阶段决定高度），X/Y 跟随机器人前方 0.2m 位置。
    """
    if not env.grasped_object:
        return
    info = get_base_info(env)
    base = np.array(info["pos"])
    yaw = info["yaw_rad"]
    env.virtual_ee_pos[0] = base[0] + 0.2 * float(np.cos(yaw))
    env.virtual_ee_pos[1] = base[1] + 0.2 * float(np.sin(yaw))
    env.set_object_pos(env.grasped_object, env.virtual_ee_pos)


def process_commands(env):
    """
    主循环调用：处理队列中的所有命令
    在主循环线程中执行，不需要锁
    """
    global _active_command

    if _step_active_command(env):
        return

    with _queue_lock:
        cmd = _cmd_queue.pop(0) if _cmd_queue else None
    if cmd is None:
        return

    for cmd in [cmd]:
        cmd_id = cmd["id"]
        cmd_type = cmd["type"]
        params = cmd["params"]
        try:
            with _env_lock:
                if cmd_type == "grasp":
                    _active_command = {
                        **cmd,
                        "state": {"obj_name": params["obj_name"], "phase": "approach"},
                    }
                    return
                elif cmd_type == "place":
                    _active_command = {
                        **cmd,
                        "state": {
                            "obj_name": params["obj_name"],
                            "target_pos": np.asarray(params["target_pos"], dtype=float),
                            "phase": "move",
                        },
                    }
                    return
                elif cmd_type == "move_to":
                    reached = move_arm(env, **params)
                    info = get_arm_info(env)
                    result = {"reached": reached, "ee_pos": info["ee_pos"]}
                elif cmd_type == "open_gripper":
                    open_gripper(env, **params)
                    result = {"success": True}
                elif cmd_type == "close_gripper":
                    close_gripper(env, **params)
                    result = {"success": True}
                elif cmd_type == "nav":
                    _active_command = {
                        **cmd,
                        "state": {
                            "x": float(params["x"]),
                            "y": float(params["y"]),
                            "target_yaw": params.get("target_yaw"),
                            "pos_threshold": float(params.get("pos_threshold", 0.25)),
                            "yaw_threshold": float(params.get("yaw_threshold", 5.0)),
                            "kp": float(params.get("kp", 1.5)),
                            "kd": float(params.get("kd", 0.25)),
                            "max_steps": int(params.get("max_steps", 3000)),
                            "step": 0,
                            "prev_heading_err": 0.0,
                        },
                    }
                    return
                elif cmd_type == "nav_path":
                    path = params.get("path", [])
                    points = [(float(p["x"]), float(p["y"])) for p in path]
                    tw = params.get("w")
                    _active_command = {
                        **cmd,
                        "state": {
                            "points": points,
                            "index": 0,
                            "target_yaw": float(tw) if tw is not None else None,
                            "step": 0,
                            "max_steps": int(params.get("max_steps", 3000)),
                            "prev_heading_err": 0.0,
                        },
                    }
                    return
                elif cmd_type == "cmd_vel":
                    info = move(env, **params)
                    result = {"success": True, "pos": info["pos"], "yaw": info["yaw_deg"]}
                elif cmd_type == "screenshot":
                    from PIL import Image as PILImage
                    from io import BytesIO
                    import base64
                    defaults = _screenshot_defaults()
                    cam = params.get("camera_name") or defaults.get("default_camera", "overhead_cam")
                    w = params.get("width") or defaults.get("width", 640)
                    h = params.get("height") or defaults.get("height", 480)
                    quality = int(defaults.get("jpeg_quality", 80))
                    img = env.sim.render(w, h, camera_name=cam)
                    if img is None:
                        result = {"success": False, "result": f"相机 '{cam}' 渲染失败"}
                    else:
                        pil_img = PILImage.fromarray(img)
                        buf = BytesIO()
                        pil_img.save(buf, format="JPEG", quality=quality)
                        img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                        result = {
                            "success": True,
                            "image": img_b64,
                            "camera": cam,
                            "width": int(w),
                            "height": int(h),
                        }
                elif cmd_type == "camera_preview":
                    from io import BytesIO
                    import base64
                    from PIL import Image
                    preview = _preview_config()
                    camera_name = params.get("camera_name")
                    camera_names = [camera_name] if camera_name else preview.get("cameras", ["overhead_cam"])
                    w = int(params.get("width") or preview.get("width", 320))
                    h = int(params.get("height") or preview.get("height", 240))
                    quality = int(preview.get("jpeg_quality", 80))
                    panels = _render_camera_preview(env, camera_names, w, h)
                    if len(panels) == 1:
                        image = panels[0]
                    else:
                        while len(panels) < 4:
                            panels.append(Image.new("RGB", (w, h), (0, 0, 0)))
                        image = Image.new("RGB", (w * 2, h * 2))
                        for idx, panel in enumerate(panels[:4]):
                            image.paste(panel, ((idx % 2) * w, (idx // 2) * h))
                    buf = BytesIO()
                    image.save(buf, format="JPEG", quality=quality)
                    result = {
                        "success": True,
                        "image": base64.b64encode(buf.getvalue()).decode("utf-8"),
                        "camera": camera_name,
                    }
                else:
                    result = {"error": f"未知命令: {cmd_type}"}
        except Exception as e:
            result = {"error": str(e)}

        if cmd_type in ("nav", "cmd_vel"):
            try:
                _read_base_info(env)
            except Exception:
                pass

        with _queue_lock:
            _results[cmd_id] = result
        cmd["event"].set()


# ============================================================
# 状态查询（直接读取，不走队列）
# ============================================================

@app.route("/status", methods=["GET"])
def api_status():
    env = _get_env()
    if env is None:
        return jsonify({"error": "仿真器未初始化"}), 503
    with _env_lock:
        state = get_arm_info(env)
    return jsonify(_np_to_list(state))


@app.route("/base_status", methods=["GET"])
def api_base_status():
    env = _get_env()
    if env is None:
        return jsonify({"error": "仿真器未初始化"}), 503
    if not _env_lock.acquire(blocking=False):
        if _base_status_cache:
            return jsonify(_base_status_cache)
        return jsonify({"error": "仿真器忙"}), 503
    try:
        info = _read_base_info(env)
    finally:
        _env_lock.release()
    return jsonify(_np_to_list(info))


@app.route("/objects", methods=["GET"])
def api_objects():
    env = _get_env()
    if env is None:
        return jsonify({"error": "仿真器未初始化"}), 503
    with _env_lock:
        result = {}
        for name in env.objects:
            pos = get_obj_pos(env, name)
            result[name] = {"pos": pos.tolist(), "grasped": is_grasped(env, name)}
    return jsonify(result)

@app.route("/fixtures", methods=["GET"])
def api_fixtures():
    env = _get_env()
    if env is None:
        return jsonify({"error": "仿真器未初始化"}), 503
    result = {}
    for name, fixture in env.fixtures.items():
        result[name] = {
            "pos": list(fixture.pos),
            "size": list(fixture.size),
            "type": fixture.type,
        }
    return jsonify(result)

@app.route("/scene", methods=["GET"])
def api_scene():
    """返回完整场景信息：物体、家具、机器人"""
    env = _get_env()
    if env is None:
        return jsonify({"error": "仿真器未初始化"}), 503

    with _env_lock:
        # 物体
        objects = {}
        for name in env.objects:
            pos = get_obj_pos(env, name)
            objects[name] = {"pos": pos.tolist(), "grasped": is_grasped(env, name)}

        # 家具
        fixtures = {}
        for name in env.fixtures:
            fxtr = env.fixtures[name]
            fixtures[name] = {
                "pos": np.asarray(fxtr.pos, dtype=float).tolist(),
                "size": np.asarray(fxtr.size, dtype=float).tolist(),
                "type": fxtr.type,
            }

        # 机器人
        arm_info = get_arm_info(env)
        base_info = get_base_info(env)
        robot = {
            "base_pos": base_info["pos"],
            "ee_pos": arm_info["ee_pos"],
            "yaw": base_info.get("yaw_deg", 0),
        }

    return jsonify(_np_to_list({
        "objects": objects,
        "fixtures": fixtures,
        "robot": robot,
    }))

@app.route("/scene_state", methods=["GET"])
def api_scene_state():
    """返回当前场景状态记忆"""
    try:
        return jsonify(get_all_locations())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================
# 视频录制（工具函数内主动调用 record_hook.try_record_frame）
# ============================================================

@app.route("/record/start", methods=["POST"])
def api_record_start():
    """开始录制"""
    if _recording["active"]:
        return jsonify({"success": False, "message": "已在录制中"})

    data = request.json or {}
    _recording["fps"] = data.get("fps", 1)
    _recording["interval"] = 1.0 / _recording["fps"]
    _recording["frames"] = []
    _recording["last_capture"] = 0
    _recording["active"] = True

    total_w = _recording["view_width"] * 2
    total_h = _recording["view_height"] * 2
    print(f"[record] 开始录制 ({_recording['fps']}fps, 4视角, {total_w}x{total_h})", flush=True)
    return jsonify({"success": True, "message": "录制已开始"})


@app.route("/record/stop", methods=["POST"])
def api_record_stop():
    """停止录制并保存为视频文件"""
    if not _recording["active"]:
        return jsonify({"success": False, "message": "未在录制中"})

    _recording["active"] = False
    frames = list(_recording["frames"])
    _recording["frames"] = []

    if not frames:
        return jsonify({"success": False, "message": "未采集到画面"})

    os.makedirs(_video_dir, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    filename = f"recording_{ts}.mp4"
    filepath = os.path.join(_video_dir, filename)

    h, w = frames[0].shape[:2]
    fps = _recording["fps"]

    try:
        import imageio
        writer = imageio.get_writer(filepath, fps=fps)
        for f in frames:
            writer.append_data(f)
        writer.close()
    except ImportError:
        import cv2
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(filepath, fourcc, fps, (w, h))
        for f in frames:
            writer.write(cv2.cvtColor(f, cv2.COLOR_RGB2BGR))
        writer.release()

    print(f"[record] 录制完成: {filename} ({len(frames)} 帧, {len(frames)/fps:.1f}s)", flush=True)
    return jsonify({
        "success": True,
        "message": f"已保存 {len(frames)} 帧",
        "filename": filename,
        "frames": len(frames),
        "duration": round(len(frames) / fps, 1),
    })


@app.route("/record/download/<filename>", methods=["GET"])
def api_record_download(filename):
    """下载录制的视频文件"""
    filepath = os.path.join(_video_dir, filename)
    if not os.path.exists(filepath):
        return jsonify({"error": "文件不存在"}), 404
    return send_file(filepath, mimetype="video/mp4", as_attachment=True)


@app.route("/record/status", methods=["GET"])
def api_record_status():
    """查询录制状态"""
    return jsonify({
        "active": _recording["active"],
        "frames": len(_recording["frames"]),
        "fps": _recording["fps"],
    })


# ============================================================
# 控制命令（走队列）
# ============================================================

@app.route("/grasp", methods=["POST"])
def api_grasp():
    data = request.json or {}
    obj_name = data.get("obj_name")
    if not obj_name:
        return jsonify({"error": "缺少 obj_name 参数"}), 400
    params = {
        "obj_name": obj_name,
        "snap_threshold": data.get("snap_threshold", 0.15),
    }
    return jsonify(submit_command("grasp", params))


@app.route("/place", methods=["POST"])
def api_place():
    data = request.json or {}
    obj_name = data.get("obj_name")
    target = data.get("target")
    if not obj_name:
        return jsonify({"error": "缺少 obj_name 参数"}), 400
    if target is None:
        return jsonify({"error": "缺少 target 参数"}), 400
    params = {
        "obj_name": obj_name,
        "target_pos": target,
    }
    if data.get("snap_threshold") is not None:
        params["snap_threshold"] = data["snap_threshold"]
    return jsonify(submit_command("place", params))


@app.route("/move_to", methods=["POST"])
def api_move_to():
    data = request.json or {}
    target = data.get("target")
    if target is None:
        return jsonify({"error": "缺少 target 参数"}), 400
    params = {
        "target_pos": target,
        "max_steps": data.get("max_steps", 200),
        "pos_threshold": data.get("pos_threshold", 0.03),
    }
    return jsonify(submit_command("move_to", params))


@app.route("/move_duration", methods=["POST"])
def api_move_duration():
    """以指定速度持续移动底盘一段时间（走命令队列）"""
    data = request.json or {}
    vx = float(data.get("vx", 0.0))
    vw = float(data.get("vw", 0.0))
    duration = float(data.get("duration", 1.0))

    if duration <= 0:
        return jsonify({"error": "duration 必须大于 0"}), 400

    params = {"vx": vx, "vw": vw, "duration": duration}
    return jsonify(submit_command("move_duration", params))


@app.route("/nav", methods=["POST"])
def api_nav():
    data = request.json or {}
    x = data.get("x")
    y = data.get("y")
    if x is None or y is None:
        return jsonify({"error": "缺少 x 或 y 参数"}), 400

    params = {"x": x, "y": y}
    if data.get("target_yaw") is not None:
        params["target_yaw"] = data["target_yaw"]
    # 兼容旧参数名 w
    elif data.get("w") is not None:
        params["target_yaw"] = data["w"]
    return jsonify(submit_command("nav", params))


@app.route("/cmd_vel", methods=["POST"])
def api_cmd_vel():
    """接收速度命令，单步执行（供 Nav2 桥接节点调用）"""
    data = request.json or {}
    env = _get_env()
    if env is None:
        return jsonify({"error": "仿真器未初始化"}), 503
    set_base_velocity(
        Vx=data.get("vx", 0.0),
        Vy=data.get("vy", 0.0),
        Vw=data.get("vw", 0.0),
        timeout=data.get("duration", 0.25),
    )
    with _env_lock:
        info = get_base_info(env)
    return jsonify({"success": True, "pos": info["pos"], "yaw": info["yaw_deg"]})


@app.route("/nav_path", methods=["POST"])
def api_nav_path():
    """接收 Nav2 全局路径，由 MuJoCo 端全向 PD 跟踪"""
    data = request.json or {}
    path = data.get("path")
    if not path:
        return jsonify({"success": False, "result": "缺少 path 参数"}), 400
    params = {
        "path": path,
        "w": data.get("w"),   # None when caller did not specify yaw → no alignment
    }
    if data.get("max_steps") is not None:
        params["max_steps"] = data["max_steps"]
    return jsonify(submit_command("nav_path", params))



@app.route("/open_gripper", methods=["POST"])
def api_open_gripper():
    return jsonify(submit_command("open_gripper", {}))


@app.route("/close_gripper", methods=["POST"])
def api_close_gripper():
    return jsonify(submit_command("close_gripper", {}))


# ============================================================
# 地图生成数据（供 map_generator.py --from-sim 使用）
# ============================================================

@app.route("/map_data", methods=["GET"])
def api_map_data():
    """从上往下投射：读取所有 MuJoCo geom 的世界坐标 2D 投影，生成占据栅格"""
    env = _get_env()
    if env is None:
        return jsonify({"error": "仿真器未初始化"}), 503

    resolution = float(request.args.get("resolution", 0.05))
    x_min = float(request.args.get("x_min", -1.0))
    x_max = float(request.args.get("x_max", 8.0))
    y_min = float(request.args.get("y_min", -6.0))
    y_max = float(request.args.get("y_max", 1.0))

    width = int((x_max - x_min) / resolution)
    height = int((y_max - y_min) / resolution)

    with _env_lock:
        model = env.sim.model
        data = env.sim.data

        # 排除机器人 body。XLeRobot 的许多子 body 名称不是稳定的
        # "robot/arm" 前缀，必须从 chassis 子树排除，避免地图把机器人自身
        # 投影成静态障碍物。
        robot_bodies = set()
        chassis_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "chassis")
        for i in range(model.nbody):
            name = (mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, i) or "").lower()
            if chassis_id >= 0 and _is_body_descendant(model, i, chassis_id):
                robot_bodies.add(i)
            elif any(k in name for k in (
                "chassis", "arm", "jaw", "wrist", "pitch", "elbow", "rotation",
                "servo", "motor", "wheel", "base_plate", "head", "battery",
                "standoff", "mount",
            )):
                robot_bodies.add(i)

        # 收集障碍物的 2D 矩形 (col_min, row_min, col_max, row_max)
        rects = []
        for i in range(model.ngeom):
            body_id = model.geom_bodyid[i]
            if body_id in robot_bodies:
                continue

            name = (mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, i) or "").lower()
            if any(k in name for k in ("floor", "ground", "ceiling", "skybox", "visual", "light")):
                continue

            pos = data.geom_xpos[i]       # 世界坐标 [x, y, z]
            size = model.geom_size[i]      # 半尺寸 [hx, hy, hz]
            mat = data.geom_xmat[i].reshape(3, 3)  # 旋转矩阵

            # 太高的跳过（天花板灯具等）
            top_z = pos[2] + abs(size[2]) * 2
            if pos[2] - abs(size[2]) > 2.0 or top_z < 0.05:
                continue

            # 投影 8 个角点到 x-y 平面，取 2D AABB
            xs, ys = [], []
            for sx in (-size[0], size[0]):
                for sy in (-size[1], size[1]):
                    for sz in (-size[2], size[2]):
                        corner = pos + mat @ np.array([sx, sy, sz])
                        xs.append(corner[0])
                        ys.append(corner[1])

            x1, x2 = min(xs), max(xs)
            y1, y2 = min(ys), max(ys)
            col_min = max(0, int((x1 - x_min) / resolution))
            col_max = min(width - 1, int((x2 - x_min) / resolution))
            row_min = max(0, int((y_max - y2) / resolution))
            row_max = min(height - 1, int((y_max - y1) / resolution))
            if col_min <= col_max and row_min <= row_max:
                rects.append((col_min, row_min, col_max, row_max))

        # 画栅格
        grid = bytearray([255] * (width * height))
        for c1, r1, c2, r2 in rects:
            for r in range(r1, r2 + 1):
                for c in range(c1, c2 + 1):
                    grid[r * width + c] = 0

    return jsonify({
        "grid": list(grid),
        "width": width,
        "height": height,
        "resolution": resolution,
        "origin": [x_min, y_min],
    })


# ============================================================
# 截图（走命令队列，在主线程渲染，避免 EGL 跨线程问题）
# ============================================================

@app.route("/screenshot", methods=["POST"])
def api_screenshot():
    """从指定相机捕获单帧截图，返回 base64 编码的 JPEG 图像"""
    data = request.json or {}
    defaults = _screenshot_defaults()
    params = {
        "camera_name": data.get("camera_name") or defaults.get("default_camera", "overhead_cam"),
        "width": data.get("width") or defaults.get("width", 640),
        "height": data.get("height") or defaults.get("height", 480),
    }
    return jsonify(submit_command("screenshot", params))


@app.route("/camera/status", methods=["GET"])
def api_camera_status():
    """返回相机渲染配置"""
    return jsonify({
        "success": True,
        "config": _camera_config(),
    })


@app.route("/camera/latest", methods=["GET"])
def api_camera_latest():
    """按需渲染相机图片；默认四宫格，?camera=name 返回单路相机"""
    result = submit_command("camera_preview", {
        "camera_name": request.args.get("camera"),
        "width": request.args.get("width"),
        "height": request.args.get("height"),
    })
    if not result.get("success"):
        return jsonify(result), 500
    import base64
    return Response(base64.b64decode(result["image"]), mimetype="image/jpeg")


# ============================================================
# 启动函数
# ============================================================

def start_server(env, port=5002):
    _env_holder["env"] = env

    def run():
        app.run(host="0.0.0.0", port=port, threaded=True, use_reloader=False)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    print(f"[service] Flask API 已启动: http://localhost:{port}")
    return thread
