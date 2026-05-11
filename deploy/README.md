# Deploy - 任务控制台

Web 管理界面，用于任务发布、配置管理和系统运维。

## 启动

```bash
python deploy/run.py
```

访问 http://127.0.0.1:8888

## 功能

| 功能 | 说明 |
|------|------|
| 任务发布 | 输入自然语言任务，转发给 Master 执行 |
| 配置编辑 | 在线加载、编辑、保存 YAML 配置文件 |
| 配置校验 | 校验 Redis 连接、MCP 可达性 |
| 服务启停 | 一键启动 Master/Slaver 服务 |
| 工具查看 | 查看已注册机器人及状态 |

## 文件

```
deploy/
├── run.py              # Flask 后端（API + 服务）
└── templates/
    └── index.html      # 前端页面
```
