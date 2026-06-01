"""
底盘导航模块 - A* 路径规划 + PD 轨迹跟踪
所有导航逻辑在此完成，不依赖仿真后端，便于迁移到实机。
"""

import heapq
import json
import math
import os
import sys

import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from serve.sim import navigate, get_base_status

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from waypoint_manager import find_waypoint

# ============================================================
# A* 路径规划器
# ============================================================

NAV2_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'nav2')
CONFIG_PATH = os.path.join(NAV2_DIR, "config.yaml")


def _load_planner_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f).get("path_planner", {})


def _build_graph(points, neighbor_radius):
    """构建邻接图"""
    n = len(points)
    radius_sq = neighbor_radius ** 2
    adj = [[] for _ in range(n)]
    for i in range(n):
        xi, yi = points[i]
        for j in range(i + 1, n):
            xj, yj = points[j]
            dist_sq = (xi - xj) ** 2 + (yi - yj) ** 2
            if dist_sq < radius_sq:
                dist = math.sqrt(dist_sq)
                adj[i].append((j, dist))
                adj[j].append((i, dist))
    return adj


def _astar(points, adj, start_idx, goal_idx):
    """A* 最短路径搜索"""
    gx, gy = points[goal_idx]
    open_set = [(0.0, start_idx)]
    g_score = {start_idx: 0.0}
    came_from = {}
    closed = set()

    while open_set:
        _, current = heapq.heappop(open_set)
        if current == goal_idx:
            path = []
            while current in came_from:
                path.append(current)
                current = came_from[current]
            path.append(start_idx)
            path.reverse()
            return path
        if current in closed:
            continue
        closed.add(current)
        for neighbor, dist in adj[current]:
            if neighbor in closed:
                continue
            tentative_g = g_score[current] + dist
            if tentative_g < g_score.get(neighbor, float("inf")):
                g_score[neighbor] = tentative_g
                came_from[neighbor] = current
                nx, ny = points[neighbor]
                h = math.hypot(nx - gx, ny - gy)
                heapq.heappush(open_set, (tentative_g + h, neighbor))
    return None


def _simplify_path(points_xy):
    """去掉三点共线的中间点"""
    if len(points_xy) <= 2:
        return points_xy
    result = [points_xy[0]]
    for i in range(1, len(points_xy) - 1):
        px, py = result[-1]
        cx, cy = points_xy[i]
        nx, ny = points_xy[i + 1]
        if abs((cx - px) * (ny - py) - (cy - py) * (nx - px)) > 0.01:
            result.append(points_xy[i])
    result.append(points_xy[-1])
    return result


def plan_path(start_xy, goal_xy):
    """
    A* 路径规划：从起点到终点，绕过障碍物

    Args:
        start_xy: [x, y]
        goal_xy:  [x, y]

    Returns:
        [{"x": float, "y": float}, ...]
    """
    cfg = _load_planner_config()
    fp_path = os.path.join(NAV2_DIR, cfg.get("free_points_path", "maps/free_points.json"))
    neighbor_radius = cfg.get("neighbor_radius", 0.8)
    connect_n = cfg.get("connect_neighbors", 3)

    with open(fp_path) as f:
        fp_data = json.load(f)

    all_points = [(p["x"], p["y"]) for p in fp_data["points"]]
    adj = _build_graph(all_points, neighbor_radius)

    # 找离起终点最近的 N 个点
    def nearest(xy, count):
        dists = sorted(
            ((math.hypot(px - xy[0], py - xy[1]), i) for i, (px, py) in enumerate(all_points))
        )
        return [(idx, d) for d, idx in dists[:count]]

    start_nbrs = nearest(start_xy, connect_n)
    goal_nbrs = nearest(goal_xy, connect_n)

    best_path = None
    best_cost = float("inf")
    for si, s_dist in start_nbrs:
        for gi, g_dist in goal_nbrs:
            path = _astar(all_points, adj, si, gi)
            if path is None:
                continue
            cost = s_dist
            for k in range(len(path) - 1):
                a, b = all_points[path[k]], all_points[path[k + 1]]
                cost += math.hypot(a[0] - b[0], a[1] - b[1])
            cost += g_dist
            if cost < best_cost:
                best_cost = cost
                best_path = path

    if best_path is None:
        return [{"x": start_xy[0], "y": start_xy[1]}, {"x": goal_xy[0], "y": goal_xy[1]}]

    coords = [all_points[i] for i in best_path]
    coords = _simplify_path(coords)

    result = [{"x": start_xy[0], "y": start_xy[1]}]
    for x, y in coords:
        result.append({"x": round(x, 3), "y": round(y, 3)})
    result.append({"x": goal_xy[0], "y": goal_xy[1]})
    return result


# ============================================================
# MCP 工具注册
# ============================================================

def register_tools(mcp):

    @mcp.tool()
    async def navigate_to_target(target: str) -> str:
        """导航到目标位置。

        将机器人底盘导航到场景中的指定位置。
        支持坐标格式："(x, y)" 或 "x, y"
        也支持物体名称："apple"、"counter" 等，会自动查找最近工作点。

        Args:
            target: 导航目标，可以是物体名称或坐标字符串

        Returns:
            包含结果消息和状态更新的 JSON 字符串。

        Examples:
            navigate_to_target(target="(1.5, -0.5)")
            navigate_to_target(target="apple")
        """
        print(f"[base] 导航请求: '{target}'", file=sys.stderr)

        # 先尝试解析为坐标
        try:
            cleaned = target.strip().strip("()")
            parts = [float(x.strip()) for x in cleaned.split(",")]
            if len(parts) >= 2:
                x, y = parts[0], parts[1]
                w = parts[2] if len(parts) > 2 else None
                return await _do_navigate(x, y, w, target)
        except ValueError:
            pass

        # 是物体名称，找最佳工作点
        wp = find_waypoint(target)
        return await _do_navigate(wp['x'], wp['y'], wp['yaw_deg'], target)

    async def _do_navigate(x, y, yaw_deg, target):
        status = get_base_status()
        start = [status["pos"][0], status["pos"][1]]

        # A* 路径规划
        path = plan_path(start, [x, y])

        if len(path) > 2:
            # 逐点导航
            print(f"[base] A* 绕障路径: {len(path)} 个点", file=sys.stderr)
            for i, wp in enumerate(path[1:], 1):
                last = (i == len(path) - 1)
                result = navigate(wp["x"], wp["y"], target_yaw=yaw_deg if last else None)
                if not result.get("success"):
                    break
        else:
            print(f"[base] 直线导航", file=sys.stderr)
            result = navigate(x, y, target_yaw=yaw_deg)

        if result.get("success"):
            pos = result.get("pos", [0, 0, 0])
            yaw = result.get("yaw", 0)
            response = f"导航成功，当前位置: [{pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}], 朝向: {yaw:.1f}°"
            return json.dumps([response, {
                "_status": "success",
                "position": target,
                "coordinates": pos,
            }])
        else:
            msg = result.get("result", f"导航到 {target} 失败，请重试。")
            return json.dumps([msg, {"_status": "failure"}])

    print("[base.py] 底盘控制模块已注册 (A* 路径规划)", file=sys.stderr)
