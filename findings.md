# 发现与决策

## 需求
- 每个目录职责清晰，避免仿真、实机、规划、工具、网页和导航混在一起。
- `serve` 当前仅代表 MuJoCo 仿真后端；未来不同仿真器应替换 `serve` 同层适配器。
- `serve_real` 应独立于仿真器，MuJoCo/Isaac/Gazebo 切换时不应改 `serve_real`。
- 所有上层接口应可复用，便于 sim2real 与 sim2sim。

## 研究发现
- Slaver 工具模块曾直接 import MuJoCo service 客户端和真实机械臂桥接，工具层混入仿真和实机细节。
- `serve/service/server.py` 曾直接 import 真实底盘桥接，仿真服务混入真实硬件；当前已移到 `robot_api.runtime`。
- `master/agents/planner.py` 直接请求 `http://127.0.0.1:5001/objects`，规划层绑定 MuJoCo 服务。
- `deploy/run.py`、`nav2/map_generator.py`、`nav2/workpoints_generator.py`、`slaver/robot/waypoint_manager.py` 多处写死 `127.0.0.1:5001`。
- `agent/tool_match` 与 `slaver/tools/tool_matcher.py` 存在相似职责，后续应统一，但本轮优先解决机器人接口解耦。

## 技术决策
| 决策 | 理由 |
|------|------|
| 新增 `robot_api/` | 给 master/slaver/deploy/nav2 一个稳定依赖点 |
| 保留现有 MuJoCo HTTP API | 降低对 `serve` 的改动风险 |
| `robot_api.runtime` 处理 sim+real 编排 | 避免工具层和仿真服务直接依赖真实硬件 |
| 配置集中到 `robot_api/config.yaml` | 用 `enabled/provide_state/accept_action/required` 控制每个后端是否传递状态和动作 |
| `robot_api.client` 只保留语义接口 | 如果公开接口只是 HTTP client 别名，就不能解决 sim2sim/sim2real 的语义解耦问题 |

## 遇到的问题
| 问题 | 解决方案 |
|------|---------|
| 真实底盘原先在 `serve` 中并发触发 | 移到 `robot_api.runtime.move_for_duration`，保持仿真请求和真实线程从同一上层接口触发 |
| `snap_threshold` 出现在公开 `grasp_object` | 移到 runtime 的 MuJoCo 翻译逻辑中，公开接口只保留 `object_name` |

## 资源
- `slaver/config.yaml` 中已有 `robocasa.server_url` 和 timeout，可作为默认 backend URL。
- `serve_real/config.yaml` 中已有 `real_arm`/`real_base` 配置。
- `robot_api/config.yaml` 应只负责 1/0 路由，真实硬件 IP、端口和串口留在 `serve_real/config.yaml`。

## 视觉/浏览器发现
- 无。
