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


def get_object_pos(obj_name):
    """查询单个物体或家具的实时坐标，返回 [x, y, z]"""
    try:
        # 先查可操作物体
        resp = requests.get("http://127.0.0.1:5001/objects", timeout=3)
        if resp.status_code == 200:
            objects = resp.json()
            if obj_name in objects:
                return objects[obj_name]['pos']

        # 再查 fixtures 模糊匹配
        resp = requests.get("http://127.0.0.1:5001/fixtures", timeout=3)
        if resp.status_code == 200:
            fixtures = resp.json()
            if obj_name in fixtures:
                return fixtures[obj_name]['pos']
            # 模糊匹配：优先含 main 的
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

    # 先找 serves 里包含目标名的候选工作点
    if target_name:
        serving = [
            wp for wp in waypoints
            if any(
                target_name in s or s in target_name
                for s in wp.get('serves', [])
            )
        ]
    else:
        serving = []

    min_dist, max_reach = load_reach_limits()

    def within_reach(wp):
        dist = np.linalg.norm(np.array(wp['pos'][:2]) - tp)
        return min_dist <= dist <= max_reach

    free_points = load_free_points()
    serving_reachable = [wp for wp in serving if within_reach(wp)]
    free_reachable = [wp for wp in free_points if within_reach(wp)]
    all_reachable = [wp for wp in waypoints if within_reach(wp)]

    # serves 只作为优先级，不能覆盖实时距离约束；预生成工作点失效时用 free_points 兜底。
    candidates = serving_reachable or free_reachable or all_reachable or serving or waypoints

    # 按距离目标排序，选最近的
    candidates_sorted = sorted(
        candidates,
        key=lambda wp: np.linalg.norm(np.array(wp['pos'][:2]) - tp)
    )
    best = candidates_sorted[0]
    best_xy = best['pos'][:2]

    # 动态计算朝向：工作点指向目标，snap 到 90°
    # yaw=0→+X, 90→+Y (CCW)，atan2(dy,dx) 直接给出正确朝向
    dx = target_pos[0] - best_xy[0]
    dy = target_pos[1] - best_xy[1]
    raw_yaw = math.degrees(math.atan2(dy, dx))
    angles = [0, 90, 180, 270]
    yaw_raw = raw_yaw % 360
    yaw_deg = float(min(angles, key=lambda a: min(abs(a - yaw_raw), 360 - abs(a - yaw_raw))))

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
