# 3全向轮底盘控制模块

## 概述

基于 lerobot lekiwi 设计的3全向轮底盘控制器，使用 Feetech STS3215 舵机驱动。参考 lerobot 实现了精确的运动学模型和速度控制。

## 目录结构

```
RealBase/
├── motor_controller.py      # 底盘控制器主模块
├── test_motor.py            # 统一的测试程序
├── requirements.txt         # Python依赖包列表
├── README.md                # 本文档
└── motors/                  # 电机驱动模块(已包含)
    ├── __init__.py
    ├── motors_bus.py        # 电机总线抽象层
    ├── calibration_gui.py   # 校准工具
    ├── feetech/             # Feetech舵机驱动
    │   ├── __init__.py
    │   ├── feetech.py       # Feetech电机总线实现
    │   └── tables.py        # 控制表和参数
    └── utils/               # 工具函数
        ├── __init__.py
        ├── encoding_utils.py
        └── utils.py
```

## 快速开始

### 1. 安装依赖

```bash
cd /home/dora/RoboOs/LekiwiTest/RealBase
pip install -r requirements.txt
```

### 2. 最简单的使用示例

```python
from motor_controller import OmniWheelController

# 创建底盘控制器
base = OmniWheelController(port="/dev/ttyACM0")

# 连接
if base.connect():
    # 向前运动 0.2 m/s
    base.set_velocity(linear_speed=0.2, vx=1, vy=0, omega=0)

    import time
    time.sleep(2)

    # 停止
    base.stop()
    base.disconnect()
```

### 3. 运行测试程序

```bash
python3 test_motor.py
```

提供交互式菜单，可以测试:
- 前进/后退
- 左移/右移
- 斜向运动
- 原地旋转
- 组合运动
- 单轮控制

## 主要功能

### 1. 运动学控制（推荐）

使用速度向量控制底盘整体运动，基于逆运动学矩阵计算。

**函数:**
```python
set_velocity(linear_speed, vx, vy, omega)
set_velocity_raw(vx, vy, omega)
```

**参数:**
- `linear_speed`: 速度大小 (m/s)
- `vx`: x方向分量 (归一化, -1到1)
- `vy`: y方向分量 (归一化, -1到1)
- `omega`: 旋转角速度 (rad/s, 正值逆时针)

**示例:**
```python
# 向前 0.2 m/s
base.set_velocity(linear_speed=0.2, vx=1, vy=0, omega=0)

# 向左横移 0.2 m/s
base.set_velocity(linear_speed=0.2, vx=0, vy=1, omega=0)

# 原地旋转 0.5 rad/s
base.set_velocity(linear_speed=0, vx=0, vy=0, omega=0.5)

# 前进同时旋转
base.set_velocity(linear_speed=0.2, vx=1, vy=0, omega=0.5)

# 直接设置速度(不归一化)
base.set_velocity_raw(vx=0.1, vy=0.1, omega=0.5)
```

### 2. 单轮控制

控制单个轮子的转动方向和速度。

**函数:**
```python
control_wheel(wheel_id, direction, speed)
```

**参数:**
- `wheel_id`: 电机ID (使用 `base.WHEEL_IDS[0/1/2]` 获取)
- `direction`: 转动方向 (1=正转, -1=反转)
- `speed`: 转动速度 (0-100, 0表示停止)

**示例:**
```python
# 轮子1正转,速度50%
base.control_wheel(wheel_id=base.WHEEL_IDS[0], direction=1, speed=50)

# 轮子2反转,速度30%
base.control_wheel(wheel_id=base.WHEEL_IDS[1], direction=-1, speed=30)

# 停止轮子1
base.stop_wheel(base.WHEEL_IDS[0])

# 停止所有轮子
base.stop()
```

### 3. 状态查询

**函数:**
```python
# 获取轮子角速度 (rad/s)
get_wheel_velocities()

# 将轮子速度转换为机器人速度
wheel_velocities_to_body_velocity(wheel_velocities)

# 获取单个轮子速度信息
get_wheel_speed(wheel_id)

# 获取所有轮子速度信息
get_all_speeds()
```

**示例:**
```python
# 查询轮子角速度 (rad/s)
wheel_vels = base.get_wheel_velocities()
print(f"轮子角速度: {wheel_vels} rad/s")

# 反推机器人速度
body_vel = base.wheel_velocities_to_body_velocity(wheel_vels)
print(f"机器人速度: vx={body_vel['vx']:.2f}, vy={body_vel['vy']:.2f}, omega={body_vel['omega']:.2f}")

# 查询轮子1的速度
result = base.get_wheel_speed(base.WHEEL_IDS[0])
print(f"速度: {result['speed']}%, 方向: {result['direction_str']}")
```

## 技术细节

### 运动学模型

参考 lerobot lekiwi 实现:

1. **轮子布置角度**: `[240°, 0°, 120°] - 90°` 偏移
2. **运动学矩阵**:
   ```
   M = [[cos(θ₁), sin(θ₁), r],
        [cos(θ₂), sin(θ₂), r],
        [cos(θ₃), sin(θ₃), r]]
   ```
   其中 θ 为轮子角度，r 为机器人半径

3. **速度转换**:
   - 机器人速度 → 轮子线速度: `v_wheel = M @ v_body`
   - 轮子线速度 → 轮子角速度: `ω = v / r_wheel`

