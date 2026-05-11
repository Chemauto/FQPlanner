# Slaver - 任务执行节点

"小脑"模块，负责连接机器人、接收子任务、匹配工具并执行，将结果回传给 Master。

## 目录结构

```
slaver/
├── run.py              # 启动入口
├── config.yaml         # 配置文件
├── agents/
│   ├── slaver_agent.py # ToolCallingAgent - 工具调用执行
│   └── models.py       # LLM 模型客户端
├── tools/
│   ├── tool_matcher.py # 工具匹配器
│   ├── utils.py        # 配置加载等工具函数
│   ├── memory.py       # 机器人状态记忆
│   ├── monitoring.py   # 执行监控
│   └── state_decorator.py # 状态装饰器
└── robot/
    ├── skill.py        # MCP 工具入口
    └── module/         # 机器人功能模块
```

## 启动

```bash
python slaver/run.py
```

## 配置

编辑 `config.yaml`，主要配置项：

- **model** — LLM 模型配置（同 Master）
- **collaborator** — Redis 连接信息（需与 Master 一致）
- **robot.call_type** — `local`（本地）或 `remote`（远程 HTTP）
- **robot.path** — 本地目录名或远程 URL
- **robot.name** — 机器人名称

## 工作流程

1. 启动后通过 MCP 连接机器人，获取可用工具列表
2. 向 Master 注册机器人信息
3. 监听 Master 分发的子任务
4. 用语义匹配选择相关工具，调用 LLM 执行任务
5. 将执行结果回传给 Master
