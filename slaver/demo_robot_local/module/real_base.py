"""
麦轮底盘控制模块 (Mecanum Wheel Base Control Module) - Socket通信版本

负责通过嵌入式开发板控制三全向轮底盘的运动。

通信方式：
    - 通过Socket TCP连接发送移动指令到开发板
    - 开发板上运行服务器程序监听指令并控制底盘
    - 支持多种移动模式和参数配置

功能：
    - move_base: 按指定方向、速度和时间移动底盘
    - move_base_raw: 直接设置底盘速度分量
    - stop_base: 立即停止底盘
    - check_base_status: 检查底盘模块状态
"""

import sys
import socket
import time
from typing import Tuple, Dict


# 配置信息（根据实际情况修改）
BOARD_CONFIG = {
    "connection_type": "socket",  # 连接类型: "socket" 或 "serial"

    # Socket通信配置
    "socket_host": "192.168.0.155",  # 开发板IP地址
    "socket_port": 9998,  # Socket端口（与开发板服务器一致，注意不要和grasp的9999冲突）
    "socket_timeout": 10,  # 连接超时时间（秒）

    # 串口通信配置（备选方案）
    "serial_port": "/dev/ttyUSB0",
    "serial_baudrate": 115200,
}


# 指令协议定义
COMMAND_PREFIX = "BASE:"  # 指令前缀

# 响应码定义
RESPONSE_CODES = {
    "SUCCESS": "执行成功",
    "FAILED": "执行失败",
}


def send_base_command(command: str) -> Tuple[bool, str]:
    """
    发送底盘控制指令到开发板

    Args:
        command: 控制指令字符串

    Returns:
        Tuple[成功标志, 结果消息]
    """
    config = BOARD_CONFIG

    if config["connection_type"] == "socket":
        return _send_via_socket(command, config)
    elif config["connection_type"] == "serial":
        return _send_via_serial(command, config)
    else:
        return False, f"不支持的连接类型: {config['connection_type']}"


def _send_via_socket(command: str, config: Dict) -> Tuple[bool, str]:
    """
    通过Socket发送底盘控制指令到开发板

    Args:
        command: 控制指令
        config: 配置字典

    Returns:
        Tuple[成功标志, 结果消息]
    """
    sock = None
    try:
        print(f"[real_base._send_via_socket] 连接到开发板: {config['socket_host']}:{config['socket_port']}", file=sys.stderr)

        # 创建Socket连接
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(config['socket_timeout'])

        # 连接到开发板
        sock.connect((config['socket_host'], config['socket_port']))
        print(f"[real_base._send_via_socket] 连接成功", file=sys.stderr)

        # 发送指令
        full_command = f"{COMMAND_PREFIX}{command}\n"
        print(f"[real_base._send_via_socket] 发送指令: {command}", file=sys.stderr)

        sock.sendall(full_command.encode('utf-8'))

        # 接收响应
        response_data = sock.recv(1024)
        response = response_data.decode('utf-8').strip()
        print(f"[real_base._send_via_socket] 收到响应: {response}", file=sys.stderr)

        # 解析响应
        if response.startswith("SUCCESS"):
            return True, response
        elif response.startswith("FAILED"):
            return False, response
        else:
            return True, response

    except socket.timeout:
        error_msg = f"Socket连接超时（{config['socket_timeout']}秒）"
        print(f"[real_base._send_via_socket] {error_msg}", file=sys.stderr)
        return False, error_msg

    except ConnectionRefusedError:
        error_msg = f"无法连接到开发板，请确认开发板上的底盘服务器程序正在运行（端口 {config['socket_port']}）"
        print(f"[real_base._send_via_socket] {error_msg}", file=sys.stderr)
        return False, error_msg

    except Exception as e:
        error_msg = f"Socket通信错误: {str(e)}"
        print(f"[real_base._send_via_socket] {error_msg}", file=sys.stderr)
        return False, error_msg

    finally:
        if sock:
            sock.close()
            print(f"[real_base._send_via_socket] 连接已关闭", file=sys.stderr)


