# tools/ — 机器人控制工具

直接操作 `MujocoKitchenEnv` 的控制函数，被 `service/server.py` 调用。

```
tools/
├── arm.py    # 机械臂控制（末端移动、抓取、放置、夹爪）
└── move.py   # 底盘导航（速度控制、目标点导航、路径跟随）
```

## arm.py — 机械臂控制

| 函数 | 作用 |
|------|------|
| `get_arm_info(env)` | 获取末端位姿、夹爪状态、关节位置/速度 |
| `get_obj_pos(env, name)` | 获取物体世界坐标 [x, y, z] |
| `is_grasped(env, name)` | 检查是否抓住物体 |
| `move_arm(env, target_pos)` | 移动虚拟末端到目标位置 |
| `open_gripper(env)` | 打开夹爪 |
| `close_gripper(env)` | 关闭夹爪 |
| `grasp(env, name)` | 抓取：移近→吸附→关夹爪→提起 |
| `place(env, name, target)` | 放置：移近→瞬移物体→开夹爪→提起 |

当前抓取/放置是高层实现（虚拟末端 + 物体吸附），不是真实 IK + 接触抓取。

## move.py — 底盘导航

| 函数 | 作用 |
|------|------|
| `get_base_info(env)` | 获取底座位置、朝向、qpos、qvel、ctrl |
| `move(env, Vx, Vy, Vw)` | 单步速度控制（body-frame） |
| `nav(env, x, y, target_yaw)` | 导航到目标位置（PD 控制全向移动） |
| `follow_path(env, path, w)` | 路径跟随（全局路径点序列） |

## 底盘控制说明

使用 MuJoCo-GS-Web 的 XLeRobot 真实外观模型：
- `chassis` 是 `freejoint`
- 高层导航直接更新 chassis 的 x/y/yaw
- GS-Web XML 中的轮子 actuator 保留在模型里，但当前导航不依赖车轮物理
