#!/usr/bin/env python3
"""
抓取服务器程序 - 运行在真实机械臂端或本机

监听 Socket 连接，接收 0xAA 指令，执行当前项目内的抓取脚本并返回结果。

使用方法：
    python3 serve_real/Arm/grasp_server.py

    或在后台运行：
    nohup python3 serve_real/Arm/grasp_server.py > grasp_server.log 2>&1 &
"""

import socket
import subprocess
import os


# 配置
HOST = "0.0.0.0"  # 监听所有网络接口
PORT = 9999       # 端口号
SCRIPT_PATH = "/home/fangqi/camera_10s.sh"  # 抓取脚本绝对路径
GRASP_COMMAND = 0xAA  # 抓取指令字节
TIMEOUT = 60          # 抓取脚本超时时间（秒）


def run_grasp_script():
    """
    执行抓取脚本

    Returns:
        响应字符串
    """
    try:
        print("[服务器] 开始执行抓取脚本")

        if not os.path.exists(SCRIPT_PATH):
            error_msg = f"抓取脚本不存在: {SCRIPT_PATH}"
            print(f"[服务器] {error_msg}")
            return f"FAILED:03:{error_msg}"

        result = subprocess.run(
            ["bash", SCRIPT_PATH],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )

        if result.returncode == 0:
            print("[服务器] 抓取成功")
            if result.stdout:
                print(f"[服务器] 输出: {result.stdout}")
            return "SUCCESS:00:抓取执行成功"

        print("[服务器] 抓取失败")
        if result.stderr:
            print(f"[服务器] 错误: {result.stderr}")
        return "FAILED:04:抓取失败"

    except subprocess.TimeoutExpired:
        error_msg = f"抓取超时（{TIMEOUT}秒）"
        print(f"[服务器] {error_msg}")
        return f"FAILED:04:{error_msg}"

    except Exception as e:
        error_msg = f"执行错误: {str(e)}"
        print(f"[服务器] {error_msg}")
        return f"FAILED:05:{error_msg}"


def handle_client(client_socket, client_address):
    """
    处理客户端请求

    Args:
        client_socket: 客户端 Socket
        client_address: 客户端地址
    """
    try:
        print(f"[服务器] 客户端连接: {client_address}")

        data = client_socket.recv(1024)
        if not data:
            print("[服务器] 收到空数据，断开连接")
            return

        hex_data = " ".join(f"0x{b:02X}" for b in data)
        print(f"[服务器] 收到数据: {hex_data}")

        if len(data) > 0 and data[0] == GRASP_COMMAND:
            print(f"[服务器] 收到抓取指令 (0x{GRASP_COMMAND:02X})")
            response = run_grasp_script()
            client_socket.sendall(response.encode("utf-8"))
        else:
            error_msg = f"无效指令，期望 0x{GRASP_COMMAND:02X}"
            print(f"[服务器] {error_msg}")
            response = f"FAILED:01:{error_msg}"
            client_socket.sendall(response.encode("utf-8"))

    except Exception as e:
        error_msg = f"处理错误: {str(e)}"
        print(f"[服务器] {error_msg}")
        try:
            response = f"FAILED:05:{error_msg}"
            client_socket.sendall(response.encode("utf-8"))
        except Exception:
            pass

    finally:
        client_socket.close()
        print(f"[服务器] 客户端断开: {client_address}")


def main():
    """主函数"""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server_socket.bind((HOST, PORT))
        server_socket.listen(5)

        print("=" * 60)
        print("抓取服务器启动成功")
        print(f"监听地址: {HOST}:{PORT}")
        print(f"抓取指令: 0x{GRASP_COMMAND:02X}")
        print(f"抓取脚本: {SCRIPT_PATH}")
        print("=" * 60)
        print("等待客户端连接...")
        print("按 Ctrl+C 停止服务器")
        print("=" * 60)

        while True:
            client_socket, client_address = server_socket.accept()
            handle_client(client_socket, client_address)

    except KeyboardInterrupt:
        print("\n" + "=" * 60)
        print("服务器停止")
        print("=" * 60)

    except Exception as e:
        print(f"\n服务器错误: {e}")

    finally:
        server_socket.close()


if __name__ == "__main__":
    main()