def _send_via_serial(command: str, config: Dict) -> Tuple[bool, str]:
    """
    通过串口发送底盘控制指令到开发板

    Args:
        command: 控制指令
        config: 配置字典

    Returns:
        Tuple[成功标志, 结果消息]
    """
    try:
        import serial

        print(f"[real_base._send_via_serial] 打开串口: {config['serial_port']}", file=sys.stderr)

        # 打开串口
        ser = serial.Serial(
            port=config['serial_port'],
            baudrate=config['serial_baudrate'],
            timeout=10
        )

        # 等待串口就绪
        time.sleep(0.1)

        # 发送指令
        full_command = f"{COMMAND_PREFIX}{command}\n"
        print(f"[real_base._send_via_serial] 发送指令: {command}", file=sys.stderr)

        ser.write(full_command.encode('utf-8'))

        # 读取响应
        response = ser.readline().decode().strip()
        print(f"[real_base._send_via_serial] 收到响应: {response}", file=sys.stderr)

        ser.close()

        if response.startswith("SUCCESS"):
            return True, response
        elif response.startswith("FAILED"):
            return False, response
        else:
            return True, response

    except ImportError:
        error_msg = "缺少pyserial库，请安装: pip install pyserial"
        print(f"[real_base._send_via_serial] {error_msg}", file=sys.stderr)
        return False, error_msg

    except Exception as e:
        error_msg = f"串口通信错误: {str(e)}"
        print(f"[real_base._send_via_serial] {error_msg}", file=sys.stderr)
        return False, error_msg


