"""
waypoint_manager.py - 工作点管理器
根据目标物体名或坐标，找到最近的导航工作点
"""

import os
import sys
import math
import numpy as np
import requests
import yaml

_WAYPOINTS_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', 'serve', 'scene', 'config', 'waypoints.yaml'
)

_waypoints_cache = None


def load_waypoints():
    global _waypoints_cache
    if _waypoints_cache is not None:
        return _waypoints_cache
    with open(_WAYPOINTS_PATH, 'r') as f:
        data = yaml.safe_load(f)
    _waypoints_cache = data['waypoints']
    print(f"[waypoint] 加载了 {len(_waypoints_cache)} 个工作点", file=sys.stderr)
    return _waypoints_cache

def get_object_pos(obj_name):
    """查询物体坐标：记忆模式用场景状态，实时模式调API"""
    # 读配置
    import yaml, os
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.yaml')
    with open(config_path) as f:
        config = yaml.safe_load(f)
    use_realtime = config.get('perception', {}).get('use_realtime_coords', True)
    
    if not use_realtime:
        # 记忆模式：直接跳到记忆查询，不调任何 API
        try:
            _serve_path = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'serve'))
            if _serve_path not in sys.path:
                sys.path.insert(0, _serve_path)
            from scene.scene_memory import get_object_coords, get_object_location
            waypoints = load_waypoints()
            FIXTURE_KEYWORDS = ['counter', 'island', 'sink', 'stove', 'floor', 'fridge', 'microwave', 'oven']
            simple_name = None
            for kw in FIXTURE_KEYWORDS:
                if kw in obj_name:
                    simple_name = kw
                    break
            if simple_name:
                for wp in waypoints:
                    serves = wp.get('serves') or []
                    if any(simple_name in s or s in simple_name for s in serves):
                        coords = wp['pos'][:2]
                        print(f"[waypoint] 记忆模式: {obj_name} 是家具({simple_name}) → {wp['name']} @ {coords}", file=sys.stderr)
                        return [coords[0], coords[1], 0.9]
            coords = get_object_coords(obj_name)
            if coords:
                location = get_object_location(obj_name)
                print(f"[waypoint] 记忆模式: {obj_name} 在工作点 {location} @ {coords[:2]}", file=sys.stderr)
                return coords
        except Exception as e:
            print(f"[waypoint] 记忆模式查询失败: {e}", file=sys.stderr)
        return None
    
    # 实时模式：调 API
    try:
        resp = requests.get("http://127.0.0.1:5001/objects", timeout=3)
        if resp.status_code == 200:
            objects = resp.json()
            if obj_name in objects:
                return objects[obj_name]['pos']
        resp = requests.get("http://127.0.0.1:5001/fixtures", timeout=3)
        if resp.status_code == 200:
            fixtures = resp.json()
            if obj_name in fixtures:
                return fixtures[obj_name]['pos']
            candidates = [k for k in fixtures if obj_name in k and 'main' in k]
            if not candidates:
                candidates = [k for k in fixtures if obj_name in k]
            if candidates:
                return fixtures[candidates[0]]['pos']
    except Exception as e:
        print(f"[waypoint] 查询物体位置失败: {e}", file=sys.stderr)
    return None


def find_waypoint(target):
    """
    根据目标名称或坐标字符串，找最近的工作点并用预存的朝向

    Args:
        target: 物体名称（如 "apple"）或坐标字符串（如 "(1.5, -0.3)"）

    Returns:
        dict: {"name": ..., "x": ..., "y": ..., "yaw_deg": ...}
    """
    target_pos = None
    target_name = None

    # 判断是坐标还是名称
    try:
        cleaned = str(target).strip().strip("()")
        parts = [float(x.strip()) for x in cleaned.split(",")]
        if len(parts) >= 2:
            target_pos = parts[:3]
    except ValueError:
        target_name = str(target).strip()

    # 用名称查实时坐标
    if target_name and target_pos is None:
        pos = get_object_pos(target_name)
        if pos:
            target_pos = pos

    waypoints = load_waypoints()

    if target_pos is None:
        print(f"[waypoint] 无法确定目标位置，使用第一个工作点", file=sys.stderr)
        wp = waypoints[0]
        return {
            "name": wp['name'],
            "x": wp['pos'][0],
            "y": wp['pos'][1],
            "yaw_deg": wp.get('yaw_deg', 0.0),
        }

    tp = np.array(target_pos[:2])

    # 记忆模式：纯距离选工作点；实时模式：优先 serves 匹配
    try:
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'config.yaml')
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        use_realtime = cfg.get('perception', {}).get('use_realtime_coords', True)
    except Exception:
        use_realtime = True

    if use_realtime and target_name:
        # 实时模式：先按 serves 缩小候选范围
        serving = [wp for wp in waypoints
                   if any(target_name in s or s in target_name
                          for s in wp.get('serves', []))]
        candidates = serving if serving else waypoints
    else:
        # 记忆模式：物体位置动态变化，serves 不可靠，直接用全部按距离选
        candidates = waypoints

    candidates_sorted = sorted(
        candidates,
        key=lambda wp: np.linalg.norm(np.array(wp['pos'][:2]) - tp)
    )
    best = candidates_sorted[0]
    best_xy = best['pos'][:2]

    # 直接用预存的朝向
    yaw_deg = best.get('yaw_deg', 0.0)

    print(
        f"[waypoint] 目标: '{target}' @ {tp.tolist()}, "
        f"工作点: {best['name']} @ {best_xy}, "
        f"朝向: {yaw_deg:.1f}°",
        file=sys.stderr
    )

    return {
        "name": best['name'],
        "x": best_xy[0],
        "y": best_xy[1],
        "yaw_deg": yaw_deg,
    }