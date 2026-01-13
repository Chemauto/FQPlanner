"""
抓取控制模块 (Grasp Control Module) - Socket通信版本

负责通过嵌入式开发板执行物体抓取功能。

通信方式：
    - 通过Socket TCP连接发送抓取指令到开发板
    - 开发板上运行服务器程序监听指令并执行抓取
    - 支持实时查看摄像头画面（在开发板上显示）

功能：
    - grasp_object: 抓取指定颜色的物体
    - check_grasp_status: 检查抓取模块状态
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
    "socket_port": 9999,  # Socket端口（与开发板服务器一致）
    "socket_timeout": 5,  # 连接超时时间（秒）

    # 串口通信配置（备选方案）
    "serial_port": "/dev/ttyUSB0",
    "serial_baudrate": 115200,
}


# 指令协议定义
COMMAND_BYTE = 0xAA  # 抓取指令字节

# 响应码定义
RESPONSE_CODES = {
    0x00: "执行成功",
    0x01: "指令格式错误",
    0x02: "颜色参数错误",
    0x03: "摄像头打开失败",
    0x04: "抓取失败",
    0x05: "未知错误",
}


def send_grasp_command(color: str) -> Tuple[bool, str]:
    """
    发送抓取指令到开发板

    Args:
        color: 目标物体颜色（如 "红色", "red"）

    Returns:
        Tuple[成功标志, 结果消息]
    """
    config = BOARD_CONFIG

    if config["connection_type"] == "socket":
        return _send_via_socket(color, config)
    elif config["connection_type"] == "serial":
        return _send_via_serial(color, config)
    else:
        return False, f"不支持的连接类型: {config['connection_type']}"


def _send_via_socket(color: str, config: Dict) -> Tuple[bool, str]:
    """
    通过Socket发送抓取指令到开发板

    Args:
        color: 目标物体颜色
        config: 配置字典

    Returns:
        Tuple[成功标志, 结果消息]
    """
    sock = None
    try:
        print(f"[grasp._send_via_socket] 连接到开发板: {config['socket_host']}:{config['socket_port']}", file=sys.stderr)

        # 创建Socket连接
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(config['socket_timeout'])

        # 连接到开发板
        sock.connect((config['socket_host'], config['socket_port']))
        print(f"[grasp._send_via_socket] 连接成功", file=sys.stderr)

        # 发送抓取指令（0xAA字节）
        command = bytes([COMMAND_BYTE])
        print(f"[grasp._send_via_socket] 发送指令: 0x{command.hex().upper()}", file=sys.stderr)

        # 发送指令
        sock.sendall(command)

        # 接收响应
        response_data = sock.recv(1024)
        response = response_data.decode('utf-8').strip()
        print(f"[grasp._send_via_socket] 收到响应: {response}", file=sys.stderr)

        # 解析响应
        if response.startswith("SUCCESS"):
            return True, f"✅ 成功执行抓取\n{response}"
        elif response.startswith("FAILED"):
            error_code = response.split(":")[1] if ":" in response else "未知错误"
            error_msg = RESPONSE_CODES.get(int(error_code), f"错误码: {error_code}")
            return False, f"❌ 抓取失败: {error_msg}"
        else:
            return True, f"✓ 抓取完成\n{response}"

    except socket.timeout:
        error_msg = f"Socket连接超时（{config['socket_timeout']}秒）"
        print(f"[grasp._send_via_socket] {error_msg}", file=sys.stderr)
        return False, error_msg

    except ConnectionRefusedError:
        error_msg = f"无法连接到开发板，请确认开发板上的服务器程序正在运行（端口 {config['socket_port']}）"
        print(f"[grasp._send_via_socket] {error_msg}", file=sys.stderr)
        return False, error_msg

    except Exception as e:
        error_msg = f"Socket通信错误: {str(e)}"
        print(f"[grasp._send_via_socket] {error_msg}", file=sys.stderr)
        return False, error_msg

    finally:
        if sock:
            sock.close()
            print(f"[grasp._send_via_socket] 连接已关闭", file=sys.stderr)


def _send_via_serial(color: str, config: Dict) -> Tuple[bool, str]:
    """
    通过串口发送抓取指令到开发板

    Args:
        color: 目标物体颜色
        config: 配置字典

    Returns:
        Tuple[成功标志, 结果消息]
    """
    try:
        import serial

        print(f"[grasp._send_via_serial] 打开串口: {config['serial_port']}", file=sys.stderr)

        # 打开串口
        ser = serial.Serial(
            port=config['serial_port'],
            baudrate=config['serial_baudrate'],
            timeout=10
        )

        # 等待串口就绪
        time.sleep(0.1)

        # 构建并发送指令（0xAA字节）
        command = bytes([COMMAND_BYTE])
        print(f"[grasp._send_via_serial] 发送指令: 0x{command.hex().upper()}", file=sys.stderr)

        ser.write(command)

        # 读取响应
        response = ser.readline().decode().strip()
        print(f"[grasp._send_via_serial] 收到响应: {response}", file=sys.stderr)

        ser.close()

        if response.startswith("SUCCESS"):
            return True, f"成功抓取{color}物体\n{response}"
        elif response.startswith("FAILED"):
            return False, f"抓取失败: {response}"
        else:
            return True, f"抓取{color}物体完成\n{response}"

    except ImportError:
        error_msg = "缺少pyserial库，请安装: pip install pyserial"
        print(f"[grasp._send_via_serial] {error_msg}", file=sys.stderr)
        return False, error_msg

    except Exception as e:
        error_msg = f"串口通信错误: {str(e)}"
        print(f"[grasp._send_via_serial] {error_msg}", file=sys.stderr)
        return False, error_msg


def register_tools(mcp):
    """
    注册抓取相关的所有工具函数到 MCP 服务器

    Args:
        mcp: FastMCP 服务器实例
    """

    @mcp.tool()
    async def grasp_object() -> Tuple[str, Dict]:
        """执行抓取动作 - 这是一个完整的独立功能，直接调用即可完成抓取。

        【重要】此功能包含所有必要操作，不需要任何导航、移动或准备步骤。
        当用户说"抓取"、"执行抓取"、"抓取物体"、"抓取方块"等时，直接调用此函数即可。

        工作原理：通过Socket发送0xAA指令到嵌入式开发板，开发板执行完整的抓取流程。
        开发板会打开摄像头、识别并抓取物体，然后返回结果。

        注意：
        - 不需要导航到任何位置
        - 不需要检查容器内容
        - 不需要任何参数
        - 不需要其他准备步骤

        Returns:
            A tuple containing the result message and updated robot state.

        Examples:
            用户说"抓取" → 直接调用 grasp_object()
            用户说"执行抓取" → 直接调用 grasp_object()
            用户说"抓取方块" → 直接调用 grasp_object()
        """
        print(f"[grasp.grasp_object] 开始执行抓取", file=sys.stderr)

        # 发送抓取指令到开发板
        success, result = send_grasp_command("")

        # 构建返回结果
        if success:
            state_update = {
                "action": "grasp",
                "success": True,
                "timestamp": time.time()
            }
            return f"✅ 抓取执行成功", state_update
        else:
            state_update = {
                "action": "grasp",
                "success": False,
                "error": result
            }
            return f"❌ 抓取执行失败: {result}", state_update

    @mcp.tool()
    async def check_grasp_status() -> Tuple[str, Dict]:
        """检查抓取模块状态 (Check grasp module status).

        检查开发板连接状态和抓取模块配置。

        Returns:
            A tuple containing the status message and current configuration.

        Examples:
            check_grasp_status()  # 检查抓取模块状态
        """
        config = BOARD_CONFIG

        print(f"[grasp.check_grasp_status] 检查模块状态", file=sys.stderr)

        status_info = f"抓取模块状态:\n"
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

        print(f"[grasp.check_grasp_status] 状态检查完成", file=sys.stderr)

        state_update = {
            "connection_type": config['connection_type'],
            "config": config,
            "status": "checked"
        }

        return status_info, state_update

    print("[grasp.py] 抓取控制模块已注册", file=sys.stderr)


# ============================================================================
# 开发板服务器程序
# ============================================================================
"""
需要在开发板上运行的服务器程序（保存为 grasp_server.py）：

