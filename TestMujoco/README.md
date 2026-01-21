# MuJoCo仿真测试 (MuJoCo Simulation Test)

## 概述

本目录包含MuJoCo物理仿真环境中三麦克纳姆轮底盘的完整测试代码。

## 目录结构

```
TestMujoco/
├── controller/           # 控制器
│   ├── omni_controller.py      # 运动学控制器
│   ├── global_navigator.py     # 全局导航控制器
│   └── quick_reference.py      # 快速参考
├── model/                # MuJoCo模型文件
│   └── assets/
│       └── scene.xml          # 机器人场景模型
└── test/                 # 测试脚本
    ├── __init__.py
    └── test_mujoco.py          # 主测试程序
```

## 依赖安装

```bash
pip install mujoco mujoco-viewer numpy scipy
```

## 快速开始

### 方式1: 运行测试脚本

```bash
cd /home/dora/RoboOs/RoboOS/TestMujoco
python test/test_mujoco.py
```

### 方式2: 通过RoboOS模块

1. 启动Slaver:
```bash
cd /home/dora/RoboOs/RoboOS
python slaver/run.py
```

2. 发送指令测试:
- "打开MuJoCo仿真测试前进"
- "导航到位置0.5,0.3"
- "检查仿真状态"

## 功能说明

### 1. 运动学控制器 (OmniWheelController)

基于LeKiwi官方实现的三轮全向轮运动学。

**轮子配置:**
- 120°间隔布局
- 左轮: 30° to forward
- 右轮: 150° from forward
- 后轮: 270° from forward

**主要方法:**
- `set_velocity(linear_speed, vx, vy, omega)` - 设置速度
- `set_velocity_raw(vx, vy, omega)` - 原始速度控制
- `get_robot_position()` - 获取位置
- `stop()` - 停止

### 2. 全局导航控制器 (GlobalNavigator)

使用PID控制器实现精确的点到点移动。

**PID参数:**
- 位置控制: kp=1.5, ki=0.05, kd=0.05
- 姿态控制: kp=3.0, ki=0.02, kd=0.1

**主要方法:**
- `set_target(x, y, z, yaw)` - 设置目标
- `update(dt)` - 更新导航
- `is_target_reached()` - 检查是否到达

## 测试模式

### 运动学测试

测试基本运动是否正确:
1. 前进测试 - 应该直线向前
2. 后退测试 - 应该直线向后
3. 左移测试 - 应该直线向左
4. 右移测试 - 应该直线向右
5. 旋转测试 - 应该原地旋转不位移

### 导航测试

测试全局导航功能:
1. 单点移动 - 移动到一个目标点
2. 多点移动 - 方形路径
3. 带姿态控制 - 位置+姿态同时控制

## 技术细节

### 坐标系

**世界坐标系:**
- x轴: 机器人初始前方
- y轴: 机器人初始左侧
- z轴: 垂直向上

**机器人坐标系:**
- x轴: 机器人当前正前方
- y轴: 机器人当前左侧
- z轴: 垂直向上

### 精度指标

- 位置容差: 2cm
- 角度容差: 3度
- 速度限制: 0.8 m/s (位置), 2.0 rad/s (姿态)

## 使用示例

### Python代码示例

```python
import mujoco
import mujoco.viewer
from controller.omni_controller import OmniWheelController
from controller.global_navigator import GlobalNavigator

# 加载模型
model = mujoco.MjModel.from_xml_path('model/assets/scene.xml')
data = mujoco.MjData(model)

# 创建控制器
omni_controller = OmniWheelController(model, data)
navigator = GlobalNavigator(model, data)

# 设置目标
navigator.set_target(x=0.5, y=0.3, yaw=None)

# 导航循环
with mujoco.viewer.launch_passive(model, data) as viewer:
    while viewer.is_running():
        vx, vy, omega = navigator.update(model.opt.timestep)
        omni_controller.set_velocity_raw(vx, vy, omega)
        omni_controller.apply_control()
        mujoco.mj_step(model, data)
        viewer.sync()

        if not navigator.is_navigating:
            print("到达目标!")
            break
```

## 常见问题

### Q: 为什么机器人有轻微偏转?

A: 这是正常现象,可能原因:
- 物理仿真中的摩擦力不均匀
- 轮子制造公差
- 数值积分误差

偏转量通常很小(几厘米),实际应用中可接受。

### Q: 如何提高导航精度?

A: 可以调整PID参数:
```python
# 在 global_navigator.py 中修改
self.pid_x = PIDController(kp=2.0, ki=0.1, kd=0.05)
```

### Q: 如何实现平滑路径规划?

A: 使用路径插值:
```python
import numpy as np

def interpolate_path(start, end, num_steps):
    path = []
    for i in range(num_steps + 1):
        t = i / num_steps
        point = start + t * (end - start)
        path.append(point)
    return path
```

## 参考资料

- [MuJoCo官方文档](https://mujoco.readthedocs.io/)
- [LeKiwi项目](https://github.com/LeKiwi)
- [scipy.spatial.transform](https://docs.scipy.org/doc/scipy/reference/spatial.transform.html)

## 版本历史

- 2026-01-21: 初始版本,从Mujoco4Nano移植到RoboOS
