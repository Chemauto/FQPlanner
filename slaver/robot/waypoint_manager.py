"""
waypoint_manager.py - 工作点管理器
根据目标物体名或坐标，找到最近的导航工作点
"""

import os
import numpy as np
import requests
import yaml


# 工作点配置路径（相对于 slaver/）
_WAYPOINTS_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', 'serve', 'scene', 'config', 'waypoints.yaml'
)

_waypoints_cache = None


def load_waypoints():
    global _waypoints_cache
    if _waypoints_cache is not None:
        return _waypoints_cache
    with open(_WAYPOINTS_PATH, 'r') as f:
        _waypoints_cache = yaml.safe_load(f)['waypoints']
    return _waypoints_cache


def get_object_pos(obj_name):
    """从仿真查询物体或家具坐标"""
    try:
        # 先查可操作物体
        resp = requests.get("http://127.0.0.1:5001/objects", timeout=3)
        if resp.status_code == 200:
            objects = resp.json()
            if obj_name in objects:
                return objects[obj_name]['pos']

        # 再查家具
        resp = requests.get("http://127.0.0.1:5001/fixtures", timeout=3)
        if resp.status_code == 200:
            fixtures = resp.json()
            # 模糊匹配
            candidates = [k for k in fixtures if obj_name in k and 'main' in k]
            if not candidates:
                candidates = [k for k in fixtures if obj_name in k]
            if candidates:
                return fixtures[candidates[0]]['pos']
    except Exception as e:
        print(f"[waypoint] 查询物体位置失败: {e}")
    return None


def find_waypoint(target) -> dict:
    """
    根据目标（物体名或坐标字符串）找最近工作点

    Args:
        target: 物体名 "apple" 或坐标字符串 "(1.5, -0.3)"

    Returns:
        dict: {"name": ..., "pos": [x, y], "serves": [...]}
    """
    waypoints = load_waypoints()

    # 解析目标坐标
    target_pos = None
    target_name = None

    # 判断是坐标还是物体名
    if '(' in str(target) or ',' in str(target):
        # 是坐标字符串，解析出 x, y
        try:
            cleaned = str(target).strip().strip('()')
            parts = [float(x.strip()) for x in cleaned.split(',')]
            target_pos = parts[:2]
        except Exception:
            pass
    else:
        # 是物体名
        target_name = str(target).strip()

    # 先按 serves 匹配
    if target_name:
        serving = [w for w in waypoints if target_name in w.get('serves', [])]
        if serving:
            # 如果有多个服务该物体的工作点，找最近的
            if target_pos is None:
                pos = get_object_pos(target_name)
                if pos:
                    target_pos = pos[:2]

            if target_pos:
                tp = np.array(target_pos)
                serving.sort(key=lambda w: np.linalg.norm(np.array(w['pos']) - tp))
            return serving[0]

    # fallback：按距离找最近工作点
    if target_pos is None and target_name:
        pos = get_object_pos(target_name)
        if pos:
            target_pos = pos[:2]

    if target_pos:
        tp = np.array(target_pos)
        waypoints_sorted = sorted(
            waypoints,
            key=lambda w: np.linalg.norm(np.array(w['pos']) - tp)
        )
        return waypoints_sorted[0]

    # 最终 fallback：返回第一个工作点
    print(f"[waypoint] 无法确定目标位置，使用默认工作点")
    return waypoints[0]