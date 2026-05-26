# Plan3: 机器人程序化控制工具

## 一、目标

在 `serve/tools/` 下提供程序化的机器人控制函数，替代键盘遥操作，支持：
1. 移动末端执行器到指定位置
2. 抓取物体
3. 释放物体
4. 移动底座到指定位置
5. 查询机器人和物体状态

**当前状态**：原 `robot_control.py` 已拆分为 `arm.py`（机械臂控制）和 `move.py`（底盘导航）。

## 二、背景：PandaOmron 动作空间

PandaOmron 使用 `HYBRID_MOBILE_BASE` 复合控制器，动作是 12 维向量：

```
action[0:3]   → 末端位置增量 [dx, dy, dz]     （OSC_POSE 控制器，范围 ±0.05m/step）
action[3:6]   → 末端旋转增量 [droll, dpitch, dyaw]（范围 ±0.5 rad/step）
action[6:7]   → 夹爪 [负数=打开, 正数=关闭]
action[7:11]  → 底座移动 [dx, dy, drot, ?]    （JOINT_VELOCITY 控制器）
action[11:12] → 控制模式 [负数=手臂模式, 正数=底座模式]
```

### 控制模式

- `action[-1] < 0`：手臂模式，末端增量控制
- `action[-1] > 0`：底座模式，底座移动时手臂跟踪目标

### 关键 API

```python
# 获取末端位置
ee_id = env.sim.model.body_name2id("robot0_right_hand")
ee_pos = env.sim.data.body_xpos[ee_id]

# 获取物体位置
obj_pos = env.sim.data.body_xpos[env.obj_body_id["pot"]]

# 检查是否抓住物体
from robocasa.utils.object_utils import check_obj_grasped
check_obj_grasped(env, "pot")  # True/False

# 执行动作
env.step(action)  # action 是 12 维 numpy 数组
```

## 三、函数设计

### arm.py 提供的函数（机械臂控制）

```python
def get_ee_pos(env):
    """获取末端执行器当前位置 [x, y, z]"""

def get_obj_pos(env, obj_name):
    """获取物体位置 [x, y, z]"""

def get_arm_state(env):
    """获取机械臂状态：末端位置、夹爪状态"""

def move_to(env, target_pos, steps=300, threshold=0.03, gain=1.5):
    """移动末端到目标位置（PD 控制 + 世界→body 坐标变换）"""

def open_gripper(env, steps=10):
    """打开夹爪"""

def close_gripper(env, steps=10):
    """关闭夹爪"""

def is_grasped(env, obj_name, threshold=0.035):
    """检查是否抓住物体"""

def grasp(env, obj_name, approach_height=0.15, snap_threshold=0.2):
    """抓取：移到上方→下降→吸附修正→关夹爪→提起"""

def release(env, lift_height=0.1, steps=20):
    """释放：开夹爪→提起"""

def pick_and_place(env, obj_name, target_pos, approach_height=0.15):
    """抓取并放置"""
```

### move.py 提供的函数（底盘导航）

```python
def get_base_info(env):
    """获取底座完整信息：位置、偏航角、qpos、qvel、ctrl"""

def move(env, Vx=0.0, Vy=0.0, Vw=0.0):
    """单步移动（直接发送速度指令）"""

def nav(env, x, y, w, yaw, Kp=1.5, Kd=0.3):
    """导航到目标位置（三阶段 PD 控制：消除 X→Y→Yaw 误差）"""
```

## 四、实现细节

### move_to 的控制逻辑

```python
def move_to(env, target_pos, steps=50, threshold=0.02):
    for _ in range(steps):
        ee_pos = get_ee_pos(env)
        error = np.array(target_pos) - ee_pos

        if np.linalg.norm(error) < threshold:
            return True

        # 限制步长，防止振荡
        max_step = 0.05
        error = np.clip(error, -max_step, max_step)

        action = np.zeros(12)
        action[0:3] = error / max_step  # 归一化到 [-1, 1]
        action[-1] = -1  # 手臂模式

        env.step(action)
    return False
```

### grasp 的分阶段控制

```
阶段 1：移动到物体正上方（approach_height 高度）
阶段 2：下降到物体位置
阶段 3：关闭夹爪（多步确认）
阶段 4：提起物体
```

### 关键注意事项

1. **坐标系**：action 中的增量是 body 坐标系下的，需要世界→body 坐标变换
2. **归一化**：action 值需要在 [-1, 1] 范围内
3. **底座 body**：必须用 `mobilebase0_base` 读取底座位置，`robot0_base` 是固定 body 不会动
4. **前进+旋转不能同时**：action[7]（前进）和 action[9]（旋转）不能同时使用，旋转会消除前进效果
5. **仿真步进**：每次 `env.step()` 后需要等待物理仿真稳定

## 五、文件结构

```
serve/tools/
├── __init__.py
├── arm.py           # 机械臂控制（move_to, grasp, release, pick_and_place）
└── move.py          # 底盘导航（get_base_info, move, nav）
```

## 六、验证方法

1. 导入并调用 `get_robot_state(env)` 确认状态查询正常
2. 调用 `move_to(env, [x, y, z])` 确认末端移动到目标
3. 调用 `grasp(env, "pot")` 确认抓取成功（`check_obj_grasped` 返回 True）
4. 调用 `release(env)` 确认释放成功
5. 调用 `pick_and_place(env, "pot", [x, y, z])` 确认完整流程

## 七、不包含的功能（后续可扩展）

- 路径规划（避障）— 当前 nav 只走直线
- 逆运动学求解（当前用增量控制近似）
- 视觉伺服（基于相机观测的抓取）
