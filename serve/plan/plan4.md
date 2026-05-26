# Plan4: Service API + Web UI

## 一、目标

将仿真器与控制接口分离：
- `main.py` 启动仿真器（mjviewer）+ Flask API 服务（后台线程）
- `service/server.py` 提供 HTTP API（命令队列架构）
- `service/web.py` 提供 Web UI 发送控制指令
- `tools/arm.py` 机械臂控制函数
- `tools/move.py` 底盘导航函数

## 二、架构

```
┌─────────────────────────────────────┐
│  main.py (主进程)                    │
│  ├─ env = create_scene()            │
│  ├─ env.reset()                     │
│  ├─ start_server(env) → Flask 线程   │
│  └─ mjviewer 渲染循环 (主线程)       │
│      └─ process_commands(env) 每帧   │
└──────────────┬──────────────────────┘
               │ HTTP API (port 5001)
┌──────────────▼──────────────────────┐
│  web.py (浏览器, port 8080)          │
│  ├─ 抓取/释放物体                    │
│  ├─ 末端移动 [x,y,z]                │
│  ├─ 底盘导航 [x, y, yaw]            │
│  └─ Pick & Place 一键操作            │
└─────────────────────────────────────┘
```

**命令队列架构**：Flask 请求线程通过 `submit_command()` 提交命令到队列并阻塞等待；主循环线程调用 `process_commands()` 执行队列中的命令并返回结果。避免多线程同时调用 `env.step()`。

## 三、文件结构

```
serve/
├── main.py                  # 仿真器入口（启动 Flask + mjviewer）
├── tools/
│   ├── arm.py               # 机械臂控制（move_to, grasp, release, pick_and_place）
│   └── move.py              # 底盘导航（get_base_info, move, nav）
├── service/
│   ├── __init__.py
│   ├── server.py            # Flask API 服务（命令队列）
│   └── web.py               # Web UI 控制界面
├── utils/
│   └── utils.py             # 场景创建（create_scene 等）
└── scene/
    ├── make_scene.py
    └── config/
```

## 四、API 设计

### `service/server.py`

| 端点 | 方法 | 说明 |
|------|------|------|
| `/status` | GET | 查询机械臂状态（末端位置、夹爪状态） |
| `/base_status` | GET | 查询底座状态（位置、偏航角） |
| `/objects` | GET | 查询所有物体位置和抓取状态 |
| `/grasp` | POST | 抓取物体 `{obj_name, snap_threshold}` |
| `/release` | POST | 释放物体 |
| `/move_to` | POST | 移动末端 `{target: [x, y, z]}` |
| `/pick_and_place` | POST | 抓取并放置 `{obj_name, target: [x, y, z]}` |
| `/nav` | POST | 底盘导航 `{x, y, w, yaw}` |
| `/open_gripper` | POST | 打开夹爪 |
| `/close_gripper` | POST | 关闭夹爪 |

### 端口

- Flask API: `http://localhost:5001`
- Web UI: `http://localhost:8080`

## 五、线程安全

MuJoCo 是单线程的，Flask 请求不能并发执行仿真步骤。使用**命令队列**模式：

```python
# Flask 请求线程 → 提交命令到队列，阻塞等待结果
result = submit_command("grasp", {"obj_name": "pot"})

# 主循环线程 → 每帧处理队列中的命令
process_commands(env)
```

状态查询（`/status`, `/base_status`, `/objects`）直接读取，不走队列。

## 六、main.py 修改

在现有代码末尾添加 Flask 启动：

```python
# 现有代码保持不变...
env = create_scene(...)
env.reset()

# 新增：启动 Flask API 后台线程
from service.server import start_server, process_commands
start_server(env, port=5001)

# 主循环中每帧处理命令
while True:
    process_commands(env)  # 处理队列中的命令
    env.viewer.update()    # 刷新画面
```

## 七、Web UI 功能

- 物体列表（实时刷新）
- 抓取/释放控制
- 末端移动控制（X, Y, Z）
- 底盘导航控制（X, Y, Yaw）
- Pick & Place 一键操作
- 状态显示（末端位置、底座位置、偏航角）

## 八、验证

1. `conda run -n robocasa python main.py` → mjviewer 打开，Flask 启动在 5001
2. `conda run -n robocasa python service/web.py` → 浏览器打开 http://localhost:8080
3. 点击"抓取 pot" → 仿真器中机器人执行抓取
4. 点击"刷新位置" → 显示末端位置和底座位置
5. 输入底盘导航坐标 → 机器人移动到目标位置
