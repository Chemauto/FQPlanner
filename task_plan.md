# FQPlanner_Mujoco 迁移计划

## 目标
去除 RoboCasa/robosuite 运行时依赖，保留原 `serve/scene/config` 场景配置和服务 API，改为纯 MuJoCo 加载本地 XLeRobot 机器人。

## 阶段

| 阶段 | 状态 | 内容 |
| --- | --- | --- |
| 1 | complete | 本地复制 XLeRobot MuJoCo 模型与 mesh，项目自包含 |
| 2 | complete | 新增纯 MuJoCo 场景生成与 Env 适配器 |
| 3 | complete | 替换 serve 入口和工具层中的 RoboCasa 依赖 |
| 4 | complete | smoke test：XML 编译、状态查询、导航、抓放接口 |
| 5 | complete | 按 `objects.yaml` 的 `placement` 生成物体位置，并加入同一台面物体避让 |

## 约束
- 不修改 `/home/fangqi/WorkXCJ/FQPlanner`。
- 不依赖启动时同步 `/home/fangqi/WorkXCJ/XLeRobot`。
- `serve/scene/config` 作为原场景配置源，不改变其语义。
- `objects.yaml` 中 cup、bowl、apple、mug 均放在 counter 上随机采样；生成器会避免同一 fixture 上的物体挤在一起。
