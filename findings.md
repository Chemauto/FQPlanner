# 迁移发现

## 2026-06-02
- `assets/xlerobot/xlerobot.xml` 已复制为本项目本地文件，并可通过 `assets/xlerobot/scene.xml` 编译。
- XLeRobot 模型的底盘 body 名称是 `chassis`，底盘前三个 actuator 是 `slider_actuator_x`、`slider_actuator_y`、`hinge_actuator_z`。
- 右臂关键 body/joint 命名是 `Fixed_Jaw_2`、`Moving_Jaw_2`、`Rotation_R`、`Pitch_R`、`Elbow_R`、`Wrist_Pitch_R`、`Wrist_Roll_R`、`Jaw_R`。
- 原 `serve` 运行时强依赖 RoboCasa/robosuite：`env.robots`、`env.objects`、`env.fixtures`、`env.obj_body_id`、`robot0_right_hand`、`mobilebase0_base` 和 12 维 action。
- 原场景逻辑主要在 `serve/scene/config/waypoints.yaml`、`scene_state.yaml`、`objects.yaml`，可用于纯 MuJoCo world 的对象和家具位置。
- 纯 MuJoCo world 生成到 `assets/xlerobot/fqplanner_scene.xml`。当前版本通过 RoboCasa `KitchenArena + ManipulationTask` 导出真实厨房 fixtures 和 objects MJCF，再合并本地 XLeRobot XML。
- 真实 RoboCasa 场景导出验证通过：合并 XLeRobot 后 `nbody=423`、`ngeom=2549`、`nmesh=480`、`nu=18`。
- 物体位置现在优先来自 `serve/scene/config/objects.yaml` 的 `placement`，根据 RoboCasa fixture 的真实 `pos/size` 放到 counter/island 等台面区域；`waypoints.yaml` 只作为无 placement 时的兜底。
- cup、bowl、apple 已改为与 mug 一样放在 counter 上随机采样；同一 fixture 上的随机物体使用最小距离避让，当前阈值为 0.35m。
- 当前抓放接口是高层测试实现：保留完整 XLeRobot MJCF，但机械臂末端用虚拟目标点，物体通过 freejoint 吸附/放置。
