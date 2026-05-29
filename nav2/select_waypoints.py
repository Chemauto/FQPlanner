"""
select_waypoints.py
从 free_points.json 里自动选出覆盖所有物体/家具的最少工作点
运行一次：python nav2/select_waypoints.py
"""

import json
import math
import requests
import yaml
import numpy as np
from pathlib import Path

FREE_POINTS_PATH = "nav2/maps/free_points.json"
OUTPUT_PATH = "serve/scene/config/waypoints.yaml"
MAX_REACH = 1     # 机械臂最大可达距离
MIN_DIST = 0.3    # 距家具最小安全距离


def get_scene_objects():
    """拉取所有可操作物体和主要家具坐标"""
    targets = {}

    # 可操作物体
    resp = requests.get("http://127.0.0.1:5001/objects", timeout=3)
    if resp.status_code == 200:
        for name, data in resp.json().items():
            targets[name] = data['pos'][:2]

    # 主要家具：明确列出需要的
    FIXTURE_SIMPLE = {
        "counter": "counter_1_main_group",
        "island":  "island_island_group",
        "stove":   "stovetop_main_group",
        "sink":    "sink_island_group",
    }

    resp = requests.get("http://127.0.0.1:5001/fixtures", timeout=3)
    if resp.status_code == 200:
        fixtures = resp.json()
        for simple_name, fixture_key in FIXTURE_SIMPLE.items():
            if fixture_key in fixtures:
                targets[simple_name] = fixtures[fixture_key]['pos'][:2]

    return targets


def load_free_points():
    with open(FREE_POINTS_PATH) as f:
        data = json.load(f)
    return data['points']


def find_covering_waypoints(free_points, targets):
    """
    贪心算法：选最少的工作点覆盖所有目标物体
    每个工作点覆盖距离在 [MIN_DIST, MAX_REACH] 内的所有目标
    """
    # 预计算每个 free_point 能覆盖哪些目标
    coverage = {}
    for p in free_points:
        pp = np.array([p['x'], p['y']])
        covered = set()
        for name, pos in targets.items():
            dist = np.linalg.norm(pp - np.array(pos))
            if MIN_DIST <= dist <= MAX_REACH:
                covered.add(name)
        if covered:
            coverage[p['name']] = {
                'point': p,
                'covers': covered,
            }

    # 贪心选点：每次选覆盖未覆盖目标最多的点
    uncovered = set(targets.keys())
    selected = []

    while uncovered:
        best_name = None
        best_covers = set()

        for pname, info in coverage.items():
            new_covers = info['covers'] & uncovered
            if len(new_covers) > len(best_covers):
                best_covers = new_covers
                best_name = pname

        if best_name is None:
            print(f"[警告] 以下目标无法被任何工作点覆盖: {uncovered}")
            break

        p = coverage[best_name]['point']
        selected.append({
            'name': best_name,
            'point': p,
            'serves': sorted(list(best_covers)),
        })
        uncovered -= best_covers
        print(f"选择工作点 {best_name} @ [{p['x']}, {p['y']}], 覆盖: {sorted(best_covers)}")

    return selected


def compute_yaw(from_xy, to_xy):
    dx = to_xy[0] - from_xy[0]
    dy = to_xy[1] - from_xy[1]
    yaw = math.degrees(math.atan2(dy, dx))
    return yaw

# 在 save_waypoints 之前加这段，强制补充家具工作点
def add_fixture_waypoints(selected, free_points, targets, fixture_names):
    """为指定家具强制添加最近的工作点，即使贪心已覆盖"""
    existing_names = {item['name'] for item in selected}
    
    for fname in fixture_names:
        if fname not in targets:
            continue
        fpos = np.array(targets[fname])
        
        # 找距离家具 [MIN_DIST, MAX_REACH] 内最近的 free_point
        candidates = []
        for p in free_points:
            pp = np.array([p['x'], p['y']])
            dist = np.linalg.norm(pp - fpos)
            if MIN_DIST <= dist <= MAX_REACH:
                candidates.append((dist, p))
        
        if not candidates:
            print(f"[警告] 找不到 {fname} 附近的工作点")
            continue
            
        candidates.sort(key=lambda x: x[0])
        best = candidates[0][1]
        
        # 如果这个点已经被选了就跳过
        if best['name'] in existing_names:
            print(f"{fname} 已被现有工作点 {best['name']} 覆盖，跳过")
            continue
        
        # 添加新工作点
        selected.append({
            'name': best['name'],
            'point': best,
            'serves': [fname],
        })
        existing_names.add(best['name'])
        print(f"为 {fname} 补充工作点 {best['name']} @ [{best['x']}, {best['y']}]")
    
    return selected

def save_waypoints(selected, targets):
    waypoints = []
    for item in selected:
        p = item['point']
        serves = item['serves']

        # 朝向：取 serves 里第一个有坐标的目标
        yaw_deg = 0.0
        for name in serves:
            if name in targets:
                yaw_deg = compute_yaw([p['x'], p['y']], targets[name])
                break

        waypoints.append({
            'name': item['name'],
            'pos': [p['x'], p['y']],
            'yaw_deg': round(yaw_deg, 1),
            'serves': serves,
        })

    Path(OUTPUT_PATH).parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, 'w') as f:
        yaml.dump({'waypoints': waypoints}, f, allow_unicode=True, default_flow_style=False)

    print(f"\n共选出 {len(waypoints)} 个工作点，保存到 {OUTPUT_PATH}")
    return waypoints


if __name__ == "__main__":
    print("拉取场景物体...")
    targets = get_scene_objects()
    print(f"找到 {len(targets)} 个目标: {list(targets.keys())}")

    print("\n加载 free_points...")
    free_points = load_free_points()
    print(f"共 {len(free_points)} 个可通行点")

    print("\n计算最优工作点覆盖...")
    selected = find_covering_waypoints(free_points, targets)

    # 强制为主要家具补充工作点
    MUST_COVER = ["counter", "island", "stove", "sink"]
    selected = add_fixture_waypoints(selected, free_points, targets, MUST_COVER)

    print("\n保存工作点...")
    save_waypoints(selected, targets)