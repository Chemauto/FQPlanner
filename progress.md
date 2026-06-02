# 进度记录

## 2026-06-02
- 用户明确要求不要启动时同步 XLeRobot，而是直接复制文件，项目单独依靠 `FQPlanner_Mujoco`。
- 已确认本地 XLeRobot MuJoCo scene 编译成功：`nbody=34, njnt=20, nu=18, ngeom=46`。
- 当前开始实现纯 MuJoCo backend，目标是去除 RoboCasa 运行时但保留原场景配置。
- 已新增 `serve/mujoco_backend.py`，从 `serve/scene/config` 调用 RoboCasa 生成真实厨房/物体 MJCF，再合并本地 XLeRobot XML，并提供 `MujocoKitchenEnv`。
- 已替换 `serve/utils/utils.py`、`serve/tools/move.py`、`serve/tools/arm.py`、`serve/service/server.py`、`serve/main.py` 的运行时路径，启动不再需要 RoboCasa/robosuite。
- 验证通过：场景创建、对象/家具/base/scene/map_data API 查询、直接 nav、抓放高层接口、offscreen render、Python 语法检查。
- 用户反馈 primitive 近似场景不可用后，已切换为真实 RoboCasa asset 导出路线。验证通过：真实场景 + XLeRobot 编译成功，6 个 RoboCasa 对象注册成功，offscreen render 成功。
- 已切换物体初始位置生成逻辑：优先按 `objects.yaml placement` 放置，cup/bowl/apple/mug 均在 counter 上随机采样，并加入同一台面最小 0.35m 的位置避让。最新生成结果无小于 0.35m 的近距离物体对。
