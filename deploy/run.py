"""
FQPlanner 任务控制台
启动后访问 http://127.0.0.1:8888

功能：任务发布、配置校验、工具查看
"""

import ast
import io
import json
import os
import sys
from pathlib import Path

import redis
import requests
import yaml
from flask import Flask, jsonify, render_template, request, send_file, send_from_directory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from robot_api.config import load_robot_api_config

app = Flask(__name__)

MASTER_URL = os.getenv("MASTER_URL", "http://127.0.0.1:5000")
SIM_URL = os.getenv("ROBOT_API_URL", load_robot_api_config().server_url)
REDIS_CFG = {"host": "127.0.0.1", "port": 6379, "db": 0, "password": None}

# 四宫格任务时间线:capture_quad_timeline.py 把每个时间点的四宫格拼图(overhead+head+左右腕)
# 和 timeline.json 存到这里,网站按时间点回放。
TIMELINE_DIR = PROJECT_ROOT / "deploy" / "task_timeline"


def extract_tools_from_ast(source, filename):
    """从 skill.py 源码中解析工具函数"""
    tree = ast.parse(source, filename=filename)
    tools = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.decorator_list:
                continue
            for deco in node.decorator_list:
                if isinstance(deco, ast.Call) and getattr(deco.func, "attr", None) == "tool":
                    parameters = []
                    total_args = len(node.args.args)
                    defaults = [None] * (total_args - len(node.args.defaults)) + node.args.defaults
                    for arg, default in zip(node.args.args, defaults):
                        if arg.arg == "self":
                            continue
                        parameters.append({
                            "name": arg.arg,
                            "type": ast.unparse(arg.annotation) if arg.annotation else "Any",
                            "default": ast.unparse(default) if default else None,
                        })
                    tools.append({
                        "name": node.name,
                        "description": ast.get_docstring(node) or "",
                        "parameters": parameters,
                    })
    return tools


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/publish_task", methods=["POST"])
def publish_task():
    """转发任务到 Master"""
    try:
        data = request.get_json()
        if not data or "task" not in data:
            return jsonify({"error": "缺少 task 字段"}), 400
        resp = requests.post(f"{MASTER_URL}/publish_task", json=data, timeout=120)
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "Master 服务未启动"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/validate-config", methods=["POST"])
def validate_config():
    """校验配置文件和 Redis/MCP 连通性"""
    project_root = Path(__file__).parent.parent
    data = request.json or {}
    master_cfg = data.get("master_config") or str(project_root / "master" / "config.yaml")
    slaver_cfg = data.get("slaver_config") or str(project_root / "slaver" / "config.yaml")

    for path in [master_cfg, slaver_cfg]:
        if not path or not os.path.exists(path):
            return jsonify({"success": False, "message": f"配置文件不存在: {path}"}), 400

    with open(master_cfg, "r", encoding="utf-8") as f:
        master_data = yaml.safe_load(f)
    with open(slaver_cfg, "r", encoding="utf-8") as f:
        slaver_data = yaml.safe_load(f)

    master_col = master_data.get("collaborator", {})
    slaver_col = slaver_data.get("collaborator", {})
    required_keys = {"host", "port", "password", "db"}

    if not required_keys.issubset(master_col.keys()) or not required_keys.issubset(slaver_col.keys()):
        return jsonify({"success": False, "message": "collaborator 配置字段不完整"})

    if (master_col["host"], master_col["port"]) != (slaver_col["host"], slaver_col["port"]):
        return jsonify({"success": False, "message": "Master 和 Slaver collaborator 配置不匹配"})

    try:
        r = redis.StrictRedis(
            host=master_col["host"], port=master_col["port"],
            password=master_col["password"], db=master_col["db"],
            socket_connect_timeout=5,
        )
        r.ping()
    except Exception as e:
        return jsonify({"success": False, "message": f"Redis 连接失败: {e}"})

    robot = slaver_data.get("robot", {})
    if robot.get("call_type") == "remote":
        try:
            requests.post(robot["path"].rstrip("/") + "/mcp", timeout=5)
        except requests.exceptions.RequestException:
            return jsonify({"success": False, "message": "MCP 远程服务不可达"})

    return jsonify({"success": True, "message": "配置校验通过"})


@app.route("/api/task_status", methods=["GET"])
def task_status():
    """转发 Master 的任务状态查询"""
    try:
        resp = requests.get(f"{MASTER_URL}/api/task_status", timeout=5)
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"active": False, "error": "Master 服务未启动"}), 503
    except Exception as e:
        return jsonify({"active": False, "error": str(e)}), 500


