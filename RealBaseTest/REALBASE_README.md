# 麦轮底盘远程控制模块使用指南

## 概述

本模块实现了通过 Socket 远程控制三全向轮底盘的功能，参考 `grasp.py` 的设计模式。

**架构设计：**
- `real_base.py`: RoboOS 端模块，发送 Socket 指令
- `base_server.py`: 开发板端服务器，接收指令并控制底盘
- 通信协议: TCP Socket (端口 9998)

## 文件位置

### RoboOS 端
```
/home/dora/RoboOs/RoboOS/slaver/demo_robot_local/module/real_base.py
```

### 开发板端
```
/tmp/base_server.py (本地源文件，部署时复制到开发板)
/home/HwHiAiUser/base_server.py (部署后在开发板上)
/home/HwHiAiUser/RealBase/ (完整的项目目录)
```

### 部署脚本
```
/home/dora/RoboOs/RoboOS/deploy_base_server.sh
```

## 快速开始

### 步骤 1: 部署服务器到开发板

**方法 A: 使用部署脚本（推荐）**
```bash
cd /home/dora/RoboOs/RoboOS
bash deploy_base_server.sh
```

**方法 B: 手动部署**
```bash
# 1. 复制 RealBase 目录到开发板
scp -r /home/dora/RoboOs/LekiwiTest/RealBase HwHiAiUser@192.168.0.155:/home/HwHiAiUser/

# 2. 复制服务器程序到开发板
scp /tmp/base_server.py HwHiAiUser@192.168.0.155:/home/HwHiAiUser/base_server.py

# 3. SSH 登录到开发板
ssh HwHiAiUser@192.168.0.155

# 4. 启动服务器
cd /home/HwHiAiUser
python3 base_server.py

# 或在后台运行
nohup python3 base_server.py > base_server.log 2>&1 &
```

### 步骤 2: 验证服务器运行

在开发板上查看日志：
```bash
tail -f base_server.log
```

应该看到类似输出：
```
============================================================
麦轮底盘控制服务器
============================================================

[初始化] 正在连接底盘...
✓ 三全向轮底盘连接成功
[初始化] 底盘连接成功

[服务器] 启动成功，监听 0.0.0.0:9998
[服务器] 等待客户端连接...
```

### 步骤 3: 启动 RoboOS 服务

```bash
cd /home/dora/RoboOs/RoboOS
conda activate RoboOS
python slaver/run.py
```

启动后会看到：
```
[real_base.py] 麦轮底盘控制模块已注册
[skill.py] ✓ 所有模块注册完成
```

## 可用功能

### 1. move_base - 方向控制移动

支持10种预设方向：

| 方向关键字 | 中文 | 说明 |
|-----------|------|------|
| forward | 前 | 向前移动 |
| backward | 后 | 向后移动 |
| left | 左 | 向左横移 |
| right | 右 | 向右横移 |
| forward_left | 左前 | 向左前方斜向移动 |
| forward_right | 右前 | 向右前方斜向移动 |
| backward_left | 左后 | 向左后方斜向移动 |
| backward_right | 右后 | 向右后方斜向移动 |
| rotate_cw | 顺时针 | 原地顺时针旋转 |
| rotate_ccw | 逆时针 | 原地逆时针旋转 |

**参数：**
- `direction`: 方向（字符串）
- `speed`: 速度（m/s，默认 0.2，建议范围 0.1-0.5）
- `duration`: 运行时间（秒，默认 2.0）

**LLM 调用示例：**
```python
# 向前移动2秒
move_base(direction="forward", speed=0.2, duration=2.0)

# 向左横移1.5秒
move_base(direction="left", speed=0.15, duration=1.5)

# 逆时针旋转3秒
move_base(direction="rotate_ccw", speed=0.5, duration=3.0)
```

### 2. move_base_raw - 原始速度分量控制

直接设置速度分量，提供更精确的控制。

**参数：**
- `vx`: X方向速度（m/s，正值向前，负值向后）
- `vy`: Y方向速度（m/s，正值向左，负值向右）
- `omega`: 旋转角速度（rad/s，默认0）
- `duration`: 运行时间（秒，默认 2.0）

**LLM 调用示例：**
```python
# 向前移动
move_base_raw(vx=0.2, vy=0.0, duration=2.0)

# 向左横移
move_base_raw(vx=0.0, vy=0.15, duration=1.5)

# 向左前方斜向移动
move_base_raw(vx=0.1, vy=0.1, duration=3.0)

# 原地逆时针旋转
move_base_raw(vx=0.0, vy=0.0, omega=0.5, duration=2.0)
```

### 3. stop_base - 立即停止

立即停止所有底盘轮子的运动。

**LLM 调用示例：**
```python
stop_base()
```

### 4. check_base_status - 检查状态

检查开发板连接状态和底盘模块配置。

**LLM 调用示例：**
```python
check_base_status()
```

## 通信协议

### 指令格式

所有指令以 `BASE:` 前缀开头：

```
BASE:MOVE:<direction>:<speed>:<duration>\n
BASE:MOVE_RAW:<vx>:<vy>:<omega>:<duration>\n
BASE:STOP\n
```

**示例：**
```
BASE:MOVE:forward:0.2:2.0\n
BASE:MOVE:左:0.15:1.5\n
BASE:MOVE_RAW:0.1:0.1:0.0:2.0\n
BASE:STOP\n
```

### 响应格式

```
SUCCESS:<消息>
FAILED:<错误信息>
```

**示例：**
```
SUCCESS:底盘已向forward方向移动2.0秒，速度0.2m/s
FAILED:底盘未连接
FAILED:无效的方向: xxx
```