def register_tools(mcp):
    """
    注册麦轮底盘相关的所有工具函数到 MCP 服务器

    Args:
        mcp: FastMCP 服务器实例
    """

    @mcp.tool()
    async def move_base(direction: str, speed: float = 0.2, duration: float = 2.0) -> Tuple[str, Dict]:
        """Control omnidirectional robot base movement (麦轮底盘移动控制).

        控制三全向轮底盘按指定方向移动。通过Socket发送指令到开发板，开发板执行实际的运动控制。

        支持的方向：前、后、左、右、左前、右前、左后、右后、原地旋转

        Args:
            direction: Movement direction. Available directions:
                      - "forward" or "前": 向前移动
                      - "backward" or "后": 向后移动
                      - "left" or "左": 向左横移
                      - "right" or "右": 向右横移
                      - "forward_left" or "左前": 向左前方斜向移动
                      - "forward_right" or "右前": 向右前方斜向移动
                      - "backward_left" or "左后": 向左后方斜向移动
                      - "backward_right" or "右后": 向右后方斜向移动
                      - "rotate_cw" or "顺时针": 原地顺时针旋转
                      - "rotate_ccw" or "逆时针": 原地逆时针旋转
            speed: Movement speed in m/s (米/秒).
                   典型范围：0.1 到 0.5 m/s，建议默认 0.2 m/s
            duration: Movement duration in seconds (秒).
                      运动持续时间，开发板会在这个时间后自动停止

        Returns:
            A tuple containing the result message and updated robot state.

        Examples:
            move_base(direction="forward", speed=0.2, duration=2.0)  # 向前移动2秒
            move_base(direction="left", speed=0.15, duration=1.5)   # 向左移动1.5秒
            move_base(direction="rotate_ccw", speed=0.3, duration=3.0)  # 逆时针旋转3秒

        Notes:
            - 指令发送到开发板后，开发板会执行运动并在duration时间后自动停止
            - 如果需要立即停止，使用 stop_base()
            - 旋转时 speed 参数表示角速度 (rad/s)
        """
        print(f"[real_base.move_base] 方向={direction}, 速度={speed}m/s, 时间={duration}s", file=sys.stderr)

        # 构建指令字符串
        # 格式: MOVE:<direction>:<speed>:<duration>
        command = f"MOVE:{direction}:{speed}:{duration}"

        # 发送指令到开发板
        success, result = send_base_command(command)

        # 构建返回结果
        if success:
            state_update = {
                "action": "move_base",
                "direction": direction,
                "speed": speed,
                "duration": duration,
                "success": True,
                "timestamp": time.time()
            }
            message = f"✅ 底盘正在向{direction}方向移动，速度{speed}m/s，持续时间{duration}秒"
            return message, state_update
        else:
            state_update = {
                "action": "move_base",
                "direction": direction,
                "speed": speed,
                "duration": duration,
                "success": False,
                "error": result
            }
            return f"❌ 底盘移动失败: {result}", state_update

    @mcp.tool()
    async def move_base_raw(vx: float, vy: float, omega: float = 0.0, duration: float = 2.0) -> Tuple[str, Dict]:
        """Control omnidirectional base with raw velocity components (原始速度分量控制底盘).

        直接设置底盘的速度分量，不进行方向归一化。通过Socket发送指令到开发板。

        与 move_base 不同，此函数直接使用速度分量，提供更精确的控制。

        Args:
            vx: X方向速度 (m/s)，正值向前，负值向后
            vy: Y方向速度 (m/s)，正值向左，负值向右
            omega: 旋转角速度 (rad/s)，正值逆时针，负值顺时针，默认0
            duration: 运动持续时间 (秒)，默认2.0秒

        Returns:
            A tuple containing the result message and updated robot state.

        Examples:
            move_base_raw(vx=0.2, vy=0.0, duration=2.0)  # 向前移动
            move_base_raw(vx=0.0, vy=0.15, duration=1.5)  # 向左横移
            move_base_raw(vx=0.1, vy=0.1, duration=3.0)  # 向左前方斜向移动
            move_base_raw(vx=0.0, vy=0.0, omega=0.5, duration=2.0)  # 原地逆时针旋转

        Notes:
            - 速度单位为 m/s，角速度单位为 rad/s
            - 运动结束后开发板会自动停止
            - 如果需要立即停止，使用 stop_base()
        """
        print(f"[real_base.move_base_raw] vx={vx}m/s, vy={vy}m/s, omega={omega}rad/s, 时间={duration}s", file=sys.stderr)

        # 构建指令字符串
        # 格式: MOVE_RAW:<vx>:<vy>:<omega>:<duration>
        command = f"MOVE_RAW:{vx}:{vy}:{omega}:{duration}"

        # 发送指令到开发板
        success, result = send_base_command(command)

        # 构建返回结果
        if success:
            state_update = {
                "action": "move_base_raw",
                "vx": vx,
                "vy": vy,
                "omega": omega,
                "duration": duration,
                "success": True,
                "timestamp": time.time()
            }
            message = f"✅ 底盘正在以 vx={vx}m/s, vy={vy}m/s, omega={omega}rad/s 移动，持续时间{duration}秒"
            return message, state_update
        else:
            state_update = {
                "action": "move_base_raw",
                "vx": vx,
                "vy": vy,
                "omega": omega,
                "duration": duration,
                "success": False,
                "error": result
            }
            return f"❌ 底盘移动失败: {result}", state_update

    @mcp.tool()
    async def stop_base() -> Tuple[str, Dict]:
        """Stop the omnidirectional robot base immediately (立即停止底盘).

        立即停止所有底盘轮子的运动。通过Socket发送停止指令到开发板。

        Returns:
            A tuple containing the result message and updated robot state.

        Examples:
            stop_base()  # 立即停止底盘

        Notes:
            - 用于紧急停止或正常停止底盘运动
            - 发送停止指令到开发板，开发板会立即停止所有轮子
        """
        print(f"[real_base.stop_base] 发送停止指令", file=sys.stderr)

        # 构建指令字符串
        command = "STOP"

        # 发送指令到开发板
        success, result = send_base_command(command)

        # 构建返回结果
        if success:
            state_update = {
                "action": "stop_base",
                "success": True,
                "timestamp": time.time()
            }
            return "✅ 底盘已停止", state_update
        else:
            state_update = {
                "action": "stop_base",
                "success": False,
                "error": result
            }
            return f"❌ 停止底盘失败: {result}", state_update

    @mcp.tool()
    async def check_base_status() -> Tuple[str, Dict]:
        """检查底盘模块状态 (Check base module status).

        检查开发板连接状态和底盘模块配置。

        Returns:
            A tuple containing the status message and current configuration.

        Examples:
            check_base_status()  # 检查底盘模块状态
        """
        config = BOARD_CONFIG

        print(f"[real_base.check_base_status] 检查模块状态", file=sys.stderr)

        status_info = f"麦轮底盘模块状态:\n"
        status_info += f"  通信方式: {config['connection_type']}\n"

        if config['connection_type'] == 'socket':
            status_info += f"  开发板地址: {config['socket_host']}:{config['socket_port']}\n"
            status_info += f"  连接超时: {config['socket_timeout']}秒\n"
        elif config['connection_type'] == 'serial':
            status_info += f"  串口设备: {config['serial_port']}\n"
            status_info += f"  波特率: {config['serial_baudrate']}\n"

        # 测试连接
        try:
            if config['connection_type'] == 'socket':
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex((config['socket_host'], config['socket_port']))
                sock.close()

                if result == 0:
                    status_info += "  连接状态: ✅ 可以连接到开发板"
                else:
                    status_info += "  连接状态: ❌ 无法连接到开发板服务器"

            elif config['connection_type'] == 'serial':
                import serial
                ser = serial.Serial(
                    port=config['serial_port'],
                    baudrate=config['serial_baudrate'],
                    timeout=1
                )
                ser.close()
                status_info += "  连接状态: ✅ 串口设备可用"

        except Exception as e:
            status_info += f"  连接状态: ❌ 检查失败: {str(e)}"

        print(f"[real_base.check_base_status] 状态检查完成", file=sys.stderr)

        state_update = {
            "connection_type": config['connection_type'],
            "config": config,
            "status": "checked"
        }

        return status_info, state_update

    print("[real_base.py] 麦轮底盘控制模块已注册", file=sys.stderr)


