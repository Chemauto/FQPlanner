# FQPlanner 项目运行流程

## 项目概述

FQPlanner 是一个 Master-Slaver 架构的机器人协作系统。Master 负责任务规划和分发，Slaver 负责具体执行。两者通过 Redis pub/sub 通信。

## 目录结构

```
FQPlanner/
├── agent/                    # 共享基础设施
│   ├── collaboration/
│   │   └── collaborator.py   # Redis 通信封装（send/listen/环境状态）
│   └── tool_match/
│       ├── tool_matcher.py   # 语义工具匹配（sentence-transformers / TF-IDF）
│       └── tool_registry.py  # 工具注册表
│
├── master/                   # "大脑" - 任务规划节点
│   ├── run.py                # 启动入口（Flask, 端口 5000）
│   ├── config.yaml           # 配置（模型、Redis、场景路径）
│   ├── agents/
│   │   ├── agent.py          # GlobalAgent - 任务编排、对话历史、结果处理
│   │   ├── planner.py        # GlobalTaskPlanner - LLM 任务分解
│   │   └── prompts.py        # Prompt 模板（MASTER_PLANNING_PLANNING）
│   └── scene/
│       └── profile.yaml      # 场景定义（位置、物体、坐标）
│
├── slaver/                   # "小脑" - 执行节点
│   ├── run.py                # 启动入口，Redis 监听，任务分发
│   ├── config.yaml           # 配置（模型、Redis、机器人名称）
│   ├── agents/
│   │   ├── slaver_agent.py   # ToolCallingAgent - ReAct 循环、工具执行
│   │   └── models.py         # ChatMessage 模型定义
│   ├── robot/
│   │   ├── skill.py          # MCP 服务器入口，注册所有工具模块
│   │   ├── skill_remote.py   # 远程 MCP 服务器
│   │   └── module/
│   │       ├── base.py       # navigate_to_target 工具
│   │       ├── grasp.py      # grasp_object 工具（模拟抓取）
│   │       ├── swap.py       # clean_area 工具（模拟打扫）
│   │       └── example.py    # 示例工具
│   └── tools/
│       ├── memory.py         # SceneMemory - 场景状态管理（add/remove/move）
│       ├── judge.py          # 失败判定（retry/skip/terminate）
│       ├── tool_matcher.py   # 工具匹配
│       ├── monitoring.py     # 日志
│       └── state_decorator.py
│
└── deploy/                   # Web 控制台
    ├── run.py                # Flask 应用（端口 8888）
    └── templates/
        └── index.html        # 前端页面
```

## 通信架构

```
用户 ──HTTP──> deploy:8888 ──HTTP──> master:5000
                                        │
                                        ▼
                                   Redis pub/sub
                                   channel: fqplanner_to_FQrobot
                                        │
                                        ▼
                                   slaver (监听)
                                        │
                                        ▼
                                   MCP 工具执行
                                        │
                                        ▼
                                   Redis pub/sub
                                   channel: FQrobot_to_FQPlanner
                                        │
                                        ▼
                                   master 收到结果
```

## 启动顺序

```bash
# 1. 启动 Redis
redis-server

# 2. 启动 Master
cd master && python run.py

# 3. 启动 Slaver
cd slaver && python run.py

# 4. 启动 Web 控制台（可选）
cd deploy && python run.py
```

---

## 运行流程详解

### 阶段一：初始化

#### Master 启动
1. 加载 `config.yaml`，连接 Redis
2. 读取 `scene/profile.yaml`，将场景写入 Redis `ENVIRONMENT_INFO` hash
3. 启动 Flask 服务（端口 5000）
4. 监听 `AGENT_REGISTRATION` 频道，等待 Slaver 注册

#### Slaver 启动
1. 加载 `config.yaml`，连接 Redis
2. 启动 MCP 服务器（`skill.py`），注册工具（navigate_to_target, grasp_object, clean_area）
3. 向 Redis 发送注册消息，Master 收到后记录机器人信息
4. 启动心跳（每 30 秒）
5. 监听 `fqplanner_to_FQrobot` 频道，等待任务

