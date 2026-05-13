# FQPlanner 项目运行流程

## 项目概述

FQPlanner 是一个 Master-Slaver 架构的机器人协作系统。Master 负责任务规划、增量重规划和经验学习，Slaver 负责具体执行。两者通过 Redis pub/sub 通信，支持场景变化驱动的动态任务调整。

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
│   │   ├── agent.py          # GlobalAgent + TaskQueue - 任务编排、增量规划、经验库
│   │   ├── planner.py        # GlobalTaskPlanner - LLM 任务分解（支持经验注入）
│   │   └── prompts.py        # Prompt 模板（MASTER_PLANNING_PLANNING + 经验占位）
│   ├── scene/
│   │   └── profile.yaml      # 场景定义（位置、物体、坐标）
│   └── memory/
│       └── experiences.md    # 经验库（自动生成，正向经验 + 避免规则）
│
├── slaver/                   # "小脑" - 执行节点
│   ├── run.py                # 启动入口，Redis 监听，任务分发，场景模拟与检测
│   ├── config.yaml           # 配置（模型、Redis、机器人名称）
│   ├── agents/
│   │   ├── slaver_agent.py   # ToolCallingAgent - ReAct 循环、工具执行
│   │   └── models.py         # ChatMessage 模型定义
│   ├── robot/
│   │   ├── skill.py          # MCP 服务器入口，注册所有工具模块
│   │   ├── skill_remote.py   # 远程 MCP 服务器
│   │   └── module/
│   │       ├── base.py       # navigate_to_target / move 工具
│   │       ├── grasp.py      # grasp_object 工具（模拟抓取）
│   │       ├── swap.py       # clean_area 工具（模拟打扫）
│   │       └── example.py    # 示例模板
│   └── tools/
│       ├── memory.py         # SceneMemory - 场景状态管理（add/remove/move）
│       ├── judge.py          # 失败判定（retry/skip/terminate）
│       ├── tool_matcher.py   # 工具匹配
│       ├── monitoring.py     # 日志 + SceneDetector 场景变化检测器
│       ├── SceneChange.py    # 场景变化模拟（部署时注释掉）
│       └── state_decorator.py
│
└── deploy/                   # Web 控制台
    ├── run.py                # Flask 应用（端口 8888）
    └── templates/
        └── index.html        # 前端页面（任务进度、经验卡片、场景管理）
```

## 通信架构

```
用户 ──HTTP──> deploy:8888 ──HTTP──> master:5000
                                        │
                                        ▼
                                   Redis pub/sub
                 ┌────────────────────────────────────────────┐
                 │ AGENT_REGISTRATION  (Slaver→Master 注册)   │
                 │ fqplanner_to_FQrobot (Master→Slaver 任务)  │
                 │ FQrobot_to_FQPlanner (Slaver→Master 结果)  │
                 │ scene_changes        (Slaver→Master 实时)  │
                 └────────────────────────────────────────────┘
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

## 核心流程

### 1. 初始化

**Master 启动：**
1. 加载 `config.yaml`，连接 Redis
2. 读取 `scene/profile.yaml`，将场景写入 Redis `ENVIRONMENT_INFO` hash
3. 启动监听线程：`AGENT_REGISTRATION`（注册）、`scene_changes`（场景变化）
4. 启动 Flask 服务（端口 5000）

**Slaver 启动：**
1. 加载 `config.yaml`，连接 Redis
2. 启动 MCP 服务器（`skill.py`），获取工具列表
3. 向 Redis 注册，Master 收到后建立监听
4. 启动心跳（每 30 秒）
5. 启动 SceneChanger（场景模拟，部署时注释掉）
6. 启动 SceneDetector（场景变化检测 + 实时推送）
7. 监听 `fqplanner_to_{robot_name}` 频道，等待任务

### 2. 任务规划（Master）

```
用户任务 → 加载经验库(experiences.md) → 注入到 prompt
         → GlobalTaskPlanner(LLM 分解) → subtask_list
         → 创建 TaskQueue（可变队列，支持增量增删）
         → 异步线程逐个发送子任务
```

LLM 收到的信息：
- 可用机器人列表 + 工具能力
- 场景信息（各位置 contains、coordinates）
- 过往经验（正向经验 ✓ + 避免规则 ✗）
- 用户任务

### 3. 任务执行（Master → Slaver → Master）

