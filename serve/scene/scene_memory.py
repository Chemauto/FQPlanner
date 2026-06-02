"""
scene_memory.py - 场景状态记忆
记录物体相对位置（在哪个家具/位置上），在动作执行后自动更新。
重启仿真时自动恢复为初始状态。
"""

import os
import yaml
import shutil
from datetime import datetime

_DIR = os.path.join(os.path.dirname(__file__), 'config')
STATE_PATH = os.path.join(_DIR, 'scene_state.yaml')
INITIAL_PATH = os.path.join(_DIR, 'scene_state_initial.yaml')
WAYPOINTS_PATH = os.path.join(_DIR, 'waypoints.yaml')


def _load_waypoint_coords() -> dict:
    """返回工作点名→坐标的映射"""
    with open(WAYPOINTS_PATH) as f:
        data = yaml.safe_load(f)
    return {wp['name']: wp['pos'][:2] for wp in data['waypoints']}


def load_state() -> dict:
    with open(STATE_PATH, 'r') as f:
        return yaml.safe_load(f)


def save_state(state: dict):
    state['last_updated'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(STATE_PATH, 'w') as f:
        yaml.dump(state, f, allow_unicode=True, default_flow_style=False)


def reset_to_initial():
    shutil.copy(INITIAL_PATH, STATE_PATH)
    print("[SceneMemory] 场景状态已重置为初始状态")


def get_object_location(obj_name: str) -> str:
    """返回物体所在的工作点名，如 'nav_012'"""
    state = load_state()
    for loc, info in state['locations'].items():
        if obj_name in (info.get('objects') or []):
            return loc
    return 'unknown'


def get_object_coords(obj_name: str) -> list:
    """
    返回物体所在工作点的坐标
    记忆模式下用这个而不是实时 API
    """
    location = get_object_location(obj_name)
    if location == 'unknown' or location == 'robot_hand':
        return None
    coords = _load_waypoint_coords()
    wp_coords = coords.get(location)
    if wp_coords:
        return [wp_coords[0], wp_coords[1], 0.9]
    return None


def move_object(obj_name: str, to_location: str):
    """更新物体位置，to_location 是工作点名或 'robot_hand'"""
    state = load_state()
    from_location = 'unknown'
    for loc, info in state['locations'].items():
        objs = info.get('objects') or []
        if obj_name in objs:
            objs.remove(obj_name)
            info['objects'] = objs
            from_location = loc
            break

    if to_location not in state['locations']:
        state['locations'][to_location] = {'fixture': None, 'objects': []}
    objs = state['locations'][to_location].get('objects') or []
    if obj_name not in objs:
        objs.append(obj_name)
    state['locations'][to_location]['objects'] = objs

    save_state(state)
    print(f"[SceneMemory] {obj_name}: {from_location} → {to_location}")


def get_location_objects(location: str) -> list:
    state = load_state()
    return state['locations'].get(location, {}).get('objects') or []


def get_all_locations() -> dict:
    state = load_state()
    return {loc: info.get('objects') or []
            for loc, info in state['locations'].items()}


def coords_to_waypoint(pos: list) -> str:
    """根据放置坐标找最近的工作点名，总是返回最近的"""
    import numpy as np
    if pos is None:
        return 'unknown'
    p = np.array(pos[:2])
    coords = _load_waypoint_coords()
    
    best_name = 'unknown'
    best_dist = float('inf')  # 不设上限，总是返回最近的
    for name, wp_coords in coords.items():
        dist = np.linalg.norm(p - np.array(wp_coords))
        if dist < best_dist:
            best_dist = dist
            best_name = name
    
    print(f"[SceneMemory] 放置位置 {p.tolist()} → 最近工作点 {best_name} (dist={best_dist:.2f})")
    return best_name