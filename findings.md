# 发现与决策

## 需求
- 用户要把抓取从纯 MuJoCo 仿真迁移到现实：仿真仍要执行，真实侧通过信号触发 `/home/fangqi/WorkXCJ/FQPlanner/grasp_server.py`。
- 真实抓取参考 `/home/fangqi/WorkXCJ/FQPlanner/slaver/demo_robot_local/module/grasp.py`，该模块向开发板 `9999` 端口发送 `0xAA` 指令。

## 研究发现
- `FQPlanner/slaver/demo_robot_local/module/grasp.py` 的真实抓取协议很简单：socket 连接开发板 `socket_host:socket_port`，发送 `bytes([0xAA])`，读取文本响应；`SUCCESS...` 判定成功，`FAILED...` 判定失败。
- `FQPlanner/grasp_server.py` 监听 `0.0.0.0:9999`，收到首字节 `0xAA` 后执行 `/home/HwHiAiUser/test.sh`，返回 `SUCCESS:00:...` 或 `FAILED:<code>:...`。
- 当前 MuJoCo 服务 `serve/service/server.py` 的 `/grasp` 不是直接调用工具函数，而是进入命令队列，主循环中分 `approach` 和 `lift` 两阶段移动虚拟末端，最后 `_finish_command(..., {"success": True})`。
- 底盘真实接入已有 `serve_real/base_bridge.py`，服务启动时在 `serve/service/server.py` 顶部导入，`move_duration` 提交时启动真实线程，仿真主循环继续运行。
- `slaver/robot/module/grasp.py` 是当前 MuJoCo 工具注册层；它调用 `serve.service.client.grasp_object()`，没有直接硬件逻辑。只要服务端 `/grasp` 接入真实桥接，现有 LLM 工具调用就会自动触发。
- `serve_real/Arm` 目录存在但为空，适合放置新的真实机械臂桥接模块。
- 用户进一步明确触发层：LLM 会调用 `slaver/robot/module/grasp.py`，真实信号发送应该参考旧项目 `demo_robot_local/module/grasp.py` 放在这个工具接口链路里。
- 当前 `FQPlanner_Mujoco` 项目原本没有 `grasp_server.py`，也没有抓取 `.sh`。
- 本机 `/home/HwHiAiUser/test.sh` 不存在，无法直接迁移真实脚本内容，只能提供项目内 shell 入口让真实抓取命令落到当前仓库。

## 技术决策
| 决策 | 理由 |
|------|------|
| 新增 `serve_real/Arm` 桥接层 | 与已有 `serve_real/Base` 结构保持一致，真实硬件逻辑不侵入仿真工具层 |
| 真实抓取触发点放在仿真抓取成功后 | 保证仿真仍完整执行，同时避免物体不存在或仿真失败时误触真实机械臂 |
| 桥接函数同步返回结果 | 抓取动作本身会阻塞到 `grasp_server.py` 返回结果，调用方能看到真实执行成功或失败 |
| `fail_on_error` 默认开启 | 迁移到真实硬件后，物理抓取失败应反馈给调用方；只想看仿真结果时可配置关闭 |
| 将真实触发从 Flask 服务端移到 LLM 工具模块 | 用户明确真实抓取应从 `slaver/robot/module/grasp.py` 发信号；同时避免直接 HTTP `/grasp` 和 LLM 工具层重复触发 |
| 仿真失败时不触发真实抓取 | 保持“仿真也需要进行”的约束，并避免仿真目标不存在时误触实物 |
| 默认 `run_grasp.sh` 返回非零 | 未填入真实机械臂命令前，不应假装物理抓取成功 |

## 遇到的问题
| 问题 | 解决方案 |
|------|---------|
| 沙箱内不能创建监听 socket | 通过授权在沙箱外运行 `grasp_server.py` |
| 裸 `python3` 环境缺少 `yaml` | 使用项目的 `robocasa` 环境完成验证；服务端本身也依赖 `yaml` |

## 资源
- `/home/fangqi/WorkXCJ/FQPlanner/grasp_server.py`
- `/home/fangqi/WorkXCJ/FQPlanner/slaver/demo_robot_local/module/grasp.py`
- `serve/service/server.py`
- `serve_real/base_bridge.py`

## 视觉/浏览器发现
- 无。
