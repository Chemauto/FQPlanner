"""serve_dream HTTP 后端 — 把 DREAM(导航建图组)交付物适配成 FQPlanner 标准后端接口。

上层(master/slaver/nav2 生成器)通过 robot_api 打这里,与打 serve/serve_3dgs 无差别:
  GET  /objects /fixtures /scene /base_status /map_data /health
  POST /nav        → 按对方文件契约写任务、轮询结果(adapters/nav_handoff)
  POST /grasp /place /screenshot → 501,真机上由 VLA 组后端提供(robot_api 分路由)

所有 GET 每次请求都重读交换目录里的 latest 文件 → 天然"随时拿最新",无缓存失效问题。
"""

import json
import math
import os
import sys

from flask import Flask, jsonify, request

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PKG_DIR = os.path.dirname(_THIS_DIR)
_PROJECT_ROOT = os.path.dirname(_PKG_DIR)
for p in (_PKG_DIR, _PROJECT_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

import yaml

from adapters import exchange, nav_handoff, rosmap, scene_graph

app = Flask(__name__)

_CONFIG_PATH = os.path.join(_PKG_DIR, "config.yaml")


def _cfg():
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _exchange_dir():
    cfg = _cfg()
    d = (cfg.get("exchange") or {}).get("dir", "serve_dream/sample")
    return d if os.path.isabs(d) else os.path.join(_PROJECT_ROOT, d)


def _exchange_file(key, default):
    cfg = (_cfg().get("exchange") or {})
    return os.path.join(_exchange_dir(), cfg.get(key, default))


def _load_graph_or_none():
    return exchange.load_json_file(_cfg(), _PROJECT_ROOT, "scene_graph",
                                   "total_scene_graph_latest.json")


@app.route("/health", methods=["GET"])
def api_health():
    cfg = _cfg()
    graph, gsrc = _load_graph_or_none()
    map_path = exchange.map_yaml_path(cfg, _PROJECT_ROOT)
    return jsonify({
        "success": True,
        "mode": exchange.mode(cfg),
        "source": exchange.base_url(cfg) if exchange.mode(cfg) == "http" else _exchange_dir(),
        "nav_url": exchange.nav_url(cfg) or None,
        "scene_graph": {"found": graph is not None, "source": gsrc,
                        **(scene_graph.graph_meta(graph) if graph else {})},
        "map": {"found": map_path is not None, "path": map_path},
    })


@app.route("/objects", methods=["GET"])
def api_objects():
    graph, path = _load_graph_or_none()
    if graph is None:
        return jsonify({"success": False, "result": f"场景图不存在: {path}"}), 503
    return jsonify(scene_graph.graph_objects(graph))


@app.route("/fixtures", methods=["GET"])
def api_fixtures():
    graph, path = _load_graph_or_none()
    if graph is None:
        return jsonify({"success": False, "result": f"场景图不存在: {path}"}), 503
    return jsonify(scene_graph.graph_fixtures(graph))


@app.route("/scene", methods=["GET"])
def api_scene():
    graph, path = _load_graph_or_none()
    if graph is None:
        return jsonify({"success": False, "result": f"场景图不存在: {path}"}), 503
    base = _read_pose()
    return jsonify({
        "objects": scene_graph.graph_objects(graph),
        "fixtures": scene_graph.graph_fixtures(graph),
        "robot": {"base_pos": base["pos"], "yaw": base["yaw_deg"]} if base else None,
        "meta": scene_graph.graph_meta(graph),
    })


def _read_pose():
    """位姿来源:nav_map_latest.json 的 robot_xyt: [x, y, yaw_rad](http/dir 通道均可)。"""
    data, _src = exchange.load_json_file(_cfg(), _PROJECT_ROOT, "pose_file", "nav_map_latest.json")
    if data is None:
        return None
    try:
        xyt = data.get("robot_xyt")
        if not xyt or len(xyt) < 3:
            return None
        yaw_rad = float(xyt[2])
        return {
            "pos": [float(xyt[0]), float(xyt[1]), 0.0],
            "yaw_rad": round(yaw_rad, 4),
            "yaw_deg": round(math.degrees(yaw_rad) % 360.0, 2),
        }
    except Exception:
        return None


@app.route("/base_status", methods=["GET"])
def api_base_status():
    pose = _read_pose()
    if pose is None:
        return jsonify({"success": False,
                        "result": "位姿文件缺失或无 robot_xyt(需导航建图组提供 nav_map_latest.json)"}), 503
    return jsonify(pose)


@app.route("/map_data", methods=["GET"])
def api_map_data():
    path = exchange.map_yaml_path(_cfg(), _PROJECT_ROOT)
    if path is None:
        return jsonify({"success": False, "result": "地图不可用(检查通道配置与对方数据服务)"}), 503
    return jsonify(rosmap.load_map_data(path))


@app.route("/nav", methods=["POST"])
def api_nav():
    data = request.json or {}
    x, y = data.get("x"), data.get("y")
    if x is None or y is None:
        return jsonify({"success": False,
                        "result": "缺少 x 或 y(serve_dream 只收 map 系坐标;地名→工作点由 slaver 解析)"}), 400
    yaw_deg = data.get("target_yaw", data.get("w"))
    nav_cfg = _cfg().get("nav") or {}
    if exchange.mode(_cfg()) == "http":
        # 首选通道:直接转发给对方的 nav2_goal_bridge(同步,走完才回)
        resp, code = exchange.nav_forward(
            _cfg(), x, y, yaw_deg,
            timeout=float(nav_cfg.get("result_timeout_sec", 180)),
        )
        return jsonify(resp), code
    task = nav_handoff.build_task(
        x, y, yaw_deg,
        position_tolerance_m=float(nav_cfg.get("position_tolerance_m", 0.35)),
        yaw_tolerance_deg=float(nav_cfg.get("yaw_tolerance_deg", 25.0)),
    )
    task_dir = nav_handoff.write_task(_exchange_dir(), task)
    print(f"[serve_dream] 导航任务已写出: {task_dir}", file=sys.stderr)
    result = nav_handoff.poll_result(
        task_dir,
        timeout_sec=float(nav_cfg.get("result_timeout_sec", 180)),
        interval_sec=float(nav_cfg.get("result_poll_interval_sec", 1.0)),
    )
    return jsonify(nav_handoff.result_to_response(result))


def _not_this_backend(what, owner):
    return jsonify({"success": False,
                    "result": f"serve_dream 不提供 {what}(真机由 {owner} 后端提供,见 robot_api/config.yaml)"}), 501


@app.route("/grasp", methods=["POST"])
def api_grasp():
    return _not_this_backend("/grasp", "VLA 执行组")


@app.route("/place", methods=["POST"])
def api_place():
    return _not_this_backend("/place", "VLA 执行组")


@app.route("/screenshot", methods=["POST"])
def api_screenshot():
    return _not_this_backend("/screenshot", "VLA 执行组")


@app.route("/scene_state", methods=["GET"])
def api_scene_state():
    # belief/scene_memory 是 robocasa 仿真端能力;真机首期用 use_realtime_coords:true(方案Y)。
    return jsonify({"success": False, "result": "serve_dream 暂无 scene_state(真机首期走 /objects 真值)"}), 503


def start_server(port=None):
    port = port or int((_cfg().get("server") or {}).get("port", 5006))
    print(f"[serve_dream] API: http://localhost:{port}  (exchange: {_exchange_dir()})")
    app.run(host="0.0.0.0", port=port, threaded=True)
