# FQPlanner_Mujoco 技术说明

本项目是 FQPlanner 的 MuJoCo / XLeRobot 迁移版本。保留 Master、Slaver、Web 控制台和原服务 API 形态，同时将仿真后端改为本地 XLeRobot MuJoCo 模型。

## 架构

```text
用户
  -> Web 控制台 (8888)
  -> Master (5000)
  -> Redis
  -> Slaver / MCP 工具
  -> serve Flask API (5001)
  -> MuJoCo: XLeRobot + RoboCasa kitchen MJCF
```

## 当前后端

`serve/main.py`：

- 创建 `MujocoKitchenEnv`
- 生成 / 加载 `assets/scene/scene.xml`
- 启动 Flask API
- 默认打开 MuJoCo viewer
- 每帧处理命令队列并 step MuJoCo

`serve/mujoco_backend.py`：

- 读取 `serve/scene/config/layout.yaml`
- 读取 `serve/scene/config/style.yaml`
- 读取 `serve/scene/config/objects.yaml`
- 调用 RoboCasa `KitchenArena`
- 调用 RoboCasa / robosuite object MJCF 工具生成真实厨房 fixtures 和 objects
- 合并本地 `assets/xlerobot/xlerobot.xml`
- 隐藏 collision / registry / backing / eef target 等非视觉调试几何
- 写出：

```text
assets/scene/scene.xml
assets/scene/scene_meta.json
```

## XLeRobot

当前机器人模型路径：

```text
assets/xlerobot/xlerobot.xml
assets/xlerobot/*.stl
```

注意：

- `assets/xlerobot/` 是有效 mesh 目录，`xlerobot.xml` 和 mesh 文件放在同一级。
- 不再使用旧的 `assets/xlerobot/meshes/`。
- 不再使用旧的 `robots/` robosuite 注册目录。
- 不会启动时从 `/home/fangqi/WorkXCJ/XLeRobot` 同步。

关键 body / actuator：

```text
body: chassis
initial pos: [0, 0, 0.035]
base actuators: slider_actuator_x, slider_actuator_y, hinge_actuator_z
right gripper bodies: Fixed_Jaw_2, Moving_Jaw_2
```

## 物体和位置

物体列表来自：

```text
serve/scene/config/objects.yaml
```

当前物体：

```text
pot
cup
bowl
apple
mug
sponge
```

placement 规则：

- 优先使用 `objects.yaml` 中的 `placement`。
- 通过 fixture 的真实 `pos/size` 估算可放置区域。
- 没有 placement 时才兜底使用 `waypoints.yaml`。
- 同一 fixture 上随机物体使用最小距离避让，当前阈值为 `0.35m`。

当前配置：

- `pot`：counter，靠近 stove。
- `cup`、`bowl`、`apple`、`mug`：counter 随机区域。
- `sponge`：island 随机区域。

## API

主要端点在 `serve/service/server.py`：

| 端点 | 方法 | 说明 |
| --- | --- | --- |
| `/status` | GET | 机械臂状态 |
| `/base_status` | GET | 底盘状态 |
| `/objects` | GET | 物体位置 |
| `/fixtures` | GET | fixtures 信息 |
| `/scene` | GET | 场景综合信息 |
| `/scene_state` | GET | 逻辑状态 |
| `/map_data` | GET | 地图生成数据 |
| `/grasp` | POST | 抓取物体 |
| `/place` | POST | 放置物体 |
| `/move_to` | POST | 移动虚拟末端 |
| `/nav` | POST | 底盘导航 |
| `/cmd_vel` | POST | 速度控制 |
| `/nav_path` | POST | 路径跟随 |
| `/open_gripper` | POST | 打开夹爪 |
| `/close_gripper` | POST | 关闭夹爪 |
| `/screenshot` | POST | 截图 |

## 工具层

`serve/tools/move.py`：

- 使用 MuJoCo-GS-Web 的 XLeRobot 真实外观模型。
- `chassis` 是 `freejoint`；`nav()` 根据世界坐标误差生成 body-frame 速度，再由工具层直接更新 x/y/yaw。
- body 名称是 `chassis`。

`serve/tools/arm.py`：

- 当前是高层测试抽象。
- `grasp()` 将物体绑定到虚拟末端。
- `place()` 通过 freejoint 把物体放到目标位置。
- 不是真实 IK / 接触抓取。

## 与原 FQPlanner 的兼容性

保留了原规划系统需要的主要 HTTP API 和 Slaver 工具语义，所以原 Master / Slaver 规划链路可以继续使用。

可以直接复用的部分：

- 自然语言任务规划
- Slaver 工具调用流程
- `navigate_to_target`
- `grasp_object`
- `place_object`
- `place_on_top`
- Web 控制台和 Redis 通信

需要注意的部分：

- 原 prompt / 文档里如果写死 PandaOmron 或 RoboCasa 原生 env，需要改成 XLeRobot / MuJoCo。
- 任务里的物体名必须匹配当前 `objects.yaml`。
- 真实抓取能力还不是完整物理抓取，目前是高层吸附 / 放置；服务端会分步移动虚拟末端和物体，避免一帧瞬移。
- 如果要完全复现 RoboCasa 原始 placement sampler，还需要进一步接入 RoboCasa 原生 placement initializer。

## 启动

```bash
conda activate robocasa
cd /home/fangqi/WorkXCJ/FQPlanner_Mujoco/serve
python main.py
```

不打开 viewer：

```bash
python main.py --no-viewer
```

完整规划链路：

```bash
redis-server

conda activate FQPlanner
cd /home/fangqi/WorkXCJ/FQPlanner_Mujoco
python master/run.py
python slaver/run.py
python deploy/run.py
```

## 开发注意

- 修改 `objects.yaml` 后，重启 `serve/main.py` 会重新生成场景 XML。
- 修改 XLeRobot 模型后，需要直接更新本项目内 `assets/xlerobot/xlerobot.xml` 和 `assets/xlerobot/*.stl`。
- 不要恢复旧的 `robots/` 目录；当前不通过 robosuite robot registry 加载 XLeRobot。
- 不要重新创建 `assets/xlerobot/meshes/` 或 `assets/xlerobot/assets/`；当前 robot XML 的 meshdir 是 `./`，生成场景 XML 的 meshdir 是 `../xlerobot/`。
