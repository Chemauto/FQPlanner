# Deploy - 任务控制台

Web 管理界面，用于任务发布、配置管理、场景查看和视频录制。

## 启动

```bash
conda activate FQPlanner
cd /home/fangqi/WorkXCJ/FQPlanner
python deploy/run.py
```

访问 http://127.0.0.1:8888

## 功能

| 功能 | 说明 |
|------|------|
| 任务发布 | 输入自然语言任务，转发给 Master 执行 |
| 仿真画面 | 点击"刷新画面"查看仿真状态 |
| 视频录制 | 1Hz 录制任务执行过程，自动保存为 MP4 |
| 场景状态 | 查看当前场景中的物体和位置 |
| 配置校验 | 校验 Redis 连接、MCP 可达性 |
| 工具查看 | 查看已注册机器人及工具列表 |

## API 代理

Web 控制台作为代理，转发请求到后端服务：

| 本地端点 | 转发到 | 说明 |
|----------|--------|------|
| `/publish_task` | Master:5000 | 任务发布 |
| `/api/task_status` | Master:5000 | 任务状态 |
| `/api/record/start` | 仿真后端:5001 | 开始录制 |
| `/api/record/stop` | 仿真后端:5001 | 停止录制 |
| `/api/sim/step_and_capture` | 仿真后端:5001 | 步进+截图 |
| `/api/auto_tools` | Redis | 工具列表 |
| `/api/scene_state` | Redis | 场景状态 |

## 文件

```
deploy/
├── run.py              # Flask 后端（API + 服务代理）
└── templates/
    └── index.html      # 前端页面
```

## 依赖服务

| 服务 | 端口 | 说明 |
|------|------|------|
| Redis | 6379 | 场景状态存储 |
| Master | 5000 | 任务规划 |
| RoboCasa | 5001 | 仿真后端（可选） |

## 注意事项

- 录制功能需要 RoboCasa 仿真服务器运行
- 刷新画面会推进仿真一步，可能影响正在进行的任务
