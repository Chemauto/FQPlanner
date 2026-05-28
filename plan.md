# Nav2 集成到 FQPlanner 仿真导航

## Context

当前 FQPlanner 的底盘导航使用简单的顺序 PD 控制器（x → y → yaw 三阶段），没有路径规划和避障能力。用户希望在现有 RoboCasa 仿真中引入 ROS2 Nav2，获得：
- 全局路径规划（A*/NavFn/Smac）
- 局部避障（DWB/MPPI Controller）
- 恢复行为（卡住自动恢复）

**关键发现**：ROS2 Humble 已安装在 `robocasa` conda 环境中，无需额外安装。

## 方案概述

在现有 Flask + MuJoCo 架构上**加一层 ROS2 桥接**，替换 PD 控制器为 Nav2 规划控制。不改动 Master/Slaver/Redis 等其他组件。

```
base.py (MCP) → sim.py → Flask /nav → Nav2 Bridge Node → ROS2 Nav2
                                                  ↕ HTTP
                                              MuJoCo 仿真
```

## 新增文件

```
FQPlanner/
├── nav2/                              # Nav2 集成模块（新增）
│   ├── bridge_node.py                 # MuJoCo ↔ ROS2 桥接节点
│   ├── map_generator.py              # 从 MuJoCo 场景生成 occupancy grid
│   ├── pandaomron.urdf               # Omron 底盘 URDF（用于 tf 树）
│   ├── nav2_params.yaml              # Nav2 配置参数
│   ├── launch.py                     # ROS2 launch 启动脚本
│   └── README.md                     # Nav2 使用说明
```

## 修改文件

| 文件 | 改动 |
|------|------|
| `serve/tools/move.py` | 新增 `nav_nav2()` 函数，调用 Nav2 action |
| `serve/service/server.py` | 新增 `/cmd_vel` 端点，nav 命令增加 Nav2 模式 |
| `slaver/robot/module/base.py` | 无需修改（接口不变） |

---

## Step 1: 生成厨房静态地图（map_generator.py）

从 `layout.yaml` 读取墙壁和家具位置，生成 2D occupancy grid（PGM/YAML 格式）。

- **厨房范围**：x ∈ [0, 6.4], y ∈ [-5.0, 0]
- **分辨率**：0.05m/pixel → 地图约 128 x 100 像素
- **障碍物来源**：
  - 墙壁：4 面墙（layout.yaml `room.walls`）
  - 台面/岛台：main_group, island_group 的 counters
  - 家具：stove, fridge, dishwasher 等大件
- **膨胀半径**：0.4m（Omron 底盘半径）

**参考文件**: `serve/scene/config/layout.yaml`

### 障碍物坐标清单（从 layout.yaml 提取）

| 名称 | 类型 | 位置 (x, y) | 尺寸 (w, d) |
|------|------|-------------|-------------|
| wall | 墙 | (3.2, 0) | 3.2 |
| wall_left | 墙 | (0, -2.5) | 2.5 |
| wall_right | 墙 | (6.4, -2.5) | 2.5 |
| wall_front | 墙 | (3.2, -5.0) | 3.2 |
| counter_corner | 台面 | (0.35, -0.325) | 0.70 x 0.65 |
| counter_1 | 台面 | align_to counter_corner | 2.0 x 0.65 |
| counter_main | 台面 | align_to counter_1 | 3.0 x 0.65 |
| island | 岛台 | (3.2, -2.725) | 2.5 x 1.55 |
| left_group counters | 台面 | group_pos (0, -3.5), z_rot 90° | 2.0 x 0.65 |
| right_group counters | 台面 | group_pos (6.4, -0.7), z_rot -90° | 2.0 x 0.65 |

---

## Step 2: 创建 Omron 底盘 URDF（pandaomron.urdf）

从 `omron_mobile_base.xml` 转换为 URDF，用于 ROS2 tf 树。只需底盘部分（Nav2 不关心机械臂）。

