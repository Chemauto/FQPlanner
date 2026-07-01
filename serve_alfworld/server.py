"""serve_alfworld/server.py — Flask HTTP layer wrapping AlfEnv (port 5301)."""

from __future__ import annotations

import os
import sys

from flask import Flask, jsonify, request
from flask_cors import CORS

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from serve_alfworld.alf_env import AlfEnv

app = Flask(__name__)
CORS(app)

_env: AlfEnv | None = None


def get_env() -> AlfEnv:
    global _env
    if _env is None:
        raise RuntimeError("env not initialised — call POST /reset first")
    return _env


# ── lifecycle ──────────────────────────────────────────────────────────────────

def _ensure_env(body: dict | None = None) -> AlfEnv:
    """Build the singleton env on first use. seed/split can come from the request
    body (benchmark driver) or env vars; seed is fixed at construction so the
    sorted/shuffled game order — i.e. which index maps to which game — is stable."""
    global _env
    body = body or {}
    if _env is None:
        config_path = os.environ.get(
            "ALFWORLD_CONFIG",
            os.path.expanduser("~/alfworld-repo/configs/base_config.yaml"),
        )
        split = body.get("split") or os.environ.get("ALFWORLD_SPLIT", "train")
        raw_seed = body.get("seed", os.environ.get("ALFWORLD_SEED"))
        seed = int(raw_seed) if raw_seed is not None and str(raw_seed) != "" else None
        _env = AlfEnv(config_path=config_path, split=split, rng_seed=seed)
    return _env


@app.post("/reset")
def reset():
    body = request.get_json(force=True, silent=True) or {}
    env = _ensure_env(body)
    # Deterministic addressable reset (benchmark): {"split","index"[,"seed"]}.
    # Without "index", legacy sequential behavior is preserved.
    if "index" in body and body["index"] is not None:
        split = body.get("split") or env._default_split
        snap = env.reset_to(split, int(body["index"]))
    else:
        snap = env.reset()
    return jsonify({"success": True, "result": snap})


@app.get("/dataset_info")
def dataset_info():
    """Game count for a split, so the driver can size train/eval subsets."""
    env = _ensure_env()
    split = request.args.get("split") or env._default_split
    return jsonify({"split": split, "size": env.dataset_size(split), "seed": env._seed})


# ── Phase 1: 持续世界(per-home) ────────────────────────────────────────────────

@app.get("/homes")
def homes():
    """按 floorplan 分组 → {floorplan_id: [game indices]}。挑一个当持续世界。"""
    env = _ensure_env()
    split = request.args.get("split") or env._default_split
    groups = env.homes(split)
    return jsonify({"split": split, "homes": groups, "count": len(groups)})


@app.post("/reset_home")
def reset_home():
    """载入某 home 的代表 game 作为持续世界(载入后不再 re-init)。Body: {floorplan_id[,split]}。"""
    body = request.get_json(force=True, silent=True) or {}
    fid = body.get("floorplan_id")
    if fid is None:
        return jsonify({"success": False, "result": "missing floorplan_id"})
    env = _ensure_env(body)
    try:
        snap = env.reset_home(str(fid), body.get("split"))
    except ValueError as e:
        return jsonify({"success": False, "result": str(e)})
    return jsonify({"success": True, "result": snap})


@app.post("/inject_move")
def inject_move():
    """测试注入:把物体挪到别处,模拟「家里东西被人动了」。Body: {obj, to}。仅持续模式。"""
    body = request.get_json(force=True, silent=True) or {}
    obj = body.get("obj") or body.get("object_name")
    to = body.get("to") or body.get("to_receptacle")
    if not obj or not to:
        return jsonify({"success": False, "result": "missing obj or to"})
    return jsonify(get_env().move_object(str(obj), str(to)))


# ── state endpoints (GET) ──────────────────────────────────────────────────────

@app.get("/scene")
def scene():
    snap = get_env().snapshot()
    return jsonify({
        "objects": {e: {"name": e, "pos": None} for e in snap.get("objects_in_view", [])},
        "fixtures": {r: {"name": r, "pos": None} for r in snap.get("receptacles", [])},
        "task": snap.get("task"),
        "observation": snap.get("observation"),
        "holding": snap.get("holding"),
        "admissible_commands": snap.get("admissible_commands"),
        "won": snap.get("won"),
    })