---

### 阶段二：任务规划（Master）

用户通过 Web 控制台或 API 发送任务，Master 的 `GlobalTaskPlanner` 调用 LLM 分解任务。

**LLM 收到的信息：**
- 可用机器人列表：`["FQrobot"]`
- 机器人工具能力：`navigate_to_target, grasp_object, clean_area`
- 场景信息：各位置的 contains、coordinates
- 用户任务

**LLM 输出格式：**
```json
{
    "reasoning_explanation": "分析任务...",
    "subtask_list": [
        {"robot_name": "FQrobot", "subtask": "导航到厨房桌子", "subtask_order": 1},
        {"robot_name": "FQrobot", "subtask": "抓取苹果", "subtask_order": 2}
    ]
}
```

Master 按 `subtask_order` 分组，同组并行、不同组串行执行。

---

### 阶段三：任务执行（Slaver）

Slaver 收到任务后，进入 ReAct 循环：

```
while step_number <= max_steps:
    1. LLM 决定调用哪个工具
    2. 执行工具
    3. 检查结果是否失败
    4. 如果失败 → 调用 judge 决策（retry/skip/terminate）
    5. 如果成功 → 更新场景状态
    6. LLM 判断是否需要继续
```

#### 工具执行流程

```
_execute_tool_call(tool_name, tool_arguments)
    │
    ▼
MCP 调用工具（如 grasp_object）
    │
    ▼
解析返回值（JSON 数组或纯字符串）
    │
    ▼
检查是否失败（包含"失败"或"failed"）
    │
    ├─ 成功 → 更新机器人状态 → 更新场景 → 返回结果
    │
    └─ 失败 → 调用 judge_on_failure()
              │
              ├─ retry（>0.4）→ 重新执行（最多3次）
              ├─ skip（0.1~0.4）→ 返回跳过消息
              └─ terminate（<0.1）→ 抛出异常，终止整个任务
```

---

### 阶段四：场景状态管理

场景状态存储在 Redis `ENVIRONMENT_INFO` hash 中。

**初始化（Master 启动时）：**
```
ENVIRONMENT_INFO:
  kitchenTable → {"type": "table", "position": [1.0, 2.0, 0.0], "description": "厨房桌子", "contains": ["apple", "pear", "banana", "knife"]}
  bedroom      → {"type": "location", "position": [0.0, 0.8, 0.0], "description": "卧室"}
  robot        → {"position": "entrance", "coordinates": [0.0, 0.0, 0.0], "holding": null, "status": "idle"}
```

**执行抓取后（Slaver 自动更新）：**
```
ENVIRONMENT_INFO:
  kitchenTable → {"type": "table", ..., "contains": ["pear", "banana", "knife"]}  # apple 被移除
  robot        → {"position": "kitchenTable", "holding": "apple", ...}             # holding 更新
```

**外部变化（通过 Web 控制台手动更新）：**
```
POST /api/update_scene
{"location": "kitchenTable", "action": "add_object", "object": "orange"}
```

---

## 实际案例

### 案例 1：简单导航 — "前往卧室"

**Master 规划：**
```json
{
    "reasoning_explanation": "单一导航任务，直接分配给 FQrobot",
    "subtask_list": [
        {"robot_name": "FQrobot", "subtask": "前往卧室", "subtask_order": 1}
    ]
}
```

**Slaver 执行：**
```
Step 1: LLM 决定调用 navigate_to_target(target="bedroom")
  → 返回: ["Navigation to bedroom has been successfully performed.", {"position": "bedroom", "coordinates": [0.0, 0.8, 0.0]}]
  → 更新机器人状态: position=bedroom, coordinates=[0.0, 0.8, 0.0]
  → memory_predict: action_type=position → move_to("bedroom")
  → LLM 判断任务完成 → final_answer
```

**最终状态：**
```
robot: {"position": "bedroom", "coordinates": [0.0, 0.8, 0.0]}
```

---