### URDF 结构
```
odom (frame)
  └── base_link
        ├── base_footprint (底盘碰撞体)
        └── imu_link (可选，用于传感器数据)
```

### ros2_control 接口
```xml
<ros2_control name="OmronBase" type="system">
  <hardware>
    <plugin>hardware_interface/SystemInterface</plugin>
  </hardware>
  <joint name="joint_mobile_forward">
    <command_interface name="velocity"/>
    <state_interface name="position"/><state_interface name="velocity"/>
  </joint>
  <joint name="joint_mobile_side">
    <command_interface name="velocity"/>
    <state_interface name="position"/><state_interface name="velocity"/>
  </joint>
  <joint name="joint_mobile_yaw">
    <command_interface name="velocity"/>
    <state_interface name="position"/><state_interface name="velocity"/>
  </joint>
</ros2_control>
```

**参考文件**:
- MuJoCo XML: `robosuite/models/assets/bases/omron_mobile_base.xml`
- Panda URDF 示例: `robosuite/models/assets/bullet_data/panda_description/urdf/panda_arm.urdf`

---

## Step 3: MuJoCo ↔ ROS2 桥接节点（bridge_node.py）

Python ROS2 节点，复用现有 Flask API，不直接操作 MuJoCo 对象。

### 数据流
```
读取（Flask → ROS2）:
  GET http://localhost:5001/base_status  →  发布 /odom + /tf   (20Hz)

写入（ROS2 → Flask）:
  订阅 /cmd_vel  →  POST http://localhost:5001/cmd_vel  (Twist → Vx,Vy,Vw)
```

### 发布的 Topics
| Topic | 类型 | 频率 | 来源 |
|-------|------|------|------|
| `/odom` | nav_msgs/Odometry | 20Hz | Flask /base_status |
| `/tf` | tf2_msgs/TFMessage | 20Hz | odom → base_link |
| `/map` | nav_msgs/OccupancyGrid | 1次 | 静态地图 |

### 订阅的 Topics
| Topic | 类型 | 用途 |
|-------|------|------|
| `/cmd_vel` | geometry_msgs/Twist | Nav2 输出的速度命令 |

### cmd_vel → MuJoCo 转换
```python
Vx = twist.linear.x    # action[7]
Vy = twist.linear.y    # action[8]（全向底盘支持侧移）
Vw = twist.angular.z   # action[9]
```

### 新增 Flask 端点（server.py）

```python
@app.route("/cmd_vel", methods=["POST"])
def api_cmd_vel():
    """接收 Nav2 速度命令，单步执行"""
    data = request.json or {}
    vx = data.get("vx", 0.0)
    vy = data.get("vy", 0.0)
    vw = data.get("vw", 0.0)
    # 直接调用 move()，不走队列（速度控制需要实时性）
    info = move(env, Vx=vx, Vy=vy, Vw=vw)
    return jsonify({"success": True, "pos": info["pos"]})
```

**注意**: `/cmd_vel` 可能需要绕过命令队列直接执行，因为 Nav2 controller 输出频率较高（10-20Hz），走队列会引入延迟。

---

## Step 4: Nav2 配置（nav2_params.yaml）

针对 Omron 全向底盘的关键参数：

### Planner Server
- **推荐**: NavFn（简单场景够用）
- **备选**: Smac Planner (Omni 模型，支持全向底盘)

### Controller Server
- **推荐**: DWB Local Planner
- **备选**: MPPI Controller（更现代，支持全向运动）

### Costmap 参数
```yaml
static_layer:
  map_topic: /map
  subscribe_to_updates: true

inflation_layer:
  cost_scaling_factor: 3.0
  inflation_radius: 0.55  # 底盘半径 + 安全余量

# 无 obstacle_layer（厨房场景静态）
```

### 速度限制
```yaml
max_vel_x: 0.5       # 保守起步，后续可调到 1.0
max_vel_y: 0.5       # 全向底盘
max_vel_theta: 0.5   # rad/s
min_vel_x: -0.5
min_vel_y: -0.5
```

