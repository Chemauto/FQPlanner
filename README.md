# FQPlanner_Mujoco

本项目基于 [FlagScale](https://github.com/FlagOpen/FlagScale) 和 [RoboOS](https://github.com/FlagOpen/RoboOS) 的智能体与具身系统开发思路，结合 [RoboCasa](https://github.com/robocasa/robocasa)、MuJoCo 和 XLeRobot 资源，将 FQPlanner 的 Master / Slaver / Web 控制链路迁移到本地仿真与可选实机桥接环境中。

项目重点支持：

- LLM 任务规划到 MCP 工具调用的闭环执行。
- XLeRobot 在 RoboCasa 风格厨房场景中的 MuJoCo 仿真。
- 抓取、放置、导航、场景状态查询等基础机器人接口。
- 仿真抓取后向真实开发板发送抓取信号的可选桥接。

## Architecture

```text
User / Web UI
  -> master/              任务规划
  -> Redis                消息通信
  -> slaver/              MCP 工具执行
  -> robot_api/           统一机器人接口
  -> serve/               MuJoCo HTTP 后端
  -> serve_real/          可选真实机器人桥接
```

抓取链路：

```text
自然语言指令
  -> slaver/robot/module/grasp.py::grasp_object
  -> robot_api.client
  -> robot_api/config.yaml 中启用的动作后端
  -> 默认 MuJoCo: serve/service/server.py POST /grasp
  -> serve/backend/mujoco_backend.py
  -> real.accept_action = 1 时发送 0xAA
  -> serve_real/bridge/arm.py
  -> serve_real/service/grasp_server.py
  -> camera_10s.sh
```

## Repository

```text
assets/xlerobot/             XLeRobot MJCF 与 mesh 资源
assets/scene/                生成后的 MuJoCo 场景
serve/                       MuJoCo HTTP 后端、场景生成、动作实现
serve/backend/               MuJoCo 运行时环境
serve/scene/config/          layout / style / objects / waypoints 配置
robot_api/                   上层复用的统一机器人接口
serve_real/                  真实机器人 bridge / service / backend
master/                      任务规划服务
slaver/                      MCP 工具执行服务
deploy/                      Web 控制台
nav2/                        导航与地图辅助文件
```

## Requirements

建议使用两个 Conda 环境：

- `robocasa`：运行 MuJoCo、RoboCasa 场景生成和仿真后端。
- `FQPlanner`：运行 Master、Slaver、Web、MCP 工具和模型客户端。

Python 依赖见 [`requirements.txt`](requirements.txt)。敏感信息请放入 `.env` 或本地配置文件，不要提交 API key、开发板密码或私有 token。

## Quick Start

启动 Redis：

```bash
redis-server
```

启动 MuJoCo 后端：

```bash
conda activate robocasa
cd serve
python main.py
```

无窗口模式：

```bash
python main.py --no-viewer
```

启动规划链路：

```bash
conda activate FQPlanner
python master/run.py
python slaver/run.py
python deploy/run.py
```

默认服务地址：

```text
Robot API: http://127.0.0.1:5001
Web UI:    http://127.0.0.1:8888
```

基础检查：

```bash
curl http://127.0.0.1:5001/status
curl http://127.0.0.1:5001/objects
curl http://127.0.0.1:5001/scene
```

## Real Robot Bridge

动作是否传递给真实机器人由 [`robot_api/config.yaml`](robot_api/config.yaml) 控制：

```yaml
backends:
  real:
    enabled: 1
    accept_action: 1
    required: 1
```

真实硬件连接参数放在 [`serve_real/config.yaml`](serve_real/config.yaml)。`host` 只填写开发板 IP，不要写成 `user@ip`。

开发板侧启动：

```bash
python3 serve_real/service/grasp_server.py
```

当前抓取服务器收到 `0xAA` 后会执行：

```bash
camera_10s.sh
```

修改 `robot_api/config.yaml` 后，需要重启 Slaver 或 `slaver/robot/skill.py`，让工具进程重新加载配置。

## Safety

- 纯仿真测试时建议保持 `real.enabled: 0` 或 `real.accept_action: 0`。
- 实机运行前确认工作空间安全，并准备独立急停或停止脚本。
- 停止 `grasp_server.py` 只能阻止新指令；已经下发到硬件或脚本中的动作是否停止，取决于真实控制脚本和硬件控制器。
- `camera_10s.sh` 是当前实机动作边界，脚本应在失败时返回非零退出码。

## Documentation

- [`usage.md`](usage.md)：启动流程和 API 示例。
- [`CLAUDE.md`](CLAUDE.md)：当前迁移状态和开发注意事项。
- [`serve_real/README.md`](serve_real/README.md)：真实机器人桥接说明。
- [`robot_api/contract.md`](robot_api/contract.md)：统一机器人接口契约。

## References

- [FlagScale](https://github.com/FlagOpen/FlagScale)
- [RoboOS](https://github.com/FlagOpen/RoboOS)
- [RoboCasa](https://github.com/robocasa/robocasa)
- [MuJoCo](https://mujoco.org/) and [MuJoCo Documentation](https://mujoco.readthedocs.io/)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [Flask Documentation](https://flask.palletsprojects.com/)
- [Redis Documentation](https://redis.io/docs/latest/)

## License

This project is released under the Apache License 2.0. See [`LICENSE`](LICENSE) for details.
