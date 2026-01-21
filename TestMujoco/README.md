# MuJoCo仿真导航 (MuJoCo Navigation Simulation)

## 概述

本目录包含MuJoCo物理仿真环境中三麦克纳姆轮底盘的导航控制代码，用于RoboOS机器人的仿真测试。

## 目录结构

```
TestMujoco/
├── controller/                   # 控制器模块
│   ├── omni_controller.py       # 运动学控制器（三轮全向轮）
│   └── global_navigator.py      # 全局导航控制器（PID）
├── model/                       # MuJoCo模型文件
│   └── assets/
│       └── scene.xml            # 机器人场景模型
├── run_navigation_standalone.py # 独立导航脚本（无GUI模式）
├── video/                       # 录制的导航视频
└── README.md                    # 本文档
```

## 核心功能

### 1. 独立进程导航

`run_navigation_standalone.py` 是核心脚本，用于在独立进程中执行导航任务：

**特性：**
- ✅ 完全独立运行，避免OpenGL上下文冲突
- ✅ 支持位置记忆，连续导航保持连续性
- ✅ 自动录制视频（俯视视角）
- ✅ 固定相机坐标系，视频可对比

**使用方式：**
```bash
python3 run_navigation_standalone.py '{"location":"bedroom","x":0.0,"y":0.6,"z":0.0,"yaw":null,"timeout":30,"video_dir":"./video","start_position":[0.0,0.0,0.0],"start_yaw":0.0}'
```

**参数说明：**
- `location`: 位置名称（用于视频文件名）
- `x, y, z`: 目标坐标（米）
- `yaw`: 目标朝向（弧度），null表示不控制姿态
- `timeout`: 超时时间（秒）
- `video_dir`: 视频保存目录
- `start_position`: 起始位置 [x, y, z]
- `start_yaw`: 起始朝向（弧度）

### 2. 运动学控制器 (OmniWheelController)

基于LeKiwi官方实现的三轮全向轮运动学。

**轮子配置:**
- 120°间隔布局
- 左轮 (30°), 右轮 (150°), 后轮 (270°)

**主要方法:**
- `set_velocity_raw(vx, vy, omega)` - 原始速度控制
- `apply_control()` - 应用控制到MuJoCo执行器
- `get_robot_position()` - 获取机器人位置

### 3. 全局导航控制器 (GlobalNavigator)

使用PID控制器实现精确的点到点移动。

**PID参数:**
- 位置控制: kp=1.5, ki=0.05, kd=0.05
- 姿态控制: kp=3.0, ki=0.02, kd=0.1

**主要方法:**
- `set_target(x, y, z, yaw)` - 设置目标
- `update(dt)` - 更新导航
- `is_target_reached()` - 检查是否到达

**分阶段控制策略:**
1. 阶段1: 先移动到目标位置（不控制姿态）
2. 阶段2: 位置到达后，再旋转到目标姿态

## 技术细节

### 坐标系

**世界坐标系（固定）:**
- x轴: 机器人初始前方
- y轴: 机器人初始左侧
- z轴: 垂直向上

**机器人坐标系（随机器人移动）:**
- x轴: 机器人当前正前方
- y轴: 机器人当前左侧
- z轴: 垂直向上

### 精度指标

- 位置容差: **5cm**
- 角度容差: **3度**
- 速度限制: 0.8 m/s (位置), 2.0 rad/s (姿态)

### 视频录制

- **相机视角**: 俯视（elevation=89°）
- **相机朝向**: 固定看向原点 (0, 0, 0)
- **视频格式**: MP4 (H.264编码)
- **帧率**: 30 FPS
- **分辨率**: 640x480

### 位置记忆

系统支持位置记忆功能，确保连续导航的连续性：

```python
# 第一次导航: (0, 0) → (0.5, 0)
# 第二次导航: (0.5, 0) → (0, 0.5)  ← 从第一次的终点开始
```

通过`start_position`参数传递起始位置给独立脚本。

## 与RoboOS集成

该模块已集成到RoboOS系统中，通过`mujoco_base.py`模块调用：

**可用工具:**
1. `navigate_to_target(target)` - 导航到指定位置
2. `move_base_test(test_mode)` - 测试底盘移动

**支持的位置名称:**
- 中文: 卧室, 客厅, 入口, 厨房, 厕所, 卫生间
- 英文: bedroom, livingRoom, entrance, kitchen, bathroom

**示例:**
```python
navigate_to_target(target="卧室")
navigate_to_target(target="bathroom")
```

## 依赖安装

```bash
pip install mujoco numpy scipy pillow
```

MuJoCo版本: >= 3.0.0

## 常见问题

### Q: 为什么使用独立进程？

A: MuJoCo的OpenGL上下文在Python进程级别缓存，多次调用会导致XIO错误。独立进程确保每次导航都有干净的OpenGL上下文。

### Q: 如何调整导航精度？

A: 修改`global_navigator.py`中的PID参数：
```python
self.pid_x = PIDController(kp=2.0, ki=0.1, kd=0.05)  # 增大响应速度
self.position_tolerance = 0.03  # 减小容差到3cm
```

### Q: 视频文件保存在哪里？

A: 默认保存在`/home/dora/RoboOs/RoboOS/TestMujoco/video/`目录，文件名格式：
- 成功: `navigate_{location}_{timestamp}.mp4`
- 超时: `navigate_{location}_timeout_{timestamp}.mp4`

### Q: 如何提高导航成功率？

A:
1. 减小单次导航距离（分段导航）
2. 增大超时时间
3. 调整PID参数
4. 检查目标位置是否在可达范围内

## 参考资料

- [MuJoCo官方文档](https://mujoco.readthedocs.io/)
- [RoboOS文档](../README.md)
- [机器人模块文档](../slaver/demo_robot_local/README_MODULES.md)

## 版本历史

- **2026-01-21**: 从Mujoco4Nano移植到RoboOS
  - 实现独立进程导航
  - 添加位置记忆功能
  - 修复OpenGL上下文冲突问题
  - 集成到RoboOS MCP工具链
