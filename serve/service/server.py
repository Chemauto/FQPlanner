"""
server.py - Flask API 服务
通过命令队列与仿真器主循环通信，避免多线程同时调用 env.step()
"""

import os
import time
import threading
import numpy as np
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

from tools.arm import (
    get_arm_info, get_obj_pos,
    move_arm, grasp, place,
    open_gripper, close_gripper, is_grasped,
)
from tools.move import get_base_info, nav, move, follow_path
from utils.utils import get_fixture_detail

app = Flask(__name__)
CORS(app)

_env_holder = {"env": None}
_cmd_queue = []      # 命令队列
_results = {}        # 命令结果缓存
_queue_lock = threading.Lock()
_env_lock = threading.RLock()
_base_cmd = {
    "Vx": 0.0,
    "Vy": 0.0,
    "Vw": 0.0,
    "expires_at": 0.0,
    "last_log_at": 0.0,
}
_base_status_cache = {}

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
    ("overhead_cam",       "Top",   False),
    ("side_cam",           "Side",  True),
    ("robot0_frontview",   "Front", True),
    ("robot0_eye_in_hand", "Eye",   False),
]

_video_dir = os.path.join(os.path.dirname(__file__), "..", "videos")


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


def set_base_velocity(Vx=0.0, Vy=0.0, Vw=0.0, timeout=0.25):
    """Store the latest velocity command for the main simulation loop."""
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


def get_base_action(action_dim):
    """Build the current base action, expiring to zero if cmd_vel stops."""
    action = np.zeros(action_dim)
    with _queue_lock:
        if time.time() > _base_cmd["expires_at"]:
            return action
        action[7] = np.clip(_base_cmd["Vx"], -1.0, 1.0)
        action[8] = np.clip(_base_cmd["Vy"], -1.0, 1.0)
        action[9] = np.clip(_base_cmd["Vw"], -1.0, 1.0)
        action[11] = 1.0
    return action


def _get_env():
    return _env_holder["env"]


def _read_base_info(env):
    info = get_base_info(env)
    _base_status_cache.clear()
    _base_status_cache.update(_np_to_list(info))
    return info


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


def process_commands(env):
    """
    主循环调用：处理队列中的所有命令
    在主循环线程中执行，不需要锁
    """
    with _queue_lock:
        cmds = list(_cmd_queue)
        _cmd_queue.clear()

    for cmd in cmds:
        cmd_id = cmd["id"]
        cmd_type = cmd["type"]
        params = cmd["params"]
        try:
            with _env_lock:
                if cmd_type == "grasp":
                    success = grasp(env, **params)
                    result = {"success": success}
                elif cmd_type == "place":
                    success = place(env, **params)
                    result = {"success": success}
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
                    info = nav(env, **params)
                    result = {"success": True, "pos": info["pos"], "yaw": info["yaw_deg"]}
                elif cmd_type == "nav_path":
                    result = follow_path(env, **params)
                elif cmd_type == "cmd_vel":
                    info = move(env, **params)
                    result = {"success": True, "pos": info["pos"], "yaw": info["yaw_deg"]}
                elif cmd_type == "screenshot":
                    from PIL import Image as PILImage
                    from io import BytesIO
                    import base64
                    cam = params.get("camera_name", "overhead_cam")
                    w = params.get("width", 640)
                    h = params.get("height", 480)
                    img = env.sim.render(w, h, camera_name=cam)
                    if img is None:
                        result = {"success": False, "result": f"相机 '{cam}' 渲染失败"}
                    else:
                        pil_img = PILImage.fromarray(img)
                        buf = BytesIO()
                        pil_img.save(buf, format="JPEG", quality=80)
                        img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                        result = {"success": True, "image": img_b64, "camera": cam}
                else:
                    result = {"error": f"未知命令: {cmd_type}"}
        except Exception as e:
            result = {"error": str(e)}

        if cmd_type in ("nav", "nav_path", "cmd_vel"):
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
        try:
            body_id = env.sim.model.body_name2id(fixture.root_body)
            pos = env.sim.data.body_xpos[body_id].copy()
            result[name] = {"pos": pos.tolist()}
        except Exception:
            pass
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
            detail = get_fixture_detail(env, name)
            for fname, info in detail.items():
                fixtures[fname] = {
                    "pos": info["pos"].tolist(),
                    "size": info["size"].tolist(),
                    "type": info["type"],
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
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from scene.scene_memory import get_all_locations
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
        "w": data.get("w", 0),
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

        # 排除的 body（机器人相关）
        robot_bodies = set()
        for i in range(model.nbody):
            name = (model.body_id2name(i) or "").lower()
            if any(k in name for k in ("robot", "panda", "omron", "mobilebase",
                                        "gripper", "finger", "hand", "torso",
                                        "camera", "link", "joint", "site")):
                robot_bodies.add(i)

        # 收集障碍物的 2D 矩形 (col_min, row_min, col_max, row_max)
        rects = []
        for i in range(model.ngeom):
            body_id = model.geom_bodyid[i]
            if body_id in robot_bodies:
                continue

            name = (model.geom_id2name(i) or "").lower()
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
    params = {
        "camera_name": data.get("camera_name", "overhead_cam"),
        "width": data.get("width", 640),
        "height": data.get("height", 480),
    }
    return jsonify(submit_command("screenshot", params))


# ============================================================
# 启动函数
# ============================================================

def start_server(env, port=5001):
    _env_holder["env"] = env

    def run():
        app.run(host="0.0.0.0", port=port, threaded=True, use_reloader=False)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    print(f"[service] Flask API 已启动: http://localhost:{port}")
    return thread