### Recovery Behaviors
- `spin` — 原地旋转
- `backup` — 后退
- `wait` — 等待

---

## Step 5: ROS2 Launch 脚本（launch.py）

### 启动流程
1. **map_server** — 发布静态地图
2. **bridge_node** — MuJoCo ↔ ROS2 桥接
3. **robot_state_publisher** — 发布 URDF → tf 静态变换
4. **Nav2 bringup** — 启动完整导航栈

### 依赖检查
```bash
conda activate robocasa
# 验证 ROS2 可用
ros2 --version
python -c "import rclpy; print('ROS2 OK')"
# 检查 Nav2 是否安装
dpkg -l | grep nav2 || pip list | grep nav2
```

---

## Step 6: 改造导航调用

### move.py 新增函数

```python
def nav_nav2(x, y, w, timeout=120):
    """通过 Nav2 导航到目标位置"""
    import rclpy
    from nav2_simple_commander.robot_navigator import BasicNavigator
    # 发送 NavigateToPose goal
    # 等待结果
    # 返回与 nav() 相同格式
```

### server.py 修改

```python
elif cmd_type == "nav":
    if nav2_available():
        result = nav_nav2(params["x"], params["y"], params["w"])
    else:
        info = nav(env, **params)
        result = {"success": True, "pos": info["pos"], "yaw": info["yaw_deg"]}
```

---

## 启动流程

```bash
# Terminal 1: Redis
redis-server

# Terminal 2: RoboCasa 仿真（原有，不变）
conda activate robocasa
cd serve && python main.py

# Terminal 3: Nav2 + Bridge（新增）
conda activate robocasa
cd nav2 && python launch.py

# Terminal 4: Master（原有，不变）
conda activate FQPlanner
cd master && python run.py

# Terminal 5: Slaver（原有，不变）
conda activate FQPlanner
cd slaver && python run.py
```

---

## 验证方法

### 1. 地图验证
```bash
ros2 topic echo /map --once
```

### 2. Odom 验证
```bash
ros2 topic echo /odom --once
```

### 3. 手动 cmd_vel 测试
```bash
ros2 topic pub /cmd_vel geometry_msgs/msg/Twist "{linear: {x: 0.3}}" --once
```

### 4. 单点导航测试
通过 MCP 工具调用：
```
navigate_to_target(target="counter")
```
观察：
- Nav2 是否规划出路径（`ros2 topic echo /plan`）
- 机器人是否按路径移动
- 到达后位置是否准确

### 5. 对比测试
分别用 PD 控制器和 Nav2 导航到同一目标：
- 路径质量
- 到达精度
- 是否避开了障碍物

---

## 风险与应对

| 风险 | 应对 |
|------|------|
| ROS2 与 MuJoCo 线程冲突 | 桥接节点走 Flask HTTP，不直接操作 env 对象 |
| Nav2 地图与仿真实际不一致 | 从 layout.yaml 自动导出障碍物坐标 |
| Omron 全向底盘 Nav2 支持不佳 | 用 Smac Omni planner，或 fallback 到差速模式 |
| cmd_vel 延迟过高 | 绕过命令队列直接调用 move()，或改用共享内存 |
| Nav2 未启动时系统崩溃 | nav 命令自动检测 Nav2 可用性，不可用时 fallback 到 PD |

---

## 参考

- [mujoco_ros2_control (DFKI-RIC)](https://github.com/dfki-ric/mujoco_ros2_control) — MuJoCo ROS2 桥接参考
- [Nav2 Documentation](https://docs.nav2.org/) — Nav2 官方文档
- [Smac Planner](https://docs.nav2.org/configuration/packages/smac/configuring-smac-hybrid.html) — 全向底盘规划器
- [Nav2 Tutorial](https://docs.nav2.org/tutorials/docs/navigation2_on_real_turtlebot3.html) — 真实机器人 Nav2 教程
