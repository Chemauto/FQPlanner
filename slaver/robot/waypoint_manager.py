"""
waypoint_manager.py - 工作点管理器
根据目标物体名或坐标，找到最近的导航工作点
"""

import os
import sys
import math
import json
import numpy as np
import requests
import yaml

_WAYPOINTS_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', 'serve', 'scene', 'config', 'waypoints.yaml'
)
_NAV2_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', 'nav2', 'config.yaml'
)
_FREE_POINTS_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', 'nav2', 'maps', 'free_points.json'
)

_waypoints_cache = None
_free_points_cache = None


def load_waypoints():
    global _waypoints_cache
    if _waypoints_cache is not None:
        return _waypoints_cache
    with open(_WAYPOINTS_PATH, 'r') as f:
        data = yaml.safe_load(f)
    _waypoints_cache = data['waypoints']
    print(f"[waypoint] 加载了 {len(_waypoints_cache)} 个工作点", file=sys.stderr)
    return _waypoints_cache


def load_free_points():
    global _free_points_cache
    if _free_points_cache is not None:
        return _free_points_cache
    with open(_FREE_POINTS_PATH, 'r') as f:
        data = json.load(f)
    _free_points_cache = [
        {
            "name": p['name'],
            "pos": [p['x'], p['y']],
            "serves": [],
        }
        for p in data.get('points', [])
    ]
    print(f"[waypoint] 加载了 {len(_free_points_cache)} 个可通行点", file=sys.stderr)
    return _free_points_cache


def load_reach_limits():
    try:
        with open(_NAV2_CONFIG_PATH, 'r') as f:
            cfg = yaml.safe_load(f)
        wp_cfg = cfg.get('waypoints', {})
        return wp_cfg.get('min_dist', 0.1), wp_cfg.get('max_reach', 1.0)
    except Exception as e:
        print(f"[waypoint] 读取工作点距离配置失败，使用默认值: {e}", file=sys.stderr)
        return 0.1, 1.0


def _load_perception_config():
    """读取感知模式配置"""
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config.yaml')
    with open(config_path) as f:
        config = yaml.safe_load(f)
    return config.get('perception', {}).get('use_realtime_coords', True)


def get_object_pos(obj_name):
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
        resp = requests.get("http://127.0.0.1:5002/objects", timeout=3)
        if resp.status_code == 200:
            objects = resp.json()
            if isinstance(objects, dict) and "objects" in objects:
                objects = objects["objects"]
            if obj_name in objects:
                return objects[obj_name]['pos']
            candidates = [k for k in objects if obj_name in k or k in obj_name]
            if candidates:
                return objects[candidates[0]]['pos']
        resp = requests.get("http://127.0.0.1:5002/fixtures", timeout=3)
        if resp.status_code == 200:
            fixtures = resp.json()
            if isinstance(fixtures, dict) and "fixtures" in fixtures:
                fixtures = fixtures["fixtures"]
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


def _find_in_scene_state(target_name):
    """
    记忆模式：从 scene_state.yaml 直接查找目标对应的工作点。
    支持家具模糊匹配（sink ↔ sink_island_group）和物体精确匹配。
    返回 waypoint dict 或 None。
    """
    try:
        _serve_path = os.path.normpath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)), '..', '..', 'serve'))
        if _serve_path not in sys.path:
            sys.path.insert(0, _serve_path)
        from scene.scene_memory import load_state

        state = load_state()
        waypoints = load_waypoints()
        wp_map = {wp['name']: wp for wp in waypoints}

        for loc, info in state['locations'].items():
            if loc == 'robot_hand':
                continue
            wp = wp_map.get(loc)
            if not wp:
                continue
            # 家具模糊匹配（如 sink ↔ sink_island_group）
            fixture = info.get('fixture') or ''
            if fixture and (target_name in fixture or fixture in target_name):
                print(f"[waypoint] 记忆: '{target_name}' → 家具 '{fixture}' @ {loc}", file=sys.stderr)
                return {'name': wp['name'], 'x': wp['pos'][0], 'y': wp['pos'][1],
                        'yaw_deg': wp.get('yaw_deg', 0.0)}
            # 物体精确匹配
            if target_name in (info.get('objects') or []):
                print(f"[waypoint] 记忆: '{target_name}' 在 {loc}", file=sys.stderr)
                return {'name': wp['name'], 'x': wp['pos'][0], 'y': wp['pos'][1],
                        'yaw_deg': wp.get('yaw_deg', 0.0)}
    except Exception as e:
        print(f"[waypoint] scene_state 查询失败: {e}", file=sys.stderr)
    return None


