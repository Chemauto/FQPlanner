"""
bridge_node.py - MuJoCo ↔ ROS2 Nav2 桥接节点

运行在 Docker 容器中（ROS2 环境），通过 HTTP 与 MuJoCo Flask API 通信。

功能:
  1. 轮询 Flask /base_status → 发布 /odom + /tf（20Hz）
  2. 订阅 /cmd_vel → POST Flask /cmd_vel
  3. 提供 HTTP /navigate 端点 → 发送 Nav2 NavigateToPose goal

使用:
  python bridge_node.py
"""

import os
import json
import math
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient

from geometry_msgs.msg import Twist, TransformStamped
from nav_msgs.msg import Odometry
from nav2_msgs.action import NavigateToPose
from tf2_ros import TransformBroadcaster

import requests

MUJOCO_API = os.environ.get("MUJOCO_API_URL", "http://127.0.0.1:5001")
BRIDGE_PORT = int(os.environ.get("BRIDGE_PORT", "5002"))
LINEAR_SCALE = float(os.environ.get("LINEAR_SCALE", "1.0"))
ANGULAR_SCALE = float(os.environ.get("ANGULAR_SCALE", "1.0"))
MAX_LINEAR = float(os.environ.get("MAX_LINEAR", "0.35"))
MAX_ANGULAR = float(os.environ.get("MAX_ANGULAR", "0.25"))
CMD_SMOOTHING = float(os.environ.get("CMD_SMOOTHING", "0.35"))


