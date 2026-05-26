# FQPlanner

基于 LLM 的机器人任务规划与执行系统，采用"大脑-小脑"分层架构。

## 架构

```
用户 → Web 控制台 (8888) → Master (5000) → Redis → Slaver (MCP 工具调用) → RoboCasa 仿真 (5001)
```

- **Master** — LLM 任务规划，将自然语言分解为子任务序列
- **Slaver** — 任务执行，通过 MCP 协议调用机器人工具
- **serve** — RoboCasa 仿真后端，提供 Flask API
- **deploy** — Web 控制台，可视化管理界面

通信方式：Master 和 Slaver 通过 Redis Pub/Sub 通信。

## 目录结构

```
FQPlanner/
├── master/                    # Master 节点
│   ├── run.py                 # 启动入口 (端口 5000)
│   ├── config.yaml            # LLM 模型、Redis、日志配置
│   ├── agents/
│   │   ├── agent.py           # GlobalAgent 主控制器
│   │   ├── planner.py         # 任务分解器
│   │   └── prompts.py         # Prompt 模板
│   └── scene/
│       └── profile.yaml       # 场景物体定义
│
├── slaver/                    # Slaver 节点
│   ├── run.py                 # 启动入口
│   ├── config.yaml            # 工具匹配、模型、机器人配置
│   ├── agents/
│   │   ├── slaver_agent.py    # ToolCallingAgent (ReAct)
│   │   └── models.py          # 模型调用封装
│   ├── robot/
│   │   ├── skill.py           # MCP 入口，注册所有工具
│   │   └── module/            # 机器人技能模块
│   │       ├── base.py        # 底盘导航 (navigate_to_target)
│   │       ├── grasp.py       # 抓取 (grasp_object)
│   │       └── place.py       # 放置 (place_on_top, place_object)
│   └── tools/
│       ├── tool_matcher.py    # 语义工具匹配 (sentence-transformers)
│       ├── memory.py          # 场景记忆
│       ├── judge.py           # 失败判断
│       └── monitoring.py      # 日志监控
│
├── serve/                     # RoboCasa 仿真服务
│   ├── main.py                # 启动入口 (端口 5001)
│   ├── sim.py                 # 仿真接口封装 (供 slaver 调用)
│   ├── tools/
│   │   ├── arm.py             # 机械臂控制 (grasp, place, move_arm)
│   │   └── move.py            # 底盘导航 (nav)
│   ├── service/
│   │   ├── server.py          # Flask API (命令队列机制)
│   │   └── web.py             # 内嵌 Web UI
│   └── scene/
│       ├── make_scene.py      # 场景构建器 (MyKitchen)
│       └── config/
│           ├── objects.yaml   # 可操作物体配置
│           └── target.yaml    # 放置目标点配置
│
├── deploy/                    # Web 控制台
│   ├── run.py                 # Flask (端口 8888)
│   └── templates/index.html
│
├── .env                       # CLOUD_API_KEY
└── requirements.txt           # Python 依赖
```

## 启动顺序

```bash
# 1. Redis
redis-server

# 2. RoboCasa 仿真后端
conda activate robocasa
cd serve && python main.py

# 3. Master
conda activate FQPlanner
cd master && python run.py

# 4. Slaver（必须在 Master 之后启动，否则机器人列表为空）
cd slaver && python run.py

# 5. Web 控制台（可选）
cd deploy && python run.py
```

## 关键 API（serve/service/server.py）

| 端点 | 方法 | 参数 | 说明 |
|------|------|------|------|
| `/status` | GET | - | 机械臂状态 |
| `/base_status` | GET | - | 底盘状态 |
| `/objects` | GET | - | 所有物体位置和抓取状态 |
| `/grasp` | POST | `obj_name`, `snap_threshold` | 抓取物体 |
| `/place` | POST | `obj_name`, `target`, `snap_threshold` | 放置物体到坐标 |
| `/nav` | POST | `x`, `y`, `w`, `yaw` | 底盘导航 |
| `/move_to` | POST | `target`, `max_steps`, `pos_threshold` | 移动机械臂 |
| `/open_gripper` | POST | - | 打开夹爪 |
| `/close_gripper` | POST | - | 关闭夹爪 |

## 关键设计

### 命令队列机制（serve/service/server.py）
Flask API 和仿真主循环在不同线程。API 收到请求后放入队列，主循环每帧调用 `process_commands()` 处理，避免多线程同时调用 `env.step()`。

### 物体抓取/放置（serve/tools/arm.py）
- 抓取：末端靠近物体 → `set_joint_qpos` 将物体瞬移到末端 → 关闭夹爪
- 放置：`set_joint_qpos` 将物体瞬移到目标位置 → 打开夹爪
- 使用 `env.sim.data.set_joint_qpos(joint_name, [x,y,z,qw,qx,qy,qz])` 操作物体

### 仿真接口（serve/sim.py）
统一的 HTTP 客户端封装，供 slaver 的技能模块调用。通过 `call_sim(endpoint, data)` 访问仿真 API。

### MCP 工具注册（slaver/robot/skill.py）
技能模块通过 `register_tools(mcp)` 函数注册 MCP 工具。Slaver 启动时加载所有模块，工具列表通过 sentence-transformers 做语义匹配。

## 机器人

PandaOmron：Franka Panda 机械臂 + Omron 移动底盘。
- 12 维动作空间：`[dx,dy,dz, droll,dpitch,dyaw, gripper, base_fwd,base_side,base_yaw, torso, mode]`
- `action[11] < 0` = 臂模式，`action[11] > 0` = 底盘模式

## 当前场景物体

在 `serve/scene/config/objects.yaml` 中配置：
- pot（锅）、cup（杯子）、bowl（碗）、apple（苹果）、mug（马克杯）、sponge（海绵）
- 家具：counter（台面）、island（岛台）、stove（炉灶）、sink（水槽）、cabinet（柜子）

## LLM

使用阿里云 Qwen 模型（`qwen3.6-35b-a3b`），API Key 从 `.env` 读取。Master 和 Slaver 各自独立调用 LLM。

## 两个 Conda 环境

- `FQPlanner` — Master、Slaver、Web 控制台
- `robocasa` — RoboCasa 仿真后端（依赖 MuJoCo、robosuite）