### 速度控制

参考 lerobot 的精确速度转换:

1. **单位转换**: rad/s → deg/s → raw ticks
2. **转换公式**:
   - `steps_per_deg = 4096.0 / 360.0`
   - `raw = degps * steps_per_deg`

3. **速度缩放**:
   - 如果任一轮子超过 `max_raw` (默认3000)
   - 按比例缩放所有轮子速度
   - 保证运动方向不变

### 配置参数

**类常量** (可在 `motor_controller.py:25-29` 修改):

```python
class OmniWheelController:
    # 电机ID配置
    WHEEL_IDS = [13, 14, 15]

    # 尺寸参数
    WHEEL_RADIUS = 0.05      # 轮子半径 (米)
    BASE_RADIUS = 0.125      # 从机器人中心到轮子的距离 (米)
    MAX_RAW_VELOCITY = 3000  # 最大原始速度值 (ticks)
    STEPS_PER_DEG = 4096.0 / 360.0  # 每度的步数
```

**初始化参数**:

```python
OmniWheelController(
    port="/dev/ttyACM0",           # 串口端口
    wheel_radius=0.05,             # 轮子半径(米)
    robot_radius=0.125,            # 机器人半径(米)
    max_raw=3000                   # 最大原始速度值
)
```

## 硬件配置

### 电机布置

3全向轮底盘的轮子布置（参考 lerobot）:
- 轮子1 (wheel_1): 左后方
- 轮子2 (wheel_2): 前方
- 轮子3 (wheel_3): 右后方

### 电机参数

- 型号: Feetech STS3215
- 通信协议: SCServo
- 控制模式: 速度模式
- 编码器分辨率: 4096 steps/圈

### 修改电机ID

**方法1: 修改源码** (推荐)

编辑 `motor_controller.py` 第23行:

```python
WHEEL_IDS = [1, 2, 3]  # 改为你的电机ID
```

**方法2: 运行时修改**

```python
from motor_controller import OmniWheelController

# 修改电机ID
OmniWheelController.WHEEL_IDS = [1, 2, 3]

# 创建控制器
base = OmniWheelController(port="/dev/ttyACM0")
```

## API参考

### OmniWheelController类

#### 初始化
```python
OmniWheelController(port, wheel_radius, robot_radius, max_raw)
```
- `port`: 串口端口 (默认 "/dev/ttyACM0")
- `wheel_radius`: 轮子半径(米), 默认0.05
- `robot_radius`: 机器人半径(米), 默认0.125
- `max_raw`: 最大原始速度值, 默认3000

#### 连接控制
```python
connect() -> bool                      # 连接底盘电机
disconnect()                           # 断开连接
```

#### 运动控制
```python
set_velocity(linear_speed, vx, vy, omega) -> bool      # 运动学控制(推荐)
set_velocity_raw(vx, vy, omega) -> bool                 # 直接速度控制
stop() -> bool                                           # 停止所有轮子
```

#### 单轮控制
```python
control_wheel(wheel_id, direction, speed) -> dict       # 控制单个轮子
stop_wheel(wheel_id) -> dict                             # 停止指定轮子
```

#### 状态查询
```python
get_wheel_velocities() -> np.ndarray                     # 获取轮子角速度(rad/s)
wheel_velocities_to_body_velocity(wheel_velocities) -> dict  # 轮子速度→机器人速度
get_wheel_speed(wheel_id) -> dict                        # 获取单个轮子速度
get_all_speeds() -> dict                                 # 获取所有轮子速度
```

#### 速度转换（静态方法）
```python
_degps_to_raw(degps: float) -> int                       # 度/秒 → 原始值
_raw_to_degps(raw_speed: int) -> float                   # 原始值 → 度/秒
```

## 依赖项

- numpy - 数值计算
- pyserial - 串口通信
- scservo-sdk - Feetech舵机SDK
- draccus - 配置文件解析
- deepdiff - 数据对比
- tqdm - 进度条

安装:
```bash
pip install -r requirements.txt
```

## 注意事项

1. **端口配置**: 确保串口端口正确
   ```bash
   ls /dev/tty*
   ```
   常见串口: `/dev/ttyACM0`, `/dev/ttyACM1`, `/dev/ttyUSB0`

2. **电机ID**: 确保电机ID配置正确

3. **安全**: 使用前确保轮子悬空或放在可自由移动的平面上

4. **异常处理**: 建议使用 try-except 捕获异常
   ```python
   try:
       base.connect()
       # 控制代码
   except KeyboardInterrupt:
       base.stop()
   finally:
       base.disconnect()
   ```

## 故障排除

### 连接失败
- 检查串口端口是否正确
- 检查USB线缆是否连接
- 检查电机电源是否开启

### 电机不响应
- 检查电机ID是否正确
- 检查电机是否已使能扭矩
- 尝试重新连接

### 运动不正常
- 检查轮子方向定义是否符合实际
- 调整 `robot_radius` 参数
- 检查轮子半径参数 `wheel_radius`

## 参考资料

- [lerobot lekiwi 实现](/home/dora/lerobot/src/lerobot/robots/lekiwi/lekiwi.py)
- [Feetech STS3215 手册](https://www.feetechrc.com/)
