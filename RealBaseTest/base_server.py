#!/usr/bin/env python3
"""
麦轮底盘控制服务器 (Omnidirectional Base Control Server)

在开发板上运行此服务器，监听来自RoboOS的Socket连接并控制底盘。
"""

import socket
import sys
import time

# 导入底盘控制器
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
    """初始化底盘连接"""
    global base_controller
    if base_controller is None:
        base_controller = OmniWheelController()
        try:
            success = base_controller.connect()
            if success:
                print("✓ 三全向轮底盘连接成功")
                return True
            else:
                print("✗ 三全向轮底盘连接失败")
                base_controller = None
                return False
        except Exception as e:
            print(f"✗ 底盘初始化异常: {e}")
            base_controller = None
            return False
    return True


def execute_move(direction, speed, duration):
    """执行移动指令"""
    try:
        if base_controller is None:
            if not initialize_base():
                return f"FAILED:底盘未连接"

        if base_controller.base_bus is None:
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

        print(f"[执行移动] 方向={direction}, 速度={speed}m/s, 时间={duration}s")

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

        print(f"[执行移动] 完成")

        return f"SUCCESS:底盘已向{direction}方向移动{duration}秒，速度{speed}m/s"

    except Exception as e:
        print(f"[执行移动] 异常: {e}")
        return f"FAILED:移动失败: {str(e)}"


def execute_move_raw(vx, vy, omega, duration):
    """执行原始速度移动指令"""
    try:
        if base_controller is None:
            if not initialize_base():
                return f"FAILED:底盘未连接"

        if base_controller.base_bus is None:
            return f"FAILED:底盘未连接"

        print(f"[执行原始移动] vx={vx}m/s, vy={vy}m/s, omega={omega}rad/s, 时间={duration}s")

        # 设置速度
        success = base_controller.set_velocity_raw(vx=float(vx), vy=float(vy), omega=float(omega))

        if not success:
            return f"FAILED:设置底盘速度失败"

        # 等待指定时间
        time.sleep(duration)

        # 停止底盘
        base_controller.stop()

        print(f"[执行原始移动] 完成")

        return f"SUCCESS:底盘已按指定速度移动{duration}秒"

    except Exception as e:
        print(f"[执行原始移动] 异常: {e}")
        return f"FAILED:移动失败: {str(e)}"


def execute_stop():
    """执行停止指令"""
    try:
        if base_controller is None:
            if not initialize_base():
                return f"FAILED:底盘未连接"

        if base_controller.base_bus is None:
            return f"FAILED:底盘未连接"

        print(f"[执行停止] 正在停止底盘")

        success = base_controller.stop()

        if success:
            print(f"[执行停止] 完成")
            return f"SUCCESS:底盘已停止"
        else:
            print(f"[执行停止] 失败")
            return f"FAILED:停止底盘失败"

    except Exception as e:
        print(f"[执行停止] 异常: {e}")
        return f"FAILED:停止失败: {str(e)}"


def handle_client(client_socket, addr):
    """处理客户端请求"""
    try:
        print(f"[客户端连接] {addr}")

        # 接收指令
        data = client_socket.recv(1024).decode('utf-8').strip()
        print(f"[收到指令] {data}")

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
                response = f"FAILED:未知指令: {command}"

            client_socket.sendall(response.encode('utf-8'))
            print(f"[发送响应] {response}")
        else:
            response = "FAILED:指令格式错误，需要BASE:前缀"
            client_socket.sendall(response.encode('utf-8'))
            print(f"[发送响应] {response}")

    except Exception as e:
        print(f"[处理错误] {e}")
        try:
            client_socket.sendall(f"FAILED:{str(e)}".encode('utf-8'))
        except:
            pass
    finally:
        client_socket.close()
        print(f"[客户端断开] {addr}")


def main():
    """主函数"""
    global base_controller

    print("=" * 60)
    print("麦轮底盘控制服务器")
    print("=" * 60)

    # 初始化底盘
    print("\n[初始化] 正在连接底盘...")
    if initialize_base():
        print("[初始化] 底盘连接成功")
    else:
        print("[初始化] 底盘连接失败，但仍可启动服务器（将在首次指令时重试）")

    # 创建服务器Socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        server_socket.bind((HOST, PORT))
        server_socket.listen(5)
        print(f"\n[服务器] 启动成功，监听 {HOST}:{PORT}")
        print("[服务器] 等待客户端连接...\n")

        while True:
            client_socket, addr = server_socket.accept()
            handle_client(client_socket, addr)

    except KeyboardInterrupt:
        print("\n[服务器] 收到停止信号")
    except Exception as e:
        print(f"\n[服务器] 错误: {e}")
    finally:
        print("[服务器] 正在关闭...")
        if base_controller:
            try:
                base_controller.stop()
                base_controller.disconnect()
                print("[服务器] 底盘已断开连接")
            except:
                pass
        server_socket.close()
        print("[服务器] 服务器已停止")


if __name__ == "__main__":
    main()