@app.get("/objects")
def objects():
    snap = get_env().snapshot()
    # pos=null so waypoint_manager.get_object_pos returns None → find_waypoint raises → string fallback
    return jsonify({e: {"name": e, "pos": None} for e in snap.get("objects_in_view", [])})


@app.get("/scene_state")
def scene_state():
    return jsonify(get_env().snapshot())


@app.get("/success")
def success():
    env = get_env()
    if env._persistent and env.task:
        # 持续模式: stock quest 的 oracle won 不代表我们的自定义任务;
        # 用 shadow_judge 做完成裁判,结果 agent 感知一致(slaver 工具也从这读)。
        won = env.shadow.judge(env.task)
        return jsonify({"won": won, "steps": env.steps(), "shadow_judge": True})
    return jsonify({"won": env.won(), "steps": env.steps()})


@app.post("/set_task")
def set_task():
    """持续模式专用:在不重置世界/shadow 的前提下切换当前任务文字。Body: {task: str}。"""
    body = request.get_json(force=True, silent=True) or {}
    task = (body.get("task") or "").strip()
    if not task:
        return jsonify({"success": False, "result": "missing task"})
    env = get_env()
    if not env._persistent:
        return jsonify({"success": False, "result": "set_task 仅持续模式可用(先 POST /reset_home)"})
    env.task = task
    return jsonify({"success": True, "task": task, "shadow_done_now": env.shadow.judge(task)})


@app.get("/shadow_state")
def shadow_state_view():
    """Agent belief state (location/open from obs; clean/hot/cold from provenance)."""
    return jsonify(get_env().shadow.to_dict())


@app.get("/shadow_judge")
def shadow_judge():
    """Judge task completion using ShadowState — no oracle.
    Query param: ?task=<task string>  (defaults to current game task if omitted)
    """
    env = get_env()
    task = request.args.get("task") or env.task
    done = env.shadow.judge(task)
    return jsonify({
        "task": task,
        "shadow_done": done,
        "oracle_won": env.won(),
        "agree": done == env.won(),
    })


@app.get("/fixtures")
def fixtures():
    snap = get_env().snapshot()
    # pos=null so waypoint_manager.get_object_pos returns None → find_waypoint raises → string fallback
    return jsonify({r: {"name": r, "pos": None} for r in snap.get("receptacles", [])})


@app.get("/base_status")
def base_status():
    return jsonify({"x": 0, "y": 0, "yaw": 0, "note": "ALFWorld: no coordinates"})


@app.get("/status")
def arm_status():
    return jsonify({"holding": get_env().holding, "note": "ALFWorld: symbolic state only"})


@app.get("/map_data")
def map_data():
    return jsonify({"note": "ALFWorld: no map"})


# ── action endpoints (POST) ────────────────────────────────────────────────────

@app.post("/nav")
def nav():
    body = request.get_json(force=True, silent=True) or {}
    target = body.get("target")
    if not target or not isinstance(target, str):
        return jsonify({"success": False, "result": "ALFWorld /nav requires {\"target\": \"<name>\"}; coordinates not supported"})
    return jsonify(get_env().navigate_to(target))


@app.post("/grasp")
def grasp():
    body = request.get_json(force=True, silent=True) or {}
    obj_name = body.get("obj_name") or body.get("object_name")
    if not obj_name:
        return jsonify({"success": False, "result": "missing obj_name"})
    return jsonify(get_env().grasp(str(obj_name)))


@app.post("/place")
def place():
    body = request.get_json(force=True, silent=True) or {}
    obj_name = body.get("obj_name") or body.get("object_name")
    target = body.get("target")
    if isinstance(target, (list, tuple)):
        return jsonify({"success": False, "result": "ALFWorld /place requires target as string name, not coordinates"})
    if not obj_name or not target:
        return jsonify({"success": False, "result": "missing obj_name or target"})
    return jsonify(get_env().place(str(obj_name), str(target)))


@app.post("/raw")
def raw():
    """Execute an arbitrary admissible command (open/heat/cool/clean/toggle etc.)."""
    body = request.get_json(force=True, silent=True) or {}
    cmd = body.get("command", "")
    if not cmd:
        return jsonify({"success": False, "result": "missing command"})
    return jsonify(get_env().raw(cmd))


@app.post("/screenshot")
def screenshot():
    return jsonify({"success": False, "result": "ALFWorld text mode: no screenshot"})


@app.post("/move_duration")
def move_duration():
    return jsonify({"success": False, "result": "ALFWorld: no continuous movement"})
