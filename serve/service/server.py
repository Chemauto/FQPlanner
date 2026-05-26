"""
server.py - Flask API 服务
通过命令队列与仿真器主循环通信，避免多线程同时调用 env.step()
"""

import threading
import numpy as np
from flask import Flask, request, jsonify
from flask_cors import CORS

from tools.arm import (
    get_ee_pos, get_obj_pos, get_arm_state,
    move_to, grasp, release, pick_and_place,
    open_gripper, close_gripper, is_grasped,
)
from tools.move import get_base_info, nav

app = Flask(__name__)
CORS(app)

_env_holder = {"env": None}
_cmd_queue = []      # 命令队列
_results = {}        # 命令结果缓存
_lock = threading.Lock()


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
            elif cmd_type == "release":
                release(env, **params)
                result = {"success": True}
            elif cmd_type == "move_to":
                reached = move_to(env, **params)
                result = {"reached": reached, "ee_pos": get_ee_pos(env).tolist()}
            elif cmd_type == "pick_and_place":
                success = pick_and_place(env, **params)
                result = {"success": success}
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
    state = get_arm_state(env)
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


# ============================================================
# 控制命令（走队列）
# ============================================================

@app.route("/grasp", methods=["POST"])
def api_grasp():
    data = request.json or {}
    params = {
        "obj_name": data.get("obj_name", "pot"),
        "snap_threshold": data.get("snap_threshold", 0.2),
        "approach_height": data.get("approach_height", 0.15),
    }
    return jsonify(submit_command("grasp", params))


@app.route("/release", methods=["POST"])
def api_release():
    data = request.json or {}
    params = {"lift_height": data.get("lift_height", 0.1)}
    return jsonify(submit_command("release", params))


@app.route("/move_to", methods=["POST"])
def api_move_to():
    data = request.json or {}
    target = data.get("target")
    if target is None:
        return jsonify({"error": "缺少 target 参数"}), 400
    params = {
        "target_pos": target,
        "steps": data.get("steps", 300),
        "threshold": data.get("threshold", 0.03),
    }
    return jsonify(submit_command("move_to", params))


@app.route("/pick_and_place", methods=["POST"])
def api_pick_and_place():
    data = request.json or {}
    target = data.get("target")
    if target is None:
        return jsonify({"error": "缺少 target 参数"}), 400
    params = {
        "obj_name": data.get("obj_name", "pot"),
        "target_pos": target,
        "approach_height": data.get("approach_height", 0.15),
    }
    return jsonify(submit_command("pick_and_place", params))


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