## 配置说明

### RoboOS 端配置

文件: `/home/dora/RoboOs/RoboOS/slaver/demo_robot_local/module/real_base.py`

```python
BOARD_CONFIG = {
    "connection_type": "socket",  # 连接类型
    "socket_host": "192.168.0.155",  # 开发板IP地址
    "socket_port": 9998,  # Socket端口
    "socket_timeout": 10,  # 连接超时时间（秒）
}
```

### 开发板端配置

文件: `/home/HwHiAiUser/base_server.py`

```python
HOST = '0.0.0.0'  # 监听所有网络接口
PORT = 9998       # 端口号（不要与grasp的9999冲突）
```

### 底盘硬件配置

文件: `/home/HwHiAiUser/RealBase/motor_controller.py`

```python
WHEEL_IDS = [13, 14, 15]  # 电机ID配置
WHEEL_RADIUS = 0.05        # 轮子半径 (米)
BASE_RADIUS = 0.125        # 机器人半径 (米)
```

## LLM 自然语言理解

LLM 可以解析各种自然语言指令并转换为相应的函数调用：

### 简单指令
- "向前移动" → `move_base(direction="forward", speed=0.2, duration=2.0)`
- "向左移动" → `move_base(direction="left", speed=0.15, duration=2.0)`
- "后退" → `move_base(direction="backward", speed=0.2, duration=2.0)`

### 带参数的指令
- "以0.3m/s速度向右移动3秒" → `move_base(direction="right", speed=0.3, duration=3.0)`
- "向前移动5秒" → `move_base(direction="forward", speed=0.2, duration=5.0)`

### 旋转指令
- "向左转" / "逆时针旋转" → `move_base(direction="rotate_ccw", speed=0.5, duration=2.0)`
- "顺时针旋转" → `move_base(direction="rotate_cw", speed=0.5, duration=2.0)`

### 斜向移动
- "向右前方移动" → `move_base(direction="forward_right", speed=0.2, duration=2.0)`
- "向左后方移动" → `move_base(direction="backward_left", speed=0.2, duration=2.0)`

### 组合指令
- "先向前移动2秒，然后向左转" → 依次调用两个函数
- "停止" → `stop_base()`

## 故障排除

### 问题 1: 无法连接到开发板

**错误信息:** `无法连接到开发板，请确认开发板上的底盘服务器程序正在运行`

**解决方案:**
1. 检查开发板 IP 地址是否正确
2. 确认开发板上的服务器正在运行：
   ```bash
   ssh HwHiAiUser@192.168.0.155
   ps aux | grep base_server
   ```
3. 如果服务器未运行，启动它：
   ```bash
   cd /home/HwHiAiUser
   python3 base_server.py
   ```

### 问题 2: 底盘未连接

**错误信息:** `FAILED:底盘未连接`

**解决方案:**
1. 检查串口连接：
   ```bash
   ls /dev/tty*
   ```
   确认 `/dev/ttyACM0` 或其他串口设备存在

2. 检查电机电源是否开启

3. 检查电机ID配置是否正确

### 问题 3: 端口冲突

**错误信息:** `Address already in use`

**解决方案:**
1. 检查端口占用：
   ```bash
   netstat -tlnp | grep 9998
   ```
2. 修改配置文件中的端口号

### 问题 4: 移动不正常

**解决方案:**
1. 检查 RealBase 目录是否完整复制到开发板
2. 检查电机ID配置是否正确
3. 在开发板上直接测试：
   ```bash
   cd /home/HwHiAiUser/RealBase
   python3 test_motor.py
   ```

## 调试技巧

### 查看开发板服务器日志

```bash
ssh HwHiAiUser@192.168.0.155
tail -f /home/HwHiAiUser/base_server.log
```

### 测试 Socket 连接

在 RoboOS 端：
```python
import socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(2)
result = sock.connect_ex(("192.168.0.155", 9998))
print("可连接" if result == 0 else "无法连接")
sock.close()
```

### 使用 check_base_status

通过 Web UI 或其他方式调用 `check_base_status()` 检查模块状态。

## 注意事项

1. **安全性**: 
   - 建议测试时将机器人悬空或放在开阔地
   - 速度建议范围：0.1 - 0.5 m/s
   - 确保有足够的运动空间

2. **网络**: 
   - 确保 RoboOS 和开发板在同一网络
   - 检查防火墙设置

3. **端口**: 
   - 底盘服务器使用 9998 端口
   - 抓取服务器使用 9999 端口
   - 不要混淆这两个端口

4. **资源管理**: 
   - 服务器关闭时会自动断开底盘连接
   - 使用 Ctrl+C 停止服务器会安全地关闭底盘

## 与 grasp.py 的对比

| 特性 | grasp.py | real_base.py |
|------|----------|--------------|
| 功能 | 抓取物体 | 底盘移动 |
| 服务器端口 | 9999 | 9998 |
| 指令前缀 | 无 | BASE: |
| 指令格式 | GRASP:颜色 | MOVE:方向:速度:时间 |
| 响应格式 | SUCCESS/FAILED | SUCCESS/FAILED |
| 超时时间 | 60秒 | 10秒 |

## 总结

本模块提供了完整的麦轮底盘远程控制功能，支持：

- ✅ 10种预设方向控制
- ✅ 原始速度分量控制
- ✅ 立即停止功能
- ✅ 状态检查功能
- ✅ LLM 自然语言解析
- ✅ Socket 远程通信
- ✅ 完善的错误处理

通过参考 grasp.py 的设计，实现了统一的通信模式和代码风格，便于维护和扩展。
