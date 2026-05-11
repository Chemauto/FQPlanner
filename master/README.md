# Master - 任务规划节点

"大脑"模块，负责接收任务、分解子任务、分发给机器人并收集结果。

## 目录结构

```
master/
├── run.py              # 启动入口（Flask 服务，端口 5000）
├── config.yaml         # 配置文件
├── agents/
│   ├── agent.py        # GlobalAgent - 任务编排与调度
│   ├── planner.py      # GlobalTaskPlanner - LLM 任务分解
│   └── prompts.py      # Prompt 模板
└── scene/
    ├── profile.yaml    # 场景位置坐标定义
    └── LOCATION_MAP.py # 中英文位置名称映射
```

## 启动

```bash
python master/run.py
```

## 配置

编辑 `config.yaml`，主要配置项：

- **model_select** — 选择 LLM 模型（如 qwen-plus）
- **collaborator** — Redis 连接信息（host、port、password、db）
- **profile** — 场景配置文件路径

## API

| 接口 | 方法 | 说明 |
|------|------|------|
| `/publish_task` | POST | 发布任务，body: `{"task": "前往卧室"}` |
| `/robot_status` | GET | 查询已注册机器人状态 |
| `/system_status` | GET | 查询系统 CPU/内存状态 |
