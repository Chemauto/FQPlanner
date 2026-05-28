# Nav2 导航集成

将 ROS2 Nav2 导航栈接入 FQPlanner RoboCasa 仿真，替代原有 PD 控制器。

## 架构

```
FQPlanner (主机)
  slaver → sim.py → Flask API (5001) ──→ MuJoCo 仿真
                      ↑ cmd_vel    ↓ /base_status
Docker 容器 (nav2)
  bridge_node.py ←── ROS2 Nav2 栈
    ├── /odom + /tf (发布)
    ├── /cmd_vel (订阅 → 转发 Flask)
    └── /navigate (HTTP 端口 5002)
```

## 文件说明

| 文件 | 作用 |
|------|------|
| `Dockerfile` | ROS2 Humble + Nav2 镜像 |
| `docker/build.sh` | 构建 Docker 镜像 |
| `docker/run.sh` | 启动容器（前台，Ctrl+C 退出） |
| `launch.sh` | 容器内启动脚本 |
| `bridge_node.py` | MuJoCo ↔ ROS2 桥接节点 |
| `pandaomron.urdf` | Omron 底盘 URDF（tf 树用） |
| `nav2_params.yaml` | Nav2 参数（DWB controller） |
| `map_generator.py` | 从 layout.yaml 生成占据地图 |
| `maps/` | 生成的地图文件 |

## 使用步骤

### 1. 生成地图

```bash
conda activate robocasa
cd FQPlanner
python nav2/map_generator.py --layout serve/scene/config/layout.yaml --output-dir nav2/maps
```

### 2. 构建 Docker 镜像

```bash
bash nav2/docker/build.sh
```

### 3. 启动系统

```bash
# Terminal 1: Redis
redis-server

# Terminal 2: 仿真（原有）
conda activate robocasa
cd serve && python main.py

# Terminal 3: Nav2 + Bridge（新增）
bash nav2/docker/run.sh

# Terminal 4: Master（原有）
conda activate FQPlanner
cd master && python run.py

# Terminal 5: Slaver（原有）
conda activate FQPlanner
cd slaver && python run.py
```

### 4. 测试

```bash
# 检查桥接节点
curl http://localhost:5002/navigate -X GET

# 手动控制底盘
curl -X POST http://localhost:5001/cmd_vel \
  -H "Content-Type: application/json" \
  -d '{"vx": 0.3, "vy": 0, "vw": 0}'

# Nav2 导航（通过 MCP 工具）
# navigate_to_target(target="counter")
```

## Nav2 未启动时的行为

`/nav` 端点会自动检测 Nav2 桥接节点是否在线：
- **在线**: 走 Nav2 路径规划 + 局部控制
- **离线**: fallback 到原有 PD 控制器

无需修改任何启动脚本，Nav2 是可选增强。