```python
#!/usr/bin/env python3
import socket
import subprocess
import sys

# 配置
HOST = '0.0.0.0'  # 监听所有网络接口
PORT = 9999       # 端口号

def run_grasp_script(color):
    \"\"\"执行抓取脚本\"\"\"
    try:
        # 调用你的抓取脚本
        result = subprocess.run(
            ['bash', '/home/HwHiAiUser/test.sh'],
            env={**subprocess.os.environ, 'TARGET_COLOR': color},
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            return f"SUCCESS:00:{result.stdout}"
        else:
            return f"FAILED:04:{result.stderr}"

    except Exception as e:
        return f"FAILED:05:{str(e)}"

def handle_client(client_socket):
    \"\"\"处理客户端请求\"\"\"
    try:
        # 接收指令
        data = client_socket.recv(1024).decode('utf-8').strip()
        print(f\"收到指令: {data}\")

        # 解析指令
        if data.startswith('GRASP:'):
            color = data.split(':')[1]
            print(f\"抓取颜色: {color}\")

            # 执行抓取
            response = run_grasp_script(color)
            client_socket.sendall(response.encode('utf-8'))
        else:
            response = \"FAILED:01:指令格式错误\"
            client_socket.sendall(response.encode('utf-8'))

    except Exception as e:
        print(f\"处理错误: {e}\")
    finally:
        client_socket.close()

def main():
    \"\"\"主函数\"\"\"
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server_socket.bind((HOST, PORT))
        server_socket.listen(5)
        print(f\"抓取服务器启动，监听 {HOST}:{PORT}\")

        while True:
            client_socket, addr = server_socket.accept()
            print(f\"客户端连接: {addr}\")
            handle_client(client_socket)

    except KeyboardInterrupt:
        print(\"\\n服务器停止\")
    finally:
        server_socket.close()

if __name__ == \"__main__\":
    main()
```

在开发板上启动服务器：

```bash
# 1. 将服务器程序复制到开发板
scp grasp_server.py HwHiAiUser@192.168.0.155:/home/HwHiAiUser/

# 2. SSH登录到开发板
ssh HwHiAiUser@192.168.0.155

# 3. 启动服务器
python3 grasp_server.py

# 或者在后台运行
nohup python3 grasp_server.py > grasp_server.log 2>&1 &
```

通信协议：

发送指令格式：
```
GRASP:红色\\n
GRASP:red\\n
```

响应格式：
```
SUCCESS:00:成功抓取红色物体
FAILED:04:抓取失败
```

响应码：
- 0x00: 执行成功
- 0x01: 指令格式错误
- 0x02: 颜色参数错误
- 0x03: 摄像头打开失败
- 0x04: 抓取失败
- 0x05: 未知错误

"""
