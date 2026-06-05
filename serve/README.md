# serve/ — 仿真后端

MuJoCo 仿真后端，提供 HTTP API 给 slaver 调用。

## 目录结构

```
serve/
├── main.py               # 启动入口：创建场景 + 启动 API + 主循环
├── mujoco_backend.py     # MuJoCo 运行时环境（MujocoKitchenEnv）
├── scene/                # 场景生成和状态管理
├── tools/                # 机器人控制工具（底盘、机械臂）
└── service/              # HTTP API 服务端 + 客户端
```

## 启动

```bash
conda activate robocasa
cd serve
python main.py              # 带 MuJoCo viewer
python main.py --no-viewer  # 无 viewer 模式
```

## 调用链路

```
slaver → service/client.py → HTTP → service/server.py → tools/ → mujoco_backend.py
```

- `client.py` 是 HTTP 客户端，slaver 通过它调 serve 的 API
- `server.py` 是 Flask 服务端，接收请求后调 tools 和 env
- `mujoco_backend.py` 是 MuJoCo 运行时，直接操作仿真模型

## sim2real 迁移

只需替换 `mujoco_backend.py`，实现同名的 `MujocoKitchenEnv` 类方法。
`client.py`、`server.py`、slaver 不需要改。

## 文件说明

### main.py
启动入口。创建 `MujocoKitchenEnv`，启动 Flask API（端口 5001），
进入主循环（处理命令队列 + `mj_step`）。可选打开 MuJoCo viewer。

相机渲染由 `scene/config/camera.yaml` 控制，按请求渲染，不启动后台线程。
可通过 `GET /camera/latest` 读取四相机拼图，通过
`GET /camera/latest?camera=right_arm_cam` 读取单路相机，通过
`GET /camera/status` 查看状态。

### mujoco_backend.py
MuJoCo 运行时环境。`MujocoKitchenEnv` 类封装模型加载、仿真步进、
物体/底盘控制。是整个 serve 的仿真核心。
