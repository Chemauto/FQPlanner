# 大脑 ↔ 导航组 对接(接待 Demo:会议室 ↔ 茶水间)

> 导航栈 = **G1control**(YeLuo-123/G1control):Cartographer 建图 + Dijkstra 规划 + nav2point 跟踪避障 + SONIC 行走。
> 纯 ROS2 topic。大脑侧起一个 **HTTP↔ROS2 桥**(仓库已备 `docker/nav2/ros2_ws/src/fqplanner_nav_bridge/fqplanner_nav_bridge/g1_nav_bridge.py`)做翻译,你们不用为大脑改代码。

## 你们做什么(跑起这套栈,给这几个 topic)

| Topic | 类型 | 方向 | 内容 |
|---|---|---|---|
| `/g1pilot/goal` | PoseStamped(map 系) | 收 | 单个目标点(桥把大脑坐标发进来) |
| `/lidar_odometry/pose_fixed` | Odometry | 发 | 机器人实时位姿(桥读它判到达 + 报 `/base_status`) |
| `/map` | OccupancyGrid | 发 | 2D 占据地图 |

- **到达**:nav2point 到 `goal_tol≈0.1m` 自停;桥订阅位姿判到达,你们不用额外发到达信号。
- **办公椅避障**:✅ 有——nav2point 用 `/scan` 激光实时避,过不去自然停(桥超时返回失败)。

## 我给你们什么

- **目标点坐标**(map 系 `{x, y, yaw}`)——大脑从场景图算好,经桥发到 `/g1pilot/goal`。你们**不用维护"地名→坐标"表**。

## ⚠️ 不归你们(更正之前的手册)

**"数可乐 / 数办公椅"的语义场景图,这套导航栈不提供**(它只做建图/定位/规划/避障,不认物体类别)。
缺口计算要数的饮料、要识别的障碍语义,归**世界模型组的场景图 或 VLA 看图**,不放导航组。

## 请你们定

1. 仿真先用哪档:`navigation_demo`(纯逻辑) / `mujoco office`(带 `G1PILOT_SCENE=office`) / 真机?
2. 你们 office 地图的坐标系,和我们 3DGS 的 office 是同一个吗?(已初步核对**极可能同源**——X 起点 ≈ −7、Y ≈ ±6 对齐;若确认同源,导航用你们地图、渲染用我们 3DGS,位姿通用。)

栈起好后,把桥能连到的 ROS2 网络(或机器 IP)发我。联系人:毕艺恒(github.com/Chemauto/FQPlanner)
