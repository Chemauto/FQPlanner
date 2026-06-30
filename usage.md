# FQPlanner_Mujoco 使用指南

## 🚀 启动顺序

```text
1. 🗄️  Redis (6379)
2. 🤖 MuJoCo / XLeRobot 仿真后端 (5001)  ·  🔮 ACT 推理服务 (5003，可选)
3. 🧠 Master (5000)
4. 🛠️ Slaver
5. 🖥️ Web 控制台 (8888，可选)
```

## 1. 🗄️ 启动 Redis

```bash
redis-server
```

## 2. 🤖 启动 MuJoCo 仿真后端

```bash
conda activate robocasa
cd serve
python main.py
```

如果只想启动 API，不打开 MuJoCo viewer：

```bash
python main.py --no-viewer
```

### 🔮 ACT 策略推理服务（可选）

使用 ACT 策略抓取物体时，需额外启动独立推理进程：

```bash
conda activate FQPlanner
python services/act_server.py \
  --policy-path <checkpoint_dir> \
  --port 5003
```

在 `robot_api/config.yaml` 中启用 ACT 服务：

```yaml
policy_services:
  act:
    enabled: 1
    url: "http://127.0.0.1:5003"
```

仿真后端启动时自动读取配置，无需额外参数：

```bash
python main.py
```

> 💡 `--act-url` 可作为临时覆盖：`python main.py --act-url http://192.168.1.100:5003`

验证：

```bash
curl http://127.0.0.1:5001/status
curl http://127.0.0.1:5001/base_status
curl http://127.0.0.1:5001/objects
curl http://127.0.0.1:5001/scene

# 🔮 ACT 服务健康检查
curl http://127.0.0.1:5003/health
curl http://127.0.0.1:5003/info
```

## 3. 🧠 启动 Master

```bash
conda activate FQPlanner
python master/run.py
```

## 4. 🛠️ 启动 Slaver

```bash
conda activate FQPlanner
python slaver/run.py
```

Slaver 的仿真服务地址应指向：

```text
http://127.0.0.1:5001
```

## 5. 🖥️ 启动 Web 控制台

```bash
conda activate FQPlanner
python deploy/run.py
```

访问：

```text
http://127.0.0.1:8888
```

## 6. 🐳 Docker 启动 Nav2 导航

如果需要使用 Nav2 的全局规划、局部控制和 costmap，不要走 MuJoCo 后端自己的简单 `/nav`。
先启动 MuJoCo 后端，再启动 Docker 内的 ROS2/Nav2。

宿主机启动 MuJoCo：

```bash
conda activate robocasa
cd serve
python main.py 
```

构建并进入 Nav2 镜像：

```bash
cd ..
./docker/build.sh 
# 构建镜像
./docker/run.sh
# 构建完成后运行镜像
```

容器内启动 Nav2：

```bash
ros2 launch fqplanner_nav_bridge mujoco_navigation.launch.py \
backend_url:=http://host.docker.internal:5001 \
http_host:=0.0.0.0 \
http_port:=5102 \
launch_rviz:=false
```

上层项目会按 `robot_api/config.yaml` 自动路由：

```bash
python slaver/run.py
```

其中 MuJoCo 主后端是 `http://127.0.0.1:5001`，只有 `navigate_to()` 会单独走 Nav2 bridge `http://127.0.0.1:5102`。
生成地图和工作点时不要设置 `ROBOT_API_URL=5102`。

## 📡 常用 API

| 地址 | 方法 | 说明 |
| --- | --- | --- |
| `/status` | GET | 🦾 机械臂 / 抓取状态 |
| `/base_status` | GET | 🧭 底盘位置和速度 |
| `/objects` | GET | 🧊 当前物体位置 |
| `/fixtures` | GET | 🪑 当前家具 / fixtures |
| `/scene` | GET | 🏠 场景综合信息 |
| `/scene_state` | GET | 📋 逻辑场景状态 |
| `/map_data` | GET | 🗺️ 地图生成数据 |
| `/grasp` | POST | 🫳 抓取物体（支持 `mode: "ik"` / `"act"`） |
| `/place` | POST | 📦 放置物体到坐标 |
| `/move_to` | POST | 🎯 移动虚拟末端 |
| `/nav` | POST | 🧭 底盘导航到坐标 |
| `/cmd_vel` | POST | 🏎️ 底盘速度控制 |
| `/screenshot` | POST | 📸 截图 |
| `/act_step` | POST | 🔮 ACT 单步推理（仅 ACT 服务） |
| `/health` | GET | 💚 ACT 服务健康检查 |

示例：

```bash
# 🧭 导航到目标位置
curl -X POST http://127.0.0.1:5001/nav \
  -H 'Content-Type: application/json' \
  -d '{"x": 3.2, "y": -2.5, "yaw": 0}'

# 🫳 IK 抓取（默认）
curl -X POST http://127.0.0.1:5001/grasp \
  -H 'Content-Type: application/json' \
  -d '{"obj_name": "apple"}'

# 🫳 ACT 策略抓取
curl -X POST http://127.0.0.1:5001/grasp \
  -H 'Content-Type: application/json' \
  -d '{"obj_name": "apple", "mode": "act"}'

# 📦 放置物体
curl -X POST http://127.0.0.1:5001/place \
  -H 'Content-Type: application/json' \
  -d '{"obj_name": "apple", "target": [4.0, -0.5, 1.0]}'

# 🔮 查询 ACT 服务信息
curl http://127.0.0.1:5003/info
```

## 🎨 场景配置

主要配置目录：

```text
serve/scene/config/
```

关键文件：

```text
layout.yaml              # 🏗️ 厨房布局
style.yaml               # 🎨 RoboCasa 风格 / 材质
objects.yaml             # 🧊 可操作物体和 placement
waypoints.yaml           # 📍 工作点 / 导航语义点
scene_state_initial.yaml # 📋 初始逻辑状态
target.yaml              # 🎯 放置目标
```

当前 `objects.yaml`：

- `pot` 放在 counter，靠近 stove 参照区域。
- `cup`、`bowl`、`apple`、`mug` 放在 counter 随机区域。
- `sponge` 放在 island 随机区域。
- 同一 fixture 上随机物体有最小距离避让，避免挤在一起。

## ⚠️ 当前限制

- ⚙️ 当前后端不是 RoboCasa 原生 env；RoboCasa 用于生成真实厨房和物体 XML。
- 🫳 IK 抓取 / 放置是高层测试逻辑，服务端会分步移动虚拟末端和物体用于可视化，不是完整真实接触抓取。
- 🔮 ACT 抓取需在 `robot_api/config.yaml` 中启用 `policy_services.act`，并启动对应推理服务。
- 🛠️ Slaver 默认 `use_realtime_coords: true`，导航会读取 `/objects` 和 `/fixtures` 的实时位置；目标名称不存在时会失败，不再退回第一个工作点。
- 📝 原规划可以继续调用同名工具，但任务成功与否主要取决于物体名称、目标名称、API 参数是否仍然匹配。