@app.route("/api/failure_pending", methods=["GET"])
def failure_pending():
    try:
        resp = requests.get(f"{MASTER_URL}/api/failure_pending", timeout=5)
        return jsonify(resp.json()), resp.status_code
    except Exception:
        return jsonify({"pending": False}), 200


@app.route("/api/save_failure_experience", methods=["POST"])
def save_failure_experience():
    try:
        resp = requests.post(f"{MASTER_URL}/api/save_failure_experience",
                             json=request.get_json(), timeout=30)
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/success_pending", methods=["GET"])
def success_pending():
    try:
        resp = requests.get(f"{MASTER_URL}/api/success_pending", timeout=5)
        return jsonify(resp.json()), resp.status_code
    except Exception:
        return jsonify({"pending": False}), 200


@app.route("/api/save_success_experience", methods=["POST"])
def save_success_experience():
    try:
        resp = requests.post(f"{MASTER_URL}/api/save_success_experience",
                             json=request.get_json(), timeout=30)
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/save_experience", methods=["POST"])
def save_experience():
    """转发经验保存到 Master"""
    try:
        data = request.get_json()
        resp = requests.post(f"{MASTER_URL}/api/save_experience", json=data, timeout=5)
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"success": False, "message": "Master 服务未启动"}), 503
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/experiences", methods=["GET"])
def experiences():
    """转发经验库查询"""
    try:
        resp = requests.get(f"{MASTER_URL}/api/experiences", timeout=5)
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"success": True, "data": ""}), 200
    except Exception as e:
        return jsonify({"success": True, "data": ""}), 200


@app.route("/api/auto_tools", methods=["GET"])
def auto_tools():
    """从 Redis 自动读取已注册机器人的工具列表"""
    try:
        r = redis.StrictRedis(**REDIS_CFG, socket_connect_timeout=3, decode_responses=True)
        r.ping()
        agents = r.hgetall("AGENT_INFO")
        if not agents:
            return jsonify({"success": True, "data": []})
        result = []
        for name, info_str in agents.items():
            try:
                info = json.loads(info_str)
                tools = info.get("robot_tool", [])
                for t in tools:
                    func = t.get("function", {})
                    params = func.get("parameters", {})
                    props = params.get("properties", {})
                    param_list = [
                        {"name": k, "type": v.get("type", "any")}
                        for k, v in props.items()
                    ]
                    result.append({
                        "robot": name,
                        "name": func.get("name", ""),
                        "description": func.get("description", ""),
                        "parameters": param_list,
                    })
            except (json.JSONDecodeError, AttributeError):
                continue
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "message": f"Redis 连接失败: {e}", "data": []})


@app.route("/api/scene_state", methods=["GET"])
def scene_state():
    """读取当前场景状态"""
    try:
        r = redis.StrictRedis(**REDIS_CFG, socket_connect_timeout=3, decode_responses=True)
        r.ping()
        raw = r.hgetall("ENVIRONMENT_INFO")
        if not raw:
            return jsonify({"success": True, "data": {}})
        result = {}
        for name, val in raw.items():
            try:
                result[name] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                result[name] = val
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "message": f"Redis 连接失败: {e}", "data": {}})


