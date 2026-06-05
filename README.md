# FQPlanner_Mujoco

FQPlanner_Mujoco 是 FQPlanner 的 MuJoCo / XLeRobot 迁移版本。当前目标是保留原来的 Master / Slaver / Web / 场景配置和规划调用方式，同时把仿真后端换成本地 XLeRobot 机器人模型。

## 当前状态

- 机器人模型：使用本项目内的 `assets/xlerobot/xlerobot.xml` 和 `assets/xlerobot/*.stl`。
- 厨房场景：通过 RoboCasa 的 `KitchenArena + ManipulationTask` 导出真实厨房 fixtures / object MJCF，再合并到 XLeRobot MuJoCo XML。
- 运行后端：`serve/main.py` 启动 MuJoCo viewer 和 Flask API，端口 `5001`。
- 项目自包含 XLeRobot 文件，不会启动时从 `/home/fangqi/WorkXCJ/XLeRobot` 同步。
- `serve/scene/config/objects.yaml` 控制有哪些物体和 placement；cup、bowl、apple、mug 当前都在 counter 上随机采样，并带最小距离避让。

## 快速启动

### 1. 启动仿真后端

```bash
conda activate robocasa
cd /home/fangqi/WorkXCJ/FQPlanner_Mujoco/serve
python main.py
```

启动后会打开 MuJoCo viewer，并启动 API：

```text
http://127.0.0.1:5001
```

只启动 API、不打开 viewer：

```bash
python main.py --no-viewer
```

### 2. 启动规划系统

```bash
redis-server

conda activate FQPlanner
cd /home/fangqi/WorkXCJ/FQPlanner_Mujoco
python master/run.py
python slaver/run.py
python deploy/run.py
```

Web 控制台：

```text
http://127.0.0.1:8888
```

## 关键路径

```text
assets/xlerobot/xlerobot.xml              # 当前使用的 XLeRobot 模型
assets/xlerobot/*.stl                     # 当前使用的 XLeRobot STL 网格
assets/scene/scene.xml                    # 生成后的厨房 + XLeRobot 场景
assets/scene/scene_meta.json              # 生成后的 fixtures / objects 元信息
serve/mujoco_backend.py                   # 场景导出、XML 合并、MuJoCo Env 适配器
serve/main.py                             # MuJoCo viewer + Flask API 入口
serve/scene/config/objects.yaml           # 可操作物体和 placement 配置
serve/scene/config/layout.yaml            # 厨房布局
serve/scene/config/style.yaml             # RoboCasa 风格 / 材质配置
```

## 可用物体

当前 `objects.yaml` 中的可操作物体：

```text
pot
cup
bowl
apple
mug
sponge
```

当前放置逻辑：

- `pot`：counter，靠近 stove 参照区域。
- `cup`、`bowl`、`apple`、`mug`：counter 随机区域，带位置避让。
- `sponge`：island 随机区域。

## API 兼容性

仿真后端保留了原 Slaver 调用需要的主要 API：

```text
GET  /status
GET  /base_status
GET  /objects
GET  /fixtures
GET  /scene
GET  /scene_state
GET  /map_data
POST /grasp
POST /place
POST /move_to
POST /nav
POST /cmd_vel
POST /open_gripper
POST /close_gripper
POST /screenshot
```

因此原来的规划链路可以继续通过 Slaver 的工具调用访问仿真后端。

## 注意事项

- 当前不是 RoboCasa 原生环境 reset；RoboCasa 用于导出真实厨房和物体 MJCF。
- 当前抓取 / 放置是高层测试实现：服务端会分步移动虚拟末端和物体用于可视化，但不是完整接触抓取和 IK。
- XLeRobot 使用 `/home/fangqi/WorkXCJ/MuJoCo-GS-Web` 的真实外观模型；底盘 body 是 `chassis`，为 `freejoint`，当前生成场景把初始位置放在岛台和台面之间：`[3.2, -1.5, 0.38]`。
- 如果要完全复现 RoboCasa 原始物体采样，需要继续接入 RoboCasa 原生 placement sampler；当前实现是基于 fixture `pos/size` 的轻量 placement。

## 文档

- [usage.md](usage.md) — 启动和 API 使用说明
- [CLAUDE.md](CLAUDE.md) — 当前技术状态和开发注意事项
- [task_plan.md](task_plan.md) — 迁移计划
- [findings.md](findings.md) — 迁移发现
- [progress.md](progress.md) — 进度记录
