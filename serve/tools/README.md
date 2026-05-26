# tools/ — 机器人控制工具

## 文件说明

- **arm.py** — 机械臂控制（抓取、放置、移动、夹爪）
- **move.py** — 底盘导航（移动、路径控制）

## arm.py 函数列表

### 状态查询

| 函数 | 说明 |
|------|------|
| `get_arm_info(env)` | 获取机械臂全部状态（末端位姿、夹爪、关节位置/速度、底座、躯干） |
| `get_obj_pos(env, obj_name)` | 获取物体位置 [x, y, z] |
| `is_grasped(env, obj_name)` | 检查是否抓住物体 |

### 移动控制

| 函数 | 说明 |
|------|------|
| `move_arm(env, target_pos, max_steps, pos_threshold, gain)` | 移动末端到目标位置（delta 控制模式） |
| `move_arm_OSC_POSE(env, target_pos, target_rot)` | 移动末端到目标位置（OSC_POSE absolute 模式） |
| `get_osc_pose_controller_config()` | 获取 OSC_POSE absolute 模式的控制器配置 |

### 夹爪控制

| 函数 | 说明 |
|------|------|
| `open_gripper(env, steps)` | 打开夹爪 |
| `close_gripper(env, steps)` | 关闭夹爪 |

### 高级操作

| 函数 | 说明 |
|------|------|
| `grasp(env, obj_name, snap_threshold)` | 抓取物体：移近→吸附→关夹爪→提起 |
| `place(env, obj_name, target_pos, snap_threshold)` | 放置物体：移近→瞬移物体→开夹爪→提起 |

## move.py 函数列表

| 函数 | 说明 |
|------|------|
| `get_base_info(env)` | 获取底座完整信息（位置、偏航角、qpos、qvel、ctrl） |
| `move(env, Vx, Vy, Vw)` | 单步移动（直接发送速度指令） |
| `nav(env, x, y, w, yaw)` | 导航到目标位置（PD 控制，分阶段消除误差） |

## 修改记录

### PandaOmron 控制器参数调整

**文件**: `robosuite/controllers/config/robots/default_pandaomron.json`

**修改内容**（OSC_POSE 手臂控制器）:

| 参数 | 原值 | 新值 | 说明 |
|------|------|------|------|
| `output_max` (位置) | 0.05 | 0.10 | 每步最大位移从 5cm 提升到 10cm |
| `output_min` (位置) | -0.05 | -0.10 | 同上（负方向） |
| `ramp_ratio` | 0.2 | 1.0 | 去掉加速延迟，直接全速输出 |

**原因**: 原 `output_max=0.05` 导致手臂每步最多移动 5cm，远距离移动非常慢。
原 `ramp_ratio=0.2` 需要 5 步才能达到全速，进一步拖慢启动。
调整后手臂移动速度提升约 2 倍。

**注意事项**:
- 如果手臂运动出现抖动或不稳定，可适当降低 `output_max`（如 0.10）
- 此修改影响所有使用 PandaOmron 的场景
- 旋转参数（0.5 rad）未改动