class MuJoCoBridge(Node):
    def __init__(self):
        super().__init__("mujoco_bridge")

        # 发布 odom
        self.odom_pub = self.create_publisher(Odometry, "/odom", 10)
        self.tf_broadcaster = TransformBroadcaster(self)

        # 订阅 cmd_vel
        self.cmd_vel_sub = self.create_subscription(
            Twist, "/cmd_vel", self._cmd_vel_cb, 10
        )

        # Nav2 action client. Nav2 computes the path and local DWB controller
        # publishes /cmd_vel; this node only bridges /cmd_vel to MuJoCo.
        self.nav_client = ActionClient(self, NavigateToPose, "navigate_to_pose")

        # 上次 odom 时间
        self.last_odom_time = self.get_clock().now()
        self.last_cmd_log_time = self.get_clock().now()
        self.filtered_vx = 0.0
        self.filtered_vy = 0.0
        self.filtered_vw = 0.0

        # 20Hz 定时器发布 odom
        self.timer = self.create_timer(0.05, self._publish_odom)

        self.get_logger().info(
            f"MuJoCo Bridge 启动: API={MUJOCO_API}, port={BRIDGE_PORT}"
        )

    def _get_base_status(self):
        """从 Flask 获取底座状态"""
        try:
            resp = requests.get(f"{MUJOCO_API}/base_status", timeout=2)
            return resp.json()
        except Exception as e:
            self.get_logger().warn(f"获取底座状态失败: {e}")
            return None

    def _publish_odom(self):
        """发布 odom 和 tf"""
        data = self._get_base_status()
        if data is None or "error" in data:
            return

        pos = data.get("pos", [0, 0, 0])
        yaw = math.radians(data.get("yaw_deg", 0))
        now = self.get_clock().now().to_msg()

        # odom
        odom = Odometry()
        odom.header.stamp = now
        odom.header.frame_id = "odom"
        odom.child_frame_id = "base_footprint"
        odom.pose.pose.position.x = pos[0]
        odom.pose.pose.position.y = pos[1]
        odom.pose.pose.position.z = pos[2]
        odom.pose.pose.orientation.z = math.sin(yaw / 2)
        odom.pose.pose.orientation.w = math.cos(yaw / 2)
        self.odom_pub.publish(odom)

        # tf: odom → base_footprint
        tf = TransformStamped()
        tf.header.stamp = now
        tf.header.frame_id = "odom"
        tf.child_frame_id = "base_footprint"
        tf.transform.translation.x = pos[0]
        tf.transform.translation.y = pos[1]
        tf.transform.translation.z = pos[2]
        tf.transform.rotation.z = math.sin(yaw / 2)
        tf.transform.rotation.w = math.cos(yaw / 2)
        self.tf_broadcaster.sendTransform(tf)

    def _cmd_vel_cb(self, msg: Twist):
        """Nav2 输出速度 → 转发给 MuJoCo"""
        try:
            target_vx = max(-MAX_LINEAR, min(MAX_LINEAR, msg.linear.x * LINEAR_SCALE))
            target_vy = max(-MAX_LINEAR, min(MAX_LINEAR, msg.linear.y * LINEAR_SCALE))
            target_vw = max(-MAX_ANGULAR, min(MAX_ANGULAR, msg.angular.z * ANGULAR_SCALE))

            alpha = max(0.0, min(1.0, CMD_SMOOTHING))
            self.filtered_vx += alpha * (target_vx - self.filtered_vx)
            self.filtered_vy += alpha * (target_vy - self.filtered_vy)
            self.filtered_vw += alpha * (target_vw - self.filtered_vw)

            now = self.get_clock().now()
            if (now - self.last_cmd_log_time).nanoseconds > 1_000_000_000:
                self.get_logger().info(
                    "cmd_vel forwarded: "
                    f"vx={self.filtered_vx:.3f}, vy={self.filtered_vy:.3f}, vw={self.filtered_vw:.3f} "
                    f"(raw vx={msg.linear.x:.3f}, vy={msg.linear.y:.3f}, vw={msg.angular.z:.3f})"
                )
                self.last_cmd_log_time = now

            resp = requests.post(
                f"{MUJOCO_API}/cmd_vel",
                json={
                    "vx": self.filtered_vx,
                    "vy": self.filtered_vy,
                    "vw": self.filtered_vw,
                },
                timeout=2,
            )
            if resp.status_code != 200:
                self.get_logger().warn(f"cmd_vel 转发失败: {resp.text}")
        except Exception as e:
            self.get_logger().warn(f"cmd_vel 转发异常: {e}")

    def send_nav_goal(self, x, y, w_deg, timeout=120):
        """发送 Nav2 NavigateToPose 目标，等待结果"""
        self.get_logger().info(f"发送 Nav2 目标: ({x}, {y}, {w_deg}°)")

        if not self.nav_client.wait_for_server(timeout_sec=5.0):
            self.get_logger().error("Nav2 action server 未就绪")
            return {"success": False, "result": "Nav2 action server 未就绪"}

        goal = NavigateToPose.Goal()
        goal.pose.header.frame_id = "map"
        goal.pose.pose.position.x = x
        goal.pose.pose.position.y = y
        yaw = math.radians(w_deg)
        goal.pose.pose.orientation.z = math.sin(yaw / 2)
        goal.pose.pose.orientation.w = math.cos(yaw / 2)

        future = self.nav_client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, future, timeout_sec=10)

        goal_handle = future.result()
        if not goal_handle.accepted:
            return {"success": False, "result": "目标被拒绝"}

        result_future = goal_handle.get_result_async()
        rclpy.spin_until_future_complete(
            self, result_future, timeout_sec=float(timeout)
        )

        result = result_future.result()
        if result is None:
            return {"success": False, "result": "导航超时"}

        status = result.status
        if status == 4:  # SUCCEEDED
            base = self._get_base_status()
            return {
                "success": True,
                "pos": base.get("pos", [0, 0, 0]) if base else [0, 0, 0],
                "yaw": base.get("yaw_deg", 0) if base else 0,
            }
        return {"success": False, "result": f"导航失败，status={status}"}


# HTTP 服务：接收导航目标
_bridge_node = None


class NavHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/navigate":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/navigate":
            content_len = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_len))
            x = body.get("x")
            y = body.get("y")
            w = body.get("w", 0)
            timeout = body.get("timeout", 120)

            result = _bridge_node.send_nav_goal(x, y, w, timeout)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # 静默


def run_http_server(port):
    server = HTTPServer(("0.0.0.0", port), NavHandler)
    server.serve_forever()


def main():
    global _bridge_node

    rclpy.init()
    _bridge_node = MuJoCoBridge()

    # 启动 HTTP 服务（单独线程，接收导航目标）
    http_thread = threading.Thread(
        target=run_http_server, args=(BRIDGE_PORT,), daemon=True
    )
    http_thread.start()
    _bridge_node.get_logger().info(f"HTTP 导航接口: http://0.0.0.0:{BRIDGE_PORT}/navigate")

    try:
        rclpy.spin(_bridge_node)
    except KeyboardInterrupt:
        pass
    finally:
        _bridge_node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