@app.route("/api/update_scene", methods=["POST"])
def update_scene():
    """手动更新场景（外部变化）"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "缺少 JSON 数据"}), 400

        location = data.get("location")
        action = data.get("action")  # add_object / remove_object
        obj = data.get("object")

        if not location or not action or not obj:
            return jsonify({"success": False, "message": "需要 location, action, object 三个字段"}), 400

        r = redis.StrictRedis(**REDIS_CFG, socket_connect_timeout=3, decode_responses=True)
        r.ping()

        raw = r.hget("ENVIRONMENT_INFO", location)
        if not raw:
            return jsonify({"success": False, "message": f"位置 '{location}' 不存在"}), 404

        scene_obj = json.loads(raw)
        contains = scene_obj.get("contains", [])

        if action == "add_object":
            if obj not in contains:
                contains.append(obj)
        elif action == "remove_object":
            if obj in contains:
                contains.remove(obj)
        else:
            return jsonify({"success": False, "message": f"不支持的 action: {action}"}), 400

        scene_obj["contains"] = contains
        r.hset("ENVIRONMENT_INFO", location, json.dumps(scene_obj, ensure_ascii=False))

        return jsonify({"success": True, "message": f"{action} '{obj}' at '{location}'", "data": scene_obj})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/get_tool_config", methods=["POST"])
def get_tool_config():
    """获取工具列表（解析 skill.py 中的 @mcp.tool() 函数）"""
    data = request.json or {}
    slaver_cfg_path = data.get("slaver_config")

    if not slaver_cfg_path or not os.path.exists(slaver_cfg_path):
        return jsonify({"success": False, "message": "配置文件不存在", "data": []}), 400

    with open(slaver_cfg_path, "r", encoding="utf-8") as f:
        slaver_data = yaml.safe_load(f)

    call_type = slaver_data.get("robot", {}).get("call_type")
    path = slaver_data.get("robot", {}).get("path")

    if call_type == "local":
        base_dir = Path(slaver_cfg_path).parent
        tool_path = base_dir / path / "skill.py"
        if not tool_path.exists():
            return jsonify({"success": False, "message": f"{tool_path} 不存在", "data": []}), 400
        with open(tool_path, "r", encoding="utf-8") as f:
            source = f.read()
        results = extract_tools_from_ast(source, str(tool_path))
        return jsonify({"success": True, "data": results})
    else:
        try:
            url = path.rstrip("/") + "/mcp"
            requests.post(url, timeout=5)
            return jsonify({"success": True, "data": []})
        except Exception as e:
            return jsonify({"success": False, "message": f"MCP 服务不可达: {e}", "data": []}), 400


@app.route("/api/robot_status", methods=["GET"])
def robot_status():
    """代理仿真后端的场景信息（机器人坐标、物体、家具）"""
    try:
        resp = requests.get(f"{SIM_URL}/scene", timeout=5)
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "仿真服务未启动"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/record/start", methods=["POST"])
def record_start():
    """代理仿真后端：开始录制"""
    try:
        resp = requests.post(f"{SIM_URL}/record/start", json=request.json or {}, timeout=5)
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"success": False, "message": "仿真服务未启动"}), 503


@app.route("/api/record/stop", methods=["POST"])
def record_stop():
    """代理仿真后端：停止录制"""
    try:
        resp = requests.post(f"{SIM_URL}/record/stop", timeout=30)
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"success": False, "message": "仿真服务未启动"}), 503


@app.route("/api/record/status", methods=["GET"])
def record_status():
    """代理仿真后端：录制状态"""
    try:
        resp = requests.get(f"{SIM_URL}/record/status", timeout=5)
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"active": False}), 503


@app.route("/api/record/download/<filename>", methods=["GET"])
def record_download(filename):
    """代理仿真后端：下载视频"""
    try:
        resp = requests.get(f"{SIM_URL}/record/download/{filename}", timeout=30, stream=True)
        if resp.status_code == 200:
            return send_file(io.BytesIO(resp.content), mimetype="video/mp4", as_attachment=True, download_name=filename)
        return jsonify({"error": "下载失败"}), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "仿真服务未启动"}), 503


# ============================================================
# 四宫格相机(真机3相机 head+左右腕 + overhead 拼图)
# ============================================================

@app.route("/api/quad_latest", methods=["GET"])
def quad_latest():
    """实时四宫格:代理仿真后端 /camera/latest(2x2 拼图 overhead+head+右腕+左腕,带标签)。"""
    try:
        resp = requests.get(f"{SIM_URL}/camera/latest", timeout=30, stream=True)
        if resp.status_code == 200:
            return send_file(io.BytesIO(resp.content), mimetype="image/jpeg")
        return jsonify({"error": "渲染失败"}), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"error": "仿真服务未启动"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/timeline", methods=["GET"])
def timeline_manifest():
    """返回已采集的四宫格任务时间线清单(deploy/task_timeline/timeline.json)。"""
    manifest = TIMELINE_DIR / "timeline.json"
    if not manifest.exists():
        return jsonify({"exists": False, "frames": []})
    try:
        with open(manifest, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["exists"] = True
        return jsonify(data)
    except Exception as e:
        return jsonify({"exists": False, "error": str(e), "frames": []}), 500


@app.route("/task_timeline/<path:filename>", methods=["GET"])
def timeline_frame(filename):
    """按文件名返回时间线里某一帧四宫格图。"""
    if not TIMELINE_DIR.exists():
        return jsonify({"error": "无时间线目录"}), 404
    return send_from_directory(str(TIMELINE_DIR), filename)


if __name__ == "__main__":
    print("任务控制台已启动: http://127.0.0.1:8888")
    app.run(host="0.0.0.0", port=8888, debug=False)
