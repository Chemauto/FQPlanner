# tools/ — 机器人控制工具

直接操作 `MujocoKitchenEnv` 的控制函数，被 `service/server.py` 调用。

```
tools/
├── arm.py    # 机械臂控制（末端移动、抓取、放置、夹爪）
└── move.py   # 底盘导航（速度控制、目标点导航）
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
| `move(env, Vx, Vw)` | 单步速度控制（差速驱动，ctrl[0]=forward, ctrl[1]=turn） |
| `nav(env, x, y, target_yaw)` | 导航到目标位置（差速驱动 PD 控制） |

## 底盘控制说明

使用 MuJoCo-GS-Web 的 XLeRobot 模型，差速驱动：
- `chassis` 是 `freejoint`，启动时自然沉降到地面
- 轮子通过 motor actuator + tendon 驱动（ctrl[0]=forward, ctrl[1]=turn）
- 与实物接口一致，部署时可直接复用
