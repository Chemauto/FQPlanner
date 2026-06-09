# 任务计划：统一机器人接口与仿真/实机解耦

## 目标
将上层规划、工具、网页和导航模块从 MuJoCo 具体后端中解耦，形成可复用的统一机器人接口，使后续 MuJoCo、Isaac Sim、Gazebo 与真实机器人可以通过适配层迁移。

## 当前阶段
完成

## 各阶段

### 阶段 1：需求与边界确认
- [x] 明确目录职责：`master` 上层规划，`slaver` 下层工具，`agent` 语义匹配，`deploy` 网页，`assets` 资产，`nav2` 通路生成，`serve` MuJoCo，`serve_real` 实机。
- [x] 识别当前耦合点。
- [x] 将发现记录到 `findings.md`。
- **状态：** complete

### 阶段 2：统一接口设计
- [x] 新增 `robot_api/` 作为上层唯一机器人接口。
- [x] 定义通用 HTTP client，隐藏 `/grasp`、`/place`、`/objects` 等后端端点。
- [x] 将真实抓取/底盘桥接放到统一 runtime 层，而不是放在 `slaver` 或 `serve` 中。
- **状态：** complete

### 阶段 3：上层调用迁移
- [x] 修改 `slaver/robot/module/*` 使用 `robot_api`。
- [x] 修改 `slaver/robot/waypoint_manager.py` 使用 `robot_api`。
- [x] 修改 `master/agents/planner.py` 使用 `robot_api`。
- [x] 修改 `deploy/run.py` 使用统一配置。
- [x] 修改 `nav2` 读取统一 scene/map 接口。
- **状态：** complete

### 阶段 4：服务边界清理
- [x] 移除 `serve/service/server.py` 对 `serve_real` 的直接 import。
- [x] 保持 `serve` 只负责 MuJoCo 仿真 API。
- [x] 保持 `serve_real` 独立，可被任何 runtime 调用。
- **状态：** complete

### 阶段 5：文档与验证
- [x] 更新 README/相关文档中的接口边界。
- [x] 静态编译检查。
- [x] 不主动启动服务或发送真实抓取信号。
- **状态：** complete

### 阶段 6：按 1/0 信号路由收紧 robot_api
- [x] 新增 `robot_api/config.yaml`，用 `enabled/provide_state/accept_action/required` 控制每个后端是否参与。
- [x] 移除 `robot_api/scene_memory.py`，避免把语义记忆混入公开机器人接口。
- [x] 重写 `robot_api/runtime.py`，按状态/动作分别路由到启用后端。
- [x] 保持 `robot_api/client.py` 只暴露 LLM/工具真正关心的公开能力接口。
- [x] 更新 `robot_api/contract.md` 和 README/Slaver README。
- [x] 静态检查与配置读取检查。
- **状态：** complete

### 阶段 7：语义接口重构
- [x] `robot_api/client.py` 只保留语义公开接口，不暴露 endpoint、阈值、控制器参数。
- [x] `robot_api/runtime.py` 内部把语义动作翻译成各后端需要的参数。
- [x] 移除公开 `call_backend`、`move_arm`、`open_gripper`、`close_gripper` 等低层接口。
- [x] Slaver 工具模块改用语义接口：`grasp_object`、`place_object`、`navigate_to`、`move_forward`、`rotate`、`capture_image`。
- [x] 项目内部路径改为相对路径，`robot_api/config.yaml` 不出现项目绝对路径。
- [x] 更新文档与静态检查。
- **状态：** complete

### 阶段 8：MuJoCo 后端目录整理
- [x] 新增 `serve/backend/` 作为 MuJoCo runtime 目录。
- [x] 将 MuJoCo runtime 移到 `serve/backend/mujoco_backend.py`。
- [x] 删除旧的 service 客户端入口，`serve/service/` 只保留 HTTP 服务端职责。
- [x] 更新 README、service README、`robot_api/contract.md` 和开发说明。
- **状态：** complete

### 阶段 9：真实后端目录整理
- [x] 新增 `serve_real/bridge/`，放 `robot_api.runtime` 调用的真实硬件桥接。
- [x] 新增 `serve_real/service/`，放开发板侧常驻服务。
- [x] 新增 `serve_real/backend/`，放真实硬件驱动和测试脚本。
- [x] 更新 `robot_api.runtime` 的真实后端导入。
- [x] 更新 README 和 `serve_real` 文档。
- [x] 静态检查与旧路径搜索。
- **状态：** complete

### 阶段 10：ROS2 SLAM/Nav2 bridge
- [x] 为 MuJoCo 后端新增 `GET /scan`。
- [x] 新建 `ros2_ws/src/fqplanner_nav_bridge/` ROS2 Python 包。
- [x] 新增 `mujoco_bridge.py` 发布 `/scan`、`/odom`、`/tf` 并转发 `/cmd_vel`。
- [x] 新增 `nav2_goal_bridge.py` 将 HTTP `/nav` 转为 Nav2 action。
- [x] 新增 SLAM 和 Nav2 launch 文件。
- [x] 更新 nav2、robot_api contract 和 serve service 文档。
- **状态：** complete

## 关键问题
1. 统一接口应避免改变现有 HTTP API，优先复用 `/grasp`、`/place`、`/scene` 等端点。
2. 真实硬件触发必须由配置控制，不能在纯仿真模式下误触发。
3. 本轮重构以解耦为主，不做大规模目录搬迁，降低破坏现有运行方式的风险。

## 已做决策
| 决策 | 理由 |
|------|------|
| 新增 `robot_api/` 而不是重命名 `serve` | `serve` 目前就是 MuJoCo 适配层，新增 facade 能最小化破坏 |
| 上层只调用 `robot_api.client` | 后续 Isaac/Gazebo 只需实现相同 API 或替换 client 配置 |
| 真实抓取/底盘桥接从 `slaver`/`serve` 移到 runtime 层 | 保持 `slaver` 不关心 sim/real，保持 `serve` 不依赖 `serve_real` |
| `robot_api/config.yaml` 使用 1/0 路由，不使用 `primary` | 用户希望每个后端独立控制是否传递状态和动作 |
| `robot_api.client` 只暴露语义参数 | `snap_threshold` 等后端实现参数不应进入 LLM/工具稳定接口 |
| `serve/service/` 不再放 client | 上层客户端统一在 `robot_api.client`，service 只表达后端 HTTP 服务 |
| `serve_real/bridge` 与 `serve_real/service` 分开 | 上层触发真实硬件和开发板监听服务是两个不同职责 |
| ROS2 bridge 独立放在 `ros2_ws/src/fqplanner_nav_bridge` | 不把 ROS2 依赖塞进 MuJoCo 后端或 LLM 工具层 |

## 遇到的错误
| 错误 | 尝试次数 | 解决方案 |
|------|---------|---------|
| 无 | 0 | - |

## 备注
- 本轮不主动运行真实服务，不发送 `0xAA`。
- 若需要更深层的 sim2sim 支持，下一步可增加 `serve_isaac/`、`serve_gazebo/` 并实现相同 HTTP 契约。
