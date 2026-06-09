# 进度日志

## 会话：2026-06-09

### 阶段 1：需求与边界确认
- **状态：** complete
- 执行的操作：
  - 梳理用户期望的目录职责。
  - 搜索硬编码 URL、MuJoCo、serve_real、绝对路径等耦合点。
  - 确认主要风险来自依赖方向，而不是目录命名。
- 创建/修改的文件：
  - `task_plan.md`
  - `findings.md`
  - `progress.md`

### 阶段 2：统一接口设计
- **状态：** complete
- 执行的操作：
  - 决定新增 `robot_api/` 作为上层唯一机器人接口。
  - 决定保持现有 HTTP endpoint 兼容。
  - 决定将真实硬件触发移入 runtime 编排层。
- 创建/修改的文件：
  - `task_plan.md`
  - `findings.md`

### 阶段 3：上层调用迁移
- **状态：** complete
- 执行的操作：
  - 新增 `robot_api/`，提供统一配置、HTTP client、runtime 编排和 scene memory wrapper。
  - 将 Slaver 工具模块迁移到 `robot_api.client`。
  - 将 `master/agents/planner.py` 的物体坐标查询迁移到 `robot_api.client`。
  - 将 `deploy/run.py` 的后端地址读取迁移到 `robot_api.config`。
  - 将 `nav2` 的 map/object/fixture 查询迁移到 `robot_api.client`。
- 创建/修改的文件：
  - `robot_api/__init__.py`
  - `robot_api/config.py`
  - `robot_api/client.py`
  - `robot_api/runtime.py`
  - `robot_api/scene_memory.py`
  - `slaver/robot/module/*.py`
  - `slaver/robot/waypoint_manager.py`
  - `slaver/agents/slaver_agent.py`
  - `master/agents/planner.py`
  - `deploy/run.py`
  - `nav2/map_generator.py`
  - `nav2/workpoints_generator.py`

### 阶段 4：服务边界清理
- **状态：** complete
- 执行的操作：
  - 早期将 service 客户端改为兼容 shim，后续阶段已删除该入口。
  - 移除 `serve/service/server.py` 对真实底盘桥接的直接依赖。
  - 保留真实抓取/底盘桥接在 `robot_api.runtime` 中统一触发。
- 创建/修改的文件：
  - `serve/service/server.py`
  - 真实机器人 bridge 文档和底盘桥接文件

### 阶段 5：文档与验证
- **状态：** complete
- 执行的操作：
  - 更新 README、Slaver README、Nav2 README 和 `serve_real/config.yaml` 注释。
  - 执行静态编译检查。
  - 执行轻量导入检查。
  - 检查后端离线时 `get_object_pos/is_object_grasped` 的安全返回。
  - 未启动任何服务，未发送真实抓取信号。
- 创建/修改的文件：
  - `README.md`
  - `slaver/README.md`
  - `nav2/README.md`
  - `serve_real/config.yaml`

### 阶段 6：按 1/0 信号路由收紧 robot_api
- **状态：** complete
- 执行的操作：
  - 新增 `robot_api/config.yaml`，默认只开启 MuJoCo。
  - 重写 `robot_api/config.py`，读取 `enabled/provide_state/accept_action/required`。
  - 重写 `robot_api/runtime.py`，状态接口走 `provide_state` 后端，动作接口走 `accept_action` 后端。
  - 删除 `robot_api/scene_memory.py`，`robot_api` 不再暴露语义记忆包装。
  - 修改 `robot_api/client.py`，保留公开能力菜单。
  - 更新 README、Slaver README、`robot_api/contract.md`。
- 创建/修改的文件：
  - `robot_api/config.yaml`
  - `robot_api/config.py`
  - `robot_api/runtime.py`
  - `robot_api/client.py`
  - `robot_api/contract.md`
  - `slaver/robot/waypoint_manager.py`
  - `README.md`
  - `slaver/README.md`