```
Master 逐个子任务:
  1. 从 TaskQueue 取下一个未完成任务
  2. Redis.send("fqplanner_to_FQrobot", subtask)
  3. wait_agents_free()（阻塞等待 Slaver 完成）
  4. mark_done(current)
  5. 检查 pending_scene_changes（来自 scene_changes 频道）
  6. 如果有变化 → _incremental_replan() → LLM 判断增删子任务
  7. 更新 TaskQueue → 继续循环

Slaver 执行子任务:
  1. 收到任务 → ToolMatcher 匹配工具
  2. ReAct 循环：LLM 决策 → 执行工具 → 检查结果
     ├─ 成功 → memory_predict 更新场景 → 继续/结束
     └─ 失败 → judge_on_failure()
              ├─ retry → 重试（最多 3 次）
              ├─ skip → 跳过子任务
              └─ terminate → 终止整个任务
  3. 返回结果 → Redis.send("FQrobot_to_FQPlanner")
```

### 4. 场景变化系统

```
SceneChanger（模拟）    SceneDetector（检测）     Master（决策）
  每2秒随机修改Redis      每2秒对比快照             收到 scene_changes
  kitchenTable contains   发现 added/removed        累积到 pending
    │                       │                        │
    │                       │ 检测到变化后:            │ 每个子任务完成后:
    │                       │ 1.存 self.changes       │ 1.取出累积变化
    │                       │ 2.立即send("scene_      │ 2.读当前场景状态
    │                       │   changes")推给Master   │ 3.调 _incremental_replan
    │                       │ 3.更新 baseline          │   → LLM返回 new/remove
    │                       │                         │ 4.更新 TaskQueue
    ▼                       ▼                         ▼
  部署时注释掉start()    部署时替换为真实传感器      不变
```

### 5. 增量规划（_incremental_replan）

每个子任务完成后，Master 检查是否有累积的场景变化。如果有，LLM 收到：

- 当前场景状态（从 Redis 实时读取）
- 已完成的子任务
- 剩余的子任务
- 场景变化摘要

LLM 返回：
```json
{
    "reasoning": "判断理由",
    "new_subtasks": [{"robot_name": "FQrobot", "subtask": "抓取 Watermelon"}],
    "remove_subtasks": ["Strawberry"]
}
```

Master 先移除、再追加，更新 TaskQueue 继续执行。

### 6. 经验库系统

任务完成后，Web 前端弹出经验卡片：
- **"是"** → 自动提取任务+子任务+结果，存为正向经验到 `master/memory/experiences.md`
- **"否"** → 用户手写避免规则，存为负向经验

经验文件格式（markdown）：
```markdown
# 经验库

## 正向经验

### 2026-05-13 14:30 抓取水果
- 任务：抓起厨房桌子上的水果
- 子任务：导航到厨房桌子 → 逐个抓取 apple、pear、banana
- 教训：每个物体单独一个子任务，导航后再抓取

## 避免规则

### 2026-05-13 15:00 多物体合并
- 任务：抓取餐具
- 规则：不要把多个物体合成一个子任务，工具一次只能抓一个
```

下次规划时，经验自动注入到 LLM prompt：
```
过往经验（请参考以下经验进行规划）：
✓ 教训：每个物体单独一个子任务，导航后再抓取
✗ 规则：不要把多个物体合成一个子任务，工具一次只能抓一个
```

---

## TaskQueue（可变任务队列）

```python
# LLM 返回后转换为内部结构
[
    {"order": 1, "robot_name": "FQrobot", "subtask": "导航到厨房桌子",  "done": False},
    {"order": 2, "robot_name": "FQrobot", "subtask": "抓取 apple",      "done": False},
    {"order": 3, "robot_name": "FQrobot", "subtask": "抓取 pear",       "done": False},
]

# 执行过程中动态变化
# 子任务1完成 → mark_done
# 子任务2完成 → 场景变化 → 增量规划 → append_tasks / remove_pending_tasks
# 循环直到 all_done()
```

---

## 场景配置 (profile.yaml)

```yaml
scene:
  - name: kitchenTable
    type: table
    position: [1.0, 2.0, 0.0]
    description: "厨房桌子"
    contains:
      - apple
      - pear
      - banana
      - knife
```

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

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `master:5000/publish_task` | POST | 发布任务 `{"task": "前往卧室"}` |
| `master:5000/robot_status` | GET | 查询机器人状态 |
| `master:5000/system_status` | GET | 查询系统 CPU/内存 |
| `master:5000/api/task_status` | GET | 查询当前任务执行进度 |
| `master:5000/api/save_experience` | POST | 保存经验 `{"task_id":"xx", "type":"positive/negative", "note":"..."}` |
| `master:5000/api/experiences` | GET | 查看经验库全文 |
| `deploy:8888/` | GET | Web 控制台 |
| `deploy:8888/api/scene_state` | GET | 读取当前场景状态 |
| `deploy:8888/api/update_scene` | POST | 手动更新场景 |
| `deploy:8888/api/auto_tools` | GET | 查看已注册工具 |
