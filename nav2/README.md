# 场景地图与工作点

从统一机器人后端生成占据地图，提取可通行点，选出最优导航工作点。当前默认后端是 XLeRobot MuJoCo。

所有参数统一配置在 `config.yaml` 中，三个脚本共享。


## 使用步骤

### 1. 生成地图

```bash
conda activate robocasa
python nav2/map_generator.py --from-sim
```

### 2. 提取可通行点

```bash
python nav2/free_points_generator.py
```

生成 `maps/free_points.json` 和 `maps/free_points_vis.png`。

### 3. 选工作点（需机器人后端已启动）

```bash
python nav2/workpoints_generator.py
```

生成三份输出：
- `serve/scene/config/waypoints.yaml` — 给 `waypoint_manager.py` 使用
- `maps/workpoints.json` — JSON 格式备份
- `maps/workpoints_vis.png` — 可视化图
