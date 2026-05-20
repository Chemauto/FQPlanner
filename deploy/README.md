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
| 仿真画面 | 点击"刷新画面"查看 OmniGibson 仿真状态 |
| 视频录制 | 1Hz 录制任务执行过程，自动保存为 MP4 |
| 场景状态 | 查看当前场景中的物体和位置 |
| 配置校验 | 校验 Redis 连接、MCP 可达性 |
| 工具查看 | 查看已注册机器人及工具列表 |

## 页面布局

### 任务发布
- 输入自然语言任务（支持中英文）
- 点击"发布任务"发送给 Master
- 查看任务执行状态和结果

### 仿真画面
- 点击"刷新画面"按钮
- 自动推进仿真一步并捕获观察者视角截图
- 显示在页面上供验证任务效果

### 视频录制
- **开始录制**: 启动 1Hz 帧捕获
- **停止录制**: 停止并保存视频文件
- 录制期间每次仿真步进自动捕获一帧

### 场景状态
- 自动刷新显示当前场景信息
- 包含桌子、容器、位置等物体状态
- 显示机器人持有的物体

## API 代理

Web 控制台作为代理，转发请求到后端服务：

| 本地端点 | 转发到 | 说明 |
|----------|--------|------|
| `/publish_task` | Master:5000 | 任务发布 |
| `/api/task_status` | Master:5000 | 任务状态 |
| `/api/record/start` | OmniGibson:5001 | 开始录制 |
| `/api/record/stop` | OmniGibson:5001 | 停止录制 |
| `/api/sim/step_and_capture` | OmniGibson:5001 | 步进+截图 |
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
| OmniGibson | 5001 | 仿真后端（可选） |

## 注意事项

- 录制功能需要 OmniGibson 服务器运行
- 录制文件保存在 `/home/fangqi/WorkXCJ/BEHAVIOR-1K/My_code/recordings/`
- 刷新画面会推进仿真一步，可能影响正在进行的任务
