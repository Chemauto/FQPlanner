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

## ROS2 SLAM / Nav2 桥接

真实 SLAM/Nav2 需要 ROS2 标准话题：`/scan`、`/odom`、`/tf` 和 `/cmd_vel`。MuJoCo 后端通过 `GET /scan` 提供二维激光扫描数据，ROS2 bridge 包放在：

```text
../ros2_ws/src/fqplanner_nav_bridge
```

构建：

```bash
cd ../ros2_ws
colcon build --packages-select fqplanner_nav_bridge
source install/setup.bash
```

SLAM 建图：

```bash
cd ../FQPlanner_Mujoco
ros2 launch fqplanner_nav_bridge mujoco_slam.launch.py backend_url:=http://127.0.0.1:5001
```

Nav2 导航：

```bash
cd ../FQPlanner_Mujoco
ros2 launch fqplanner_nav_bridge mujoco_navigation.launch.py backend_url:=http://127.0.0.1:5001
```

如果不在项目根目录启动，设置：

```bash
export FQPLANNER_ROOT=/path/to/FQPlanner_Mujoco
```

`nav2_goal_bridge` 默认监听 `http://127.0.0.1:5102`，会把 `/nav` 转成 Nav2 `NavigateToPose` action，其它后端请求代理回 MuJoCo。