### 阶段 7：语义接口重构
- **状态：** complete
- 执行的操作：
  - 重写 `robot_api/client.py`，公开接口只保留语义能力。
  - 重写 `robot_api/runtime.py`，内部翻译到 MuJoCo HTTP endpoint 和真实后端。
  - 更新 Slaver 底盘/相机/放置模块，改用语义接口。
  - 收紧旧 service 客户端兼容层，后续阶段已删除。
  - 将 `robot_api/config.yaml` 的 `launch_hint` 改为相对路径 `serve/main.py`。
  - 将真实抓取脚本配置改为相对项目根目录解析：`../../camera_10s.sh`。
  - 更新 `robot_api/contract.md`，明确公开语义接口。
  - 执行静态检查与配置读取检查。
- 创建/修改的文件：
  - `robot_api/client.py`
  - `robot_api/runtime.py`
  - `robot_api/__init__.py`
  - `robot_api/config.yaml`
  - `robot_api/contract.md`
  - `slaver/robot/module/base.py`
  - `slaver/robot/module/camera.py`
  - `slaver/robot/module/place.py`
  - 真实抓取服务文件
  - README/usage/CLAUDE/slaver/nav2 文档

### 阶段 8：MuJoCo 后端目录整理
- **状态：** complete
- 执行的操作：
  - 新增 `serve/backend/`。
  - 将 MuJoCo runtime 移到 `serve/backend/mujoco_backend.py`。
  - 修改 `serve/main.py` 导入新 backend 路径。
  - 删除旧的 service 客户端入口，`serve/service/` 只保留 HTTP 服务端。
  - 更新 README、service README、`robot_api/contract.md`、CLAUDE 和计划记录。
- 创建/修改的文件：
  - `serve/backend/__init__.py`
  - `serve/backend/mujoco_backend.py`
  - `serve/main.py`
  - `serve/README.md`
  - `serve/service/README.md`
  - `robot_api/contract.md`
  - `README.md`
  - `CLAUDE.md`
  - `task_plan.md`
  - `findings.md`

### 阶段 9：真实后端目录整理
- **状态：** complete
- 执行的操作：
  - 新增 `serve_real/bridge/`，放真实机械臂和底盘 bridge。
  - 新增 `serve_real/service/`，放开发板侧抓取 socket 服务。
  - 新增 `serve_real/backend/`，放真实底盘驱动和测试脚本。
  - 将 `robot_api.runtime` 的真实后端调用改为 `serve_real.bridge.arm/base`。
  - 将真实硬件 IP、端口、串口等细节保留在 `serve_real/config.yaml`，`robot_api/config.yaml` 只保留 1/0 路由。
  - 更新 README、`serve_real/README.md`、`robot_api/contract.md` 和发现记录。
  - 移出旧源码目录残留的 Python 缓存目录。
- 创建/修改的文件：
  - `serve_real/README.md`
  - `serve_real/__init__.py`
  - `serve_real/bridge/__init__.py`
  - `serve_real/bridge/arm.py`
  - `serve_real/bridge/base.py`
  - `serve_real/service/__init__.py`
  - `serve_real/service/grasp_server.py`
  - `serve_real/backend/__init__.py`
  - `serve_real/backend/base/__init__.py`
  - `serve_real/backend/base/`
  - `robot_api/runtime.py`
  - `robot_api/config.yaml`
  - `README.md`
  - `robot_api/contract.md`
  - `task_plan.md`
  - `progress.md`

