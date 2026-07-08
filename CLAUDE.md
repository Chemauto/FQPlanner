# FQPlanner_Mujoco 技术说明

本项目是 FQPlanner 的 MuJoCo 迁移版本。保留 Master、Slaver、Web 控制台和原服务 API 形态，仿真后端是 RoboCasa 厨房 + robosuite **PandaOmron** 机器人（曾短暂用过 XLeRobot，已换回 PandaOmron，见「## 机器人」）。

## 架构

```text
用户
  -> Web 控制台 (8888)
  -> Master (5000)
  -> Redis
  -> Slaver / MCP 工具
  -> robot_api
  -> serve Flask API (5001)
  -> MuJoCo: PandaOmron + RoboCasa kitchen MJCF
```

## 当前后端

`serve/main.py`：

- 创建 `MujocoKitchenEnv`
- 生成 / 加载 `assets/scene/scene.xml`
- 启动 Flask API
- 默认打开 MuJoCo viewer
- 每帧处理命令队列并 step MuJoCo

`serve/backend/mujoco_backend.py`：

- 读取 `serve/scene/config/layout.yaml`
- 读取 `serve/scene/config/style.yaml`
- 读取 `serve/scene/config/objects.yaml`
- 调用 RoboCasa `KitchenArena`
- 调用 RoboCasa / robosuite object MJCF 工具生成真实厨房 fixtures 和 objects
- robosuite 装配 PandaOmron 并 merge 进 `ManipulationTask`（见 `_assemble_pandaomron`）
- 隐藏 collision / registry / backing / eef target / 机器人调试 site 等非视觉几何
- 写出：

```text
assets/scene/scene.xml
assets/scene/scene_meta.json
```

## 机器人：PandaOmron

当前机器人是 **PandaOmron**（Franka Panda 白色 7-DOF 臂 + Omron 移动底座 + PandaGripper），
由 robosuite 原生装配（`create_robot("PandaOmron") + add_base + add_gripper`），
`scene_generator._assemble_pandaomron` 交给 `ManipulationTask(mujoco_robots=[robot])` merge 进厨房。
mesh 走 robosuite 安装目录的绝对路径（不需要项目内 mesh 目录）。

注意：

- 不再用 XLeRobot（`assets/xlerobot/xlerobot.xml`）——已从 robosuite registry 换回 PandaOmron。
- **底座用 Option F**：`scene_generator._pandaomron_freejoint_base` 给 `robot0_base` 加 `base_freejoint`、
  剥离 Omron 3 个平面移动关节（forward/side/yaw）及其 actuator → 复用现有 freejoint 运动学 nav。
- **臂是力矩驱动**（ctrl=0 会因重力下垂）→ `mujoco_backend._hold_arm_pose` 每步把臂/夹爪 qpos 钉回
  初始位姿（运动学冻结，臂随底座刚性移动，和吸附抓取同一思路）。
- **相机**：scene_generator 把 `robot0_eye_in_hand`→`right_arm_cam`，另在 `robot0_base` 上加一个
  抬高俯视工作区的 `head_cam`（PandaOmron 自带 robotview 看的是机器人自己，感知没用），
  复制 head_cam 当 `left_arm_cam`（单臂凑四宫格）。这样 camera.yaml/四宫格/segmentation 名字全不用改。
- **碰撞几何隐藏**：`_hide_collision_geoms` 把碰撞几何移到 group 4（不渲染，保留 contype 物理）；
  因为 `inertiagrouprange` 只算 group0 的质量，必须先把它扩到 `0 5`（`_set_physics_options`）否则
  freejoint 底座失去质量报错。`_hide_robot_sites` 藏夹爪绿柱等调试 site。

关键 body / actuator：

```text
base body: robot0_base   (加了 base_freejoint;初始 [3.2, -1.5, 0])
base joint: base_freejoint (freejoint,运动学 nav 直接设 qpos)
arm joints: robot0_joint1..7 (力矩 actuator robot0_torq_j1..7,靠 _hold_arm_pose 冻结)
gripper / EE: robot0_right_hand / gripper0_right_eef (抓取吸附到虚拟末端)
cameras: head_cam(工作区俯视) right_arm_cam(手眼) left_arm_cam(=head 复制) overhead_cam(俯视)
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
| `/open_gripper` | POST | 打开夹爪 |
| `/close_gripper` | POST | 关闭夹爪 |
| `/screenshot` | POST | 截图 |

## 工具层

`serve/tools/move.py`：

- 使用 robosuite PandaOmron 模型。
- `robot0_base` 加了 `base_freejoint`；`nav()` 根据世界坐标误差生成 body-frame 速度，再由工具层直接更新 x/y/yaw。
- 底座 body 名称是 `robot0_base`（不是 `chassis`）。

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
cd serve
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
python master/run.py
python slaver/run.py
python deploy/run.py
```

## 开发注意

- 修改 `objects.yaml` 后，重启 `serve/main.py` 会重新生成场景 XML。
- 机器人来自 robosuite registry（`create_robot("PandaOmron")`），改机器人在 `scene_generator._assemble_pandaomron`。
- 换机器人 body/关节/相机名后，`mujoco_backend`（robot0_base/base_freejoint/gripper EE/`_hold_arm_pose` 臂关节）、
  `serve/tools/move.py`（robot0_base）、`arm.py`（robot0_joint*/gripper）、`server.py`（robot0_base、地图排除）都要跟着改。
- 感知/四宫格靠 `head_cam` 抬高俯视工作区；换机器人若 head_cam 看不到台面物体，`/visible_objects?camera=head_cam&scan=1`
  会返回 []，要调 `_rename_robot_cameras` 里 head_cam 的 pos/xyaxes。
- 隐藏碰撞几何前必须先把 compiler `inertiagrouprange` 扩到含 group 4，否则 freejoint 底座失质量报错。
