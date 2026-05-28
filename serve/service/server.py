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
from tools.move import get_base_info, nav
from utils.utils import get_fixture_detail

app = Flask(__name__)
CORS(app)

_env_holder = {"env": None}
_cmd_queue = []      # 命令队列
_results = {}        # 命令结果缓存
_lock = threading.Lock()

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
    return _lock


def _get_env():
    return _env_holder["env"]


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
    with _lock:
        _cmd_queue.append(cmd)
    event.wait(timeout=120)  # 最多等 120 秒
    with _lock:
        result = _results.pop(cmd_id, {"error": "超时"})
    return result


def process_commands(env):
    """
    主循环调用：处理队列中的所有命令
    在主循环线程中执行，不需要锁
    """
    with _lock:
        cmds = list(_cmd_queue)
        _cmd_queue.clear()

    for cmd in cmds:
        cmd_id = cmd["id"]
        cmd_type = cmd["type"]
        params = cmd["params"]
        try:
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
            else:
                result = {"error": f"未知命令: {cmd_type}"}
        except Exception as e:
            result = {"error": str(e)}

        with _lock:
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
    state = get_arm_info(env)
    return jsonify(_np_to_list(state))


@app.route("/base_status", methods=["GET"])
def api_base_status():
    env = _get_env()
    if env is None:
        return jsonify({"error": "仿真器未初始化"}), 503
    info = get_base_info(env)
    return jsonify(_np_to_list(info))


@app.route("/objects", methods=["GET"])
def api_objects():
    env = _get_env()
    if env is None:
        return jsonify({"error": "仿真器未初始化"}), 503
    result = {}
    for name in env.objects:
        pos = get_obj_pos(env, name)
        result[name] = {"pos": pos.tolist(), "grasped": is_grasped(env, name)}
    return jsonify(result)


@app.route("/scene", methods=["GET"])
def api_scene():
    """返回完整场景信息：物体、家具、机器人"""
    env = _get_env()
    if env is None:
        return jsonify({"error": "仿真器未初始化"}), 503

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
    w = data.get("w", 0)
    yaw = data.get("yaw", 0)
    if x is None or y is None:
        return jsonify({"error": "缺少 x 或 y 参数"}), 400
    params = {"x": x, "y": y, "w": w, "yaw": yaw}
    return jsonify(submit_command("nav", params))


@app.route("/open_gripper", methods=["POST"])
def api_open_gripper():
    return jsonify(submit_command("open_gripper", {}))


@app.route("/close_gripper", methods=["POST"])
def api_close_gripper():
    return jsonify(submit_command("close_gripper", {}))


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