### 案例 2：抓取任务 — "帮我抓取厨房桌子上的水果"

**Master 规划：**
```json
{
    "reasoning_explanation": "需要先导航到厨房桌子，再抓取水果",
    "subtask_list": [
        {"robot_name": "FQrobot", "subtask": "导航到厨房桌子", "subtask_order": 1},
        {"robot_name": "FQrobot", "subtask": "抓取水果", "subtask_order": 2}
    ]
}
```

**Slaver 执行子任务 1（导航）：**
```
Step 1: navigate_to_target(target="kitchenTable")
  → 成功，机器人位置更新为 kitchenTable
```

**Slaver 执行子任务 2（抓取）：**
```
Step 1: grasp_object(object_name="apple")
  → 随机成功/失败（80% 成功率）

  如果成功：
    → memory_predict: remove_object → 从 kitchenTable.contains 移除 apple
    → robot.holding = "apple"

  如果失败：
    → judge 决策：
      - retry（>0.4）→ 重试抓取，最多3次
      - skip（0.1~0.4）→ 跳过，返回"任务跳过"
      - terminate（<0.1）→ 终止整个任务
    → 不更新场景（失败不影响 contains）
```

---

### 案例 3：打扫任务 — "帮我打扫卧室"

**Master 规划：**
```json
{
    "reasoning_explanation": "单一打扫任务，直接分配给 FQrobot",
    "subtask_list": [
        {"robot_name": "FQrobot", "subtask": "帮我打扫卧室", "subtask_order": 1}
    ]
}
```

**Slaver 执行：**
```
Step 1: LLM 决定先导航到卧室
  → navigate_to_target(target="bedroom") → 成功

Step 2: LLM 决定调用 clean_area
  → clean_area(area_name="卧室") → 随机成功/失败（80% 成功率）
  → memory_predict: action_type=position（打扫不改变物体归属）
```

---

### 案例 4：多任务并行 — "打扫卧室，同时抓取厨房桌子上的苹果"

**Master 规划：**
```json
{
    "reasoning_explanation": "两个任务互不依赖，可以并行",
    "subtask_list": [
        {"robot_name": "FQrobot", "subtask": "打扫卧室", "subtask_order": 1},
        {"robot_name": "FQrobot", "subtask": "抓取厨房桌子上的苹果", "subtask_order": 1}
    ]
}
```

注意：`subtask_order` 相同表示并行执行。但当前只有一个机器人，实际是串行的。如果有两个机器人，才会真正并行。

---

## 关键配置项

### master/config.yaml
- `model.model_select` — LLM 模型（如 qwen3.5-plus-2026-02-15）
- `collaborator` — Redis 连接信息
- `profile.path` — 场景配置文件路径
- `profiling` — 是否输出调试信息

### slaver/config.yaml
- `robot.name` — 机器人名称（如 FQrobot）
- `robot.call_type` — "local"（本地 MCP）或 "remote"（远程 HTTP）
- `robot.path` — MCP 服务器路径
- `tool.matching` — 工具匹配配置（max_tools, min_similarity）

---

## 场景配置 (profile.yaml)

```yaml
scene:
  - name: kitchenTable      # 英文名称（唯一标识）
    type: table              # 类型：location / table / container
    position: [1.0, 2.0, 0.0]  # [x, y, z] 坐标
    description: "厨房桌子"  # 中文名称
    contains:                # 该位置包含的物体
      - apple
      - pear
      - banana
      - knife
```

添加新位置：只需在 `profile.yaml` 中添加条目，重启 Master 和 Slaver。

---

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `master:5000/publish_task` | POST | 发布任务 `{"task": "前往卧室"}` |
| `master:5000/robot_status` | GET | 查询机器人状态 |
| `deploy:8888/` | GET | Web 控制台 |
| `deploy:8888/api/scene_state` | GET | 读取当前场景状态 |
| `deploy:8888/api/update_scene` | POST | 手动更新场景 |
| `deploy:8888/api/auto_tools` | GET | 查看已注册工具 |