## 测试结果
| 测试 | 输入 | 预期结果 | 实际结果 | 状态 |
|------|------|---------|---------|------|
| 静态编译 | 主要 Python 文件 | 无语法错误 | 通过 | pass |
| 导入检查 | `robot_api.client` | 可导入且不加载实机桥接警告 | 通过 | pass |
| 离线安全返回 | `get_object_pos('mug')` / `is_object_grasped('mug')` | `None` / `False` | `None` / `False` | pass |
| 配置读取 | `conda run -n robocasa python ... load_robot_api_config()` | 读到 mujoco/isaacsim/gazebo/real | 通过 | pass |
| 语义签名检查 | `inspect.signature(grasp_object)` | 只显示 `object_name` | 通过 | pass |
| 相对路径检查 | `robot_api/config.yaml` | `launch_hint: serve/main.py` | 通过 | pass |
| 静态编译 | `serve/main.py`、`serve/backend/mujoco_backend.py`、`serve/service/server.py`、`robot_api/*.py` | 无语法错误 | 通过 | pass |
| 后端导入 | `from backend.mujoco_backend import MujocoKitchenEnv` | 可导入类 | `MujocoKitchenEnv` | pass |
| 旧路径搜索 | 旧 service client、旧 backend 路径、旧 backend 导入方式 | 无残留引用 | 无结果 | pass |
| 静态编译 | `robot_api/runtime.py`、`serve_real/bridge/*.py`、`serve_real/service/grasp_server.py`、真实底盘脚本 | 无语法错误 | 通过 | pass |
| 配置读取 | `serve_real/config.yaml` | 保留用户设置的开发板 IP | `10.11.32.17` | pass |
| bridge 导入 | `serve_real.bridge.arm/base` | 可导入且不连接硬件 | 通过 | pass |
| 真实后端目录检查 | `find serve_real -maxdepth 4 -type d` | 只保留 bridge/service/backend 等有意义目录 | 通过 | pass |
| 路径检查 | 旧真实后端入口和项目绝对路径搜索 | 无旧入口；无项目绝对路径 | 通过 | pass |

### 阶段 10：ROS2 SLAM/Nav2 bridge
- **状态：** complete
- 执行的操作：
  - 在 MuJoCo Flask 后端新增 `GET /scan`，基于占据栅格和底座位姿生成 2D LaserScan 数据。
  - 新建 ROS2 Python 包 `fqplanner_nav_bridge` 到 `ros2_ws/src/`。
  - 新增 `mujoco_bridge.py`：发布 `/scan`、`/odom`、`/tf`，订阅 `/cmd_vel` 并转发到 MuJoCo `/cmd_vel`。
  - 新增 `nav2_goal_bridge.py`：HTTP `/nav` 转 Nav2 `NavigateToPose` action，其它请求代理回 MuJoCo 后端。
  - 新增 `mujoco_slam.launch.py` 和 `mujoco_navigation.launch.py`。
  - 新增 Nav2 参数文件并更新 nav2/README、robot_api contract、serve service README。
- 创建/修改的文件：
  - `serve/service/server.py`
  - `nav2/README.md`
  - `robot_api/contract.md`
  - `serve/service/README.md`
  - `/home/fangqi/WorkXCJ/ros2_ws/src/fqplanner_nav_bridge/`

## ROS2 bridge 验证
| 测试 | 输入 | 预期结果 | 实际结果 | 状态 |
|------|------|---------|---------|------|
| Flask 后端静态编译 | `python3 -m py_compile serve/service/server.py` | 无语法错误 | 通过 | pass |
| ROS2 bridge 静态编译 | `/tmp/fqplanner_nav_bridge/*.py` | 无语法错误 | 通过 | pass |
| 复制一致性 | `diff -qr /tmp/fqplanner_nav_bridge ros2_ws/src/fqplanner_nav_bridge` | 无差异 | 通过 | pass |
| ROS2 包结构 | `find ros2_ws/src/fqplanner_nav_bridge -maxdepth 3 -type f` | package/launch/config/node 文件齐全 | 通过 | pass |

## 错误日志
| 时间戳 | 错误 | 尝试次数 | 解决方案 |
|--------|------|---------|---------|
| - | 无 | 0 | - |

## 五问重启检查
| 问题 | 答案 |
|------|------|
| 我在哪里？ | 已完成 |
| 我要去哪里？ | 等待用户确认下一步是否继续补 Isaac/Gazebo adapter 或真实服务停止协议 |
| 目标是什么？ | 让上层通过统一 `robot_api` 复用接口，方便 sim2real/sim2sim |
| 我学到了什么？ | 见 `findings.md` |
| 我做了什么？ | 已完成计划与发现记录 |

---
*每个阶段完成后或遇到错误时更新此文件*