# ============================================================================
# 开发板服务器程序
# ============================================================================
"""
需要在开发板上运行的服务器程序（保存为 base_server.py）：

```python
#!/usr/bin/env python3
import socket
import sys
import time
from motor_controller import OmniWheelController

# 配置
HOST = '0.0.0.0'  # 监听所有网络接口
PORT = 9998       # 端口号（注意不要和grasp的9999冲突）

# 全局底盘控制器
base_controller = None

# 方向映射
DIRECTION_MAP = {
    "forward": (1, 0, 0),
    "前": (1, 0, 0),
    "backward": (-1, 0, 0),
    "后": (-1, 0, 0),
    "left": (0, 1, 0),
    "左": (0, 1, 0),
    "right": (0, -1, 0),
    "右": (0, -1, 0),
    "forward_left": (1, 1, 0),
    "左前": (1, 1, 0),
    "forward_right": (1, -1, 0),
    "右前": (1, -1, 0),
    "backward_left": (-1, 1, 0),
    "左后": (-1, 1, 0),
    "backward_right": (-1, -1, 0),
    "右后": (-1, -1, 0),
    "rotate_cw": (0, 0, -1),
    "顺时针": (0, 0, -1),
    "rotate_ccw": (0, 0, 1),
    "逆时针": (0, 0, 1),
}

def initialize_base():
    \"\"\"初始化底盘连接\"\"\"
    global base_controller
    if base_controller is None:
        base_controller = OmniWheelController()
        try:
            success = base_controller.connect()
            if success:
                print("✓ 三全向轮底盘连接成功")
            else:
                print("✗ 三全向轮底盘连接失败")
                base_controller = None
        except Exception as e:
            print(f"✗ 底盘初始化异常: {e}")
            base_controller = None

def execute_move(direction, speed, duration):
    \"\"\"执行移动指令\"\"\"
    try:
        if base_controller is None:
            initialize_base()

        if base_controller is None or base_controller.base_bus is None:
            return f"FAILED:底盘未连接"

        # 检查方向是否有效
        if direction not in DIRECTION_MAP:
            return f"FAILED:无效的方向: {direction}"

        # 获取方向分量
        vx, vy, omega_direction = DIRECTION_MAP[direction]

        # 对于旋转，使用 speed 作为角速度
        if omega_direction != 0:
            omega = speed * omega_direction
            linear_speed = 0.0
            vx, vy = 0, 0
        else:
            omega = 0.0
            linear_speed = speed

        # 设置速度
        success = base_controller.set_velocity(
            linear_speed=linear_speed,
            vx=vx,
            vy=vy,
            omega=omega
        )

        if not success:
            return f"FAILED:设置底盘速度失败"

        # 等待指定时间
        time.sleep(duration)

        # 停止底盘
        base_controller.stop()

        return f"SUCCESS:底盘已向{direction}方向移动{duration}秒"

    except Exception as e:
        return f"FAILED:移动失败: {str(e)}"

def execute_move_raw(vx, vy, omega, duration):
    \"\"\"执行原始速度移动指令\"\"\"
    try:
        if base_controller is None:
            initialize_base()

        if base_controller is None or base_controller.base_bus is None:
            return f"FAILED:底盘未连接"

        # 设置速度
        success = base_controller.set_velocity_raw(vx=float(vx), vy=float(vy), omega=float(omega))

        if not success:
            return f"FAILED:设置底盘速度失败"

        # 等待指定时间
        time.sleep(duration)

        # 停止底盘
        base_controller.stop()

        return f"SUCCESS:底盘已按指定速度移动{duration}秒"

    except Exception as e:
        return f"FAILED:移动失败: {str(e)}"

def execute_stop():
    \"\"\"执行停止指令\"\"\"
    try:
        if base_controller is None:
            initialize_base()

        if base_controller is None or base_controller.base_bus is None:
            return f"FAILED:底盘未连接"

        success = base_controller.stop()

        if success:
            return f"SUCCESS:底盘已停止"
        else:
            return f"FAILED:停止底盘失败"

    except Exception as e:
        return f"FAILED:停止失败: {str(e)}"

def handle_client(client_socket):
    \"\"\"处理客户端请求\"\"\"
    try:
        # 接收指令
        data = client_socket.recv(1024).decode('utf-8').strip()
        print(f\"收到指令: {data}\")

        # 解析指令
        if data.startswith('BASE:'):
            command = data[5:]  # 移除 "BASE:" 前缀

            if command.startswith('MOVE:'):
                # 格式: MOVE:<direction>:<speed>:<duration>
                parts = command.split(':')
                if len(parts) == 4:
                    direction = parts[1]
                    speed = float(parts[2])
                    duration = float(parts[3])
                    response = execute_move(direction, speed, duration)
                else:
                    response = "FAILED:指令格式错误"

            elif command.startswith('MOVE_RAW:'):
                # 格式: MOVE_RAW:<vx>:<vy>:<omega>:<duration>
                parts = command.split(':')
                if len(parts) == 5:
                    vx = float(parts[1])
                    vy = float(parts[2])
                    omega = float(parts[3])
                    duration = float(parts[4])
                    response = execute_move_raw(vx, vy, omega, duration)
                else:
                    response = "FAILED:指令格式错误"

            elif command.startswith('STOP'):
                response = execute_stop()

            else:
                response = "FAILED:未知指令"

            client_socket.sendall(response.encode('utf-8'))
        else:
            response = "FAILED:指令格式错误"
            client_socket.sendall(response.encode('utf-8'))

    except Exception as e:
        print(f\"处理错误: {e}\")
        client_socket.sendall(f\"FAILED:{str(e)}\".encode('utf-8'))
    finally:
        client_socket.close()

def main():
    \"\"\"主函数\"\"\"
    global base_controller

    # 初始化底盘
    initialize_base()

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server_socket.bind((HOST, PORT))
        server_socket.listen(5)
        print(f\"底盘服务器启动，监听 {HOST}:{PORT}\")

        while True:
            client_socket, addr = server_socket.accept()
            print(f\"客户端连接: {addr}\")
            handle_client(client_socket)

    except KeyboardInterrupt:
        print(\"\\n服务器停止\")
    finally:
        if base_controller:
            base_controller.disconnect()
        server_socket.close()

if __name__ == \"__main__\":
    main()
```

在开发板上启动服务器：

```bash
# 1. 将服务器程序复制到开发板
scp base_server.py HwHiAiUser@192.168.0.155:/home/HwHiAiUser/

# 2. 确保开发板上有 motor_controller.py
# 将 RealBase 目录复制到开发板
scp -r /home/dora/RoboOs/LekiwiTest/RealBase HwHiAiUser@192.168.0.155:/home/HwHiAiUser/

# 3. SSH登录到开发板
ssh HwHiAiUser@192.168.0.155

# 4. 启动服务器
cd /home/HwHiAiUser
python3 base_server.py

# 或者在后台运行
nohup python3 base_server.py > base_server.log 2>&1 &
```

通信协议：

发送指令格式：
```
BASE:MOVE:forward:0.2:2.0\\n
BASE:MOVE:左:0.15:1.5\\n
BASE:MOVE_RAW:0.1:0.1:0.0:2.0\\n
BASE:STOP\\n
```

响应格式：
```
SUCCESS:底盘已向forward方向移动2.0秒
FAILED:底盘未连接
```
"""
