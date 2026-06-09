# serve/ — MuJoCo 后端

`serve/` 是当前 MuJoCo 仿真后端。上层规划、工具、网页和导航代码不直接依赖这里，而是统一通过 `robot_api.client` 调用。

## 目录结构

```
serve/
├── main.py               # 启动入口：创建场景 + 启动 API + 主循环
├── backend/
│   └── mujoco_backend.py # MuJoCo 运行时环境（MujocoKitchenEnv）
├── scene/                # MuJoCo/RoboCasa 场景生成和状态管理
├── tools/                # MuJoCo 动作实现（底盘、机械臂）
└── service/
    └── server.py         # HTTP API 服务端
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
master/slaver/deploy/nav2
  -> robot_api.client
  -> robot_api.runtime
  -> HTTP
  -> serve/service/server.py
  -> serve/tools/
  -> serve/backend/mujoco_backend.py
```

- `robot_api` 是上层唯一机器人接口。
- `service/server.py` 是 MuJoCo HTTP 服务端，负责实现 `robot_api` 的后端契约。
- `tools/` 是 MuJoCo 的动作实现，不是上层通用工具接口。
- `backend/mujoco_backend.py` 是 MuJoCo 运行时，直接操作模型和仿真数据。

## sim2real 迁移

真实机器人放在 `serve_real/`，由 `robot_api.runtime` 按配置触发。`serve/` 不直接 import `serve_real`。

## sim2sim 迁移

Isaac Sim、Gazebo 等后端应在同层目录实现自己的服务，例如 `serve_isaac/` 或 `serve_gazebo/`，并提供与 [`robot_api/contract.md`](../robot_api/contract.md) 对齐的 HTTP endpoint。上层仍然只调用 `robot_api.client`。

## 文件说明

### main.py
启动入口。创建 `MujocoKitchenEnv`，启动 Flask API（端口 5001），
进入主循环（处理命令队列 + `mj_step`）。可选打开 MuJoCo viewer。

相机渲染由 `scene/config/camera.yaml` 控制，按请求渲染，不启动后台线程。
可通过 `GET /camera/latest` 读取四相机拼图，通过
`GET /camera/latest?camera=right_arm_cam` 读取单路相机，通过
`GET /camera/status` 查看状态。

### backend/mujoco_backend.py
MuJoCo 运行时环境。`MujocoKitchenEnv` 类封装模型加载、仿真步进、
物体/底盘控制。是整个 serve 的仿真核心。
