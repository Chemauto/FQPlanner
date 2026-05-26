# FQPlanner

FQPlanner 是基于"大脑-小脑"分层架构的机器人操作系统，通过大语言模型实现任务规划与执行。

**核心功能**
- **任务规划** — LLM 自动分解复杂任务为子任务序列
- **仿真执行** — RoboCasa 物理仿真后端，支持导航、抓取、放置等操作
- **Web 控制台** — 可视化任务发布、场景查看、视频录制
- **MCP 工具调用** — Slaver 通过 MCP 协议调用机器人技能模块

## 快速入门

### 1. 环境要求

- Python 3.10+
- Conda
- Redis
- RoboCasa（仿真后端，依赖 MuJoCo / robosuite）

### 2. 安装

```bash
git clone https://github.com/Chemauto/FQPlanner.git
cd FQPlanner

# 创建 FQPlanner 环境（Master / Slaver / Web 控制台）
conda create -n FQPlanner python=3.10
conda activate FQPlanner
pip install -r requirements.txt

# RoboCasa 环境需单独安装，参考 robocasa 文档
```

### 3. 配置 API Key

新建 `.env` 文件：

```bash
CLOUD_API_KEY=sk-xxxxxxxxxxxxxxx
```

当前使用阿里云 Qwen 模型（`qwen3.6-35b-a3b`），配置在 `master/config.yaml` 和 `slaver/config.yaml` 中。

### 4. 启动系统

按顺序启动，需要 3-4 个终端：

```bash
# 终端 1 — Redis
redis-server

# 终端 2 — RoboCasa 仿真后端（robocasa 环境）
conda activate robocasa
cd serve && python main.py

# 终端 3 — Master（FQPlanner 环境）
conda activate FQPlanner
python master/run.py

# 终端 4 — Slaver（必须在 Master 之后启动）
conda activate FQPlanner
python slaver/run.py

# 终端 5 — Web 控制台（可选）
conda activate FQPlanner
python deploy/run.py
```

### 5. 发布任务

访问 http://127.0.0.1:8888 ，输入自然语言任务：

- "抓取苹果"
- "把杯子放到岛台上"
- "导航到水槽旁边"

## 项目结构

```
FQPlanner/
├── master/                    # Master 节点（任务规划）
│   ├── run.py                 #   启动脚本 (端口 5000)
│   ├── config.yaml            #   LLM、Redis、日志配置
│   ├── agents/                #   规划 Agent、Prompt 模板
│   └── scene/profile.yaml     #   场景物体定义
│
├── slaver/                    # Slaver 节点（任务执行）
│   ├── run.py                 #   启动脚本
│   ├── config.yaml            #   工具匹配、模型、机器人配置
│   ├── agents/                #   执行 Agent (ReAct)
│   ├── robot/
│   │   ├── skill.py           #     MCP 入口，注册所有工具
│   │   └── module/            #     技能模块（base / grasp / place）
│   └── tools/                 #   工具匹配、场景记忆、失败判断
│
├── serve/                     # RoboCasa 仿真服务
│   ├── main.py                #   启动脚本 (端口 5001)
│   ├── sim.py                 #   仿真接口封装
│   ├── tools/arm.py           #   机械臂控制
│   ├── tools/move.py          #   底盘导航
│   ├── service/server.py      #   Flask API
│   └── scene/                 #   场景配置
│
├── deploy/                    # Web 控制台
│   ├── run.py                 #   Flask (端口 8888)
│   └── templates/index.html   #   前端页面
│
├── .env                       # API Key
└── requirements.txt           # Python 依赖
```

## Conda 环境

| 环境 | 用途 | 说明 |
|------|------|------|
| `FQPlanner` | Master、Slaver、Web 控制台 | flask, redis, requests, pyyaml, sentence-transformers |
| `robocasa` | RoboCasa 仿真后端 | robosuite, mujoco, flask |

## 可用工具

| 工具 | 参数 | 说明 |
|------|------|------|
| `navigate_to_target` | `target` | 导航底盘到坐标，如 `"(1.5, -0.5)"` |
| `grasp_object` | `object_name` | 抓取物体 |
| `place_on_top` | `obj_name`, `target_name` | 放到目标物体上方 |
| `place_object` | `obj_name`, `x`, `y`, `z` | 放到指定坐标 |
| `release_object` | 无 | 释放当前抓取的物体 |

## 文档

- [使用指南](usage.md) — 启动步骤和 API 说明
- [CLAUDE.md](CLAUDE.md) — 项目完整技术文档
- [serve/tools/README.md](serve/tools/README.md) — 机械臂和底盘控制

## 致谢

本项目基于 [FlagScale](https://github.com/flagos-ai/FlagScale) 和 [RoboOS](https://github.com/FlagOpen/RoboOS) 进行开发。仿真后端使用 [RoboCasa](https://github.com/ARISE-Initiative/robocasa)。
