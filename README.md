# FQPlanner_Mujoco3DGS

> LLM 驱动的具身智能任务规划系统 —— 从自然语言指令到 MuJoCo 仿真中的机器人闭环执行，支持 3D Gaussian Splatting 场景渲染。

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/MuJoCo-Physics-orange?logo=mujoco&logoColor=white" alt="MuJoCo" />
  <img src="https://img.shields.io/badge/License-Apache_2.0-green?logo=apache&logoColor=white" alt="License" />
  <img src="https://img.shields.io/badge/3DGS-Scene_Rendering-purple" alt="3DGS" />
</p>

本项目基于 [FlagScale](https://github.com/FlagOpen/FlagScale) 和 [RoboOS](https://github.com/FlagOpen/RoboOS) 的智能体与具身系统架构，结合 [RoboCasa](https://github.com/robocasa/robocasa)、MuJoCo 和 XLeRobot，将 FQPlanner 的 Master / Slaver / Web 控制链路迁移到本地仿真与可选实机桥接环境中。

---

## ✨ Features

- 🧠 **LLM 任务规划** — 从自然语言到 MCP 工具调用的闭环执行
- 🤖 **XLeRobot 仿真** — 双臂移动机器人在 RoboCasa 风格厨房场景中的 MuJoCo 仿真
- 🏠 **3DGS 场景** — 基于 3D Gaussian Splatting 的真实感场景渲染与导航
- 🫳 **操作能力** — IK 与 ACT 策略抓取、放置等基础机器人操作接口
- 🗺️ **导航规划** — Nav2 风格的 2D 占据地图生成与路径规划
- 🌐 **Web 控制台** — 浏览器端的任务下发与状态监控
- 🔌 **实机桥接** — 仿真验证后向真实开发板发送动作信号

---

## 📁 Repository

```text
FQPlanner_Mujoco3DGS/
├── 🤖 agent/                   # Agent 协作框架
├── 📦 assets/                   # 机器人与场景资源
│   ├── xlerobot/                #   XLeRobot MJCF 与 mesh
│   └── scene_3dgs/              #   3DGS 导航场景（地图生成）
├── 🖥️ deploy/                   # Web 控制台
├── 🐳 docker/                   # Docker 部署
├── 🧠 master/                   # LLM 任务规划服务
├── 🗺️ nav2/                     # 导航地图生成与路径规划
├── 🤖 robot_api/                # 统一机器人接口层
├── 🔮 services/                 # ACT 策略推理服务（独立进程）
├── 🎮 serve/                    # MuJoCo HTTP 后端（厨房场景）
├── 🎨 serve_3dgs/               # 3DGS 场景渲染后端
├── 🔧 serve_real/               # 真实机器人桥接服务
├── 🛠️ slaver/                   # MCP 工具执行服务
├── requirements.txt
└── README.md
```

---

## ⚙️ Requirements

| 环境 | 用途 | 说明 |
|------|------|------|
| `robocasa` | MuJoCo 仿真 | 运行 MuJoCo 后端、场景生成 |
| `FQPlanner` | 规划链路 | 运行 Master、Slaver、Web、MCP 工具 |

```bash
pip install -r requirements.txt   # ⚠️ 敏感信息请放入 .env，不要提交
```

---

## 🚀 Quick Start

### 1️⃣ 安装 Git LFS

首次克隆后必须执行，否则大文件会损坏：

```bash
git lfs install
```

### 2️⃣ 启动 Redis

```bash
redis-server
```

### 3️⃣ 启动 MuJoCo 仿真后端

```bash
conda activate robocasa
cd serve  or cd serve_3dgs
python main.py                  # 策略服务地址自动读取 robot_api/config.yaml
```

> 💡 使用 ACT 抓取时，在 `robot_api/config.yaml` 中启用 `policy_services.act`，并启动推理服务。

### 4️⃣ 启动规划链路

```bash
conda activate FQPlanner
python master/run.py       # 🧠 任务规划
python slaver/run.py       # 🛠️ 工具执行
python deploy/run.py       # 🖥️ Web 控制台
```

### 5️⃣ 验证服务

```text
📍 Robot API:   http://127.0.0.1:5001
📍 Web UI:      http://127.0.0.1:8888
```

```bash
curl http://127.0.0.1:5001/status
curl http://127.0.0.1:5001/objects
curl http://127.0.0.1:5001/scene
```

---

## 🤖 3DGS Scene

基于 3D Gaussian Splatting 的真实感场景，支持碰撞体驱动的导航地图生成。

<details>
<summary>📁 场景结构</summary>

```text
assets/scene_3dgs/
├── config.json              # 场景入口配置
├── config.yaml              # 地图生成参数
├── map_generator.py         # 碰撞 → 占据地图脚本
└── nav_scene_1/
    ├── 3dgs/point_cloud.ply # 3DGS 高斯点云 (~94万点)
    ├── meshes/              # 场景 mesh + V-HACD 碰撞分解
    └── mjcf/scene.xml       # MuJoCo 场景定义
```

</details>

生成导航地图：

```bash
python assets/scene_3dgs/map_generator.py
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `map.resolution` | 0.05 m/px | 栅格分辨率 |
| `map.z_min` | 0.0 m | 碰撞高度下限 |
| `map.z_max` | 2.0 m | 碰撞高度上限 |
| `map.inflate_radius` | 0.05 m | 障碍物膨胀半径 |

详细说明见 [`assets/scene_3dgs/README.md`](assets/scene_3dgs/README.md)。

---

## 🔌 Real Robot Bridge

动作是否传递给真实机器人由 [`robot_api/config.yaml`](robot_api/config.yaml) 控制：

```yaml
backends:
  real:
    enabled: 1
    accept_action: 1
    required: 1
```

真实硬件参数放在 [`serve_real/config.yaml`](serve_real/config.yaml)。开发板侧：

```bash
python3 serve_real/service/grasp_server.py
```

> 💡 修改配置后需重启 Slaver 使配置生效。

---

## 🛡️ Safety

- 🔴 纯仿真测试时保持 `real.enabled: 0` 或 `real.accept_action: 0`
- 🟡 实机运行前确认工作空间安全，准备独立急停
- ⚠️ 停止 `grasp_server.py` 只阻止新指令，已下发动作取决于硬件控制器
- 📜 `camera_10s.sh` 是当前实机动作边界，失败时应返回非零退出码

---

## 📚 Documentation

| 文档 | 说明 |
|------|------|
| [`usage.md`](usage.md) | 启动流程与 API 示例 |
| [`CLAUDE.md`](CLAUDE.md) | 迁移状态与开发注意事项 |
| [`serve_real/README.md`](serve_real/README.md) | 真实机器人桥接说明 |
| [`robot_api/contract.md`](robot_api/contract.md) | 统一机器人接口契约 |
| [`assets/scene_3dgs/README.md`](assets/scene_3dgs/README.md) | 3DGS 场景与地图生成 |
| [`serve_3dgs/README.md`](serve_3dgs/README.md) | 3DGS 渲染后端说明 |

---

## 📎 References

| 项目 | 说明 |
|------|------|
| [FlagScale](https://github.com/FlagOpen/FlagScale) | 智能体系统框架 |
| [RoboOS](https://github.com/FlagOpen/RoboOS) | 具身操作系统 |
| [RoboCasa](https://github.com/robocasa/robocasa) | 机器人仿真平台 |
| [MuJoCo](https://mujoco.org/) | 物理仿真引擎 |
| [Model Context Protocol](https://modelcontextprotocol.io/) | LLM 工具调用协议 |
| [Hunyuan3D](https://github.com/Tencent/Hunyuan3D-1) | 3D 物体生成 |

---

## 📄 License

This project is released under the [Apache License 2.0](LICENSE).