def _wp_dict(wp):
    return {'name': wp['name'], 'x': wp['pos'][0], 'y': wp['pos'][1],
            'yaw_deg': wp.get('yaw_deg', 0.0)}


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

    waypoints = load_waypoints()

    # ── 记忆模式：直接查 scene_state，不查实时坐标 ──────────────────────────
    if target_name and not _load_perception_config():
        wp = _find_in_scene_state(target_name)
        if wp:
            return wp
        # scene_state 未记录，按 serves 回退
        serving = [w for w in waypoints
                   if any(target_name in s or s in target_name for s in w.get('serves', []))]
        if serving:
            print(f"[waypoint] 记忆(serves回退): '{target_name}' → {serving[0]['name']}", file=sys.stderr)
            return _wp_dict(serving[0])
        print(f"[waypoint] 记忆模式未找到 '{target_name}'，使用第一个工作点", file=sys.stderr)
        return _wp_dict(waypoints[0])

    # ── 实时模式：用名称查实时坐标 ──────────────────────────────────────────
    if target_name and target_pos is None:
        pos = get_object_pos(target_name)
        if pos:
            target_pos = pos

    if target_pos is None:
        # 位置查询失败，退而按名称匹配 serves 字段
        if target_name:
            serving = [wp for wp in waypoints
                       if any(target_name in s or s in target_name
                              for s in wp.get('serves', []))]
            if serving:
                wp = serving[0]
                print(f"[waypoint] 位置未知，按名称匹配工作点: {wp['name']} (serves={wp['serves']})",
                      file=sys.stderr)
                return {
                    "name": wp['name'],
                    "x": wp['pos'][0],
                    "y": wp['pos'][1],
                    "yaw_deg": wp.get('yaw_deg', 0.0),
                }
        print(f"[waypoint] 无法确定目标位置，使用第一个工作点", file=sys.stderr)
        wp = waypoints[0]
        return {
            "name": wp['name'],
            "x": wp['pos'][0],
            "y": wp['pos'][1],
            "yaw_deg": wp.get('yaw_deg', 0.0),
        }

    tp = np.array(target_pos[:2])

    use_realtime = _load_perception_config()

    min_dist, max_reach = load_reach_limits()

    def within_reach(wp):
        dist = np.linalg.norm(np.array(wp['pos'][:2]) - tp)
        return min_dist <= dist <= max_reach

    if use_realtime and target_name:
        # 实时模式：先按 serves 缩小候选范围
        serving = [wp for wp in waypoints
                   if any(target_name in s or s in target_name
                          for s in wp.get('serves', []))]
        free_points = load_free_points()
        serving_reachable = [wp for wp in serving if within_reach(wp)]
        free_reachable = [wp for wp in free_points if within_reach(wp)]
        all_reachable = [wp for wp in waypoints if within_reach(wp)]
        candidates = serving_reachable or serving or free_reachable or all_reachable or waypoints
    else:
        # 记忆模式：物体位置动态变化，serves 不可靠，直接用全部按距离选
        candidates = waypoints

    if not candidates:
        candidates = waypoints

    # 按距离目标排序，选最近的
    candidates_sorted = sorted(
        candidates,
        key=lambda wp: np.linalg.norm(np.array(wp['pos'][:2]) - tp)
    )
    best = candidates_sorted[0]
    best_xy = best['pos'][:2]

    # 工作点生成器已经根据可达区域和目标家具方向写入 yaw_deg。
    # 这里必须使用预存角度，否则会出现 nav_011 应为 90° 却被重算成 0° 的问题。
    yaw_deg = float(best.get('yaw_deg', 0.0))

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
