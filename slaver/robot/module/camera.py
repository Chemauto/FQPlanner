"""
摄像头模块 - 场景截图工具
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from serve.sim import capture_screenshot


def register_tools(mcp):

    @mcp.tool()
    async def capture_image(camera_name: str = "overhead_cam") -> str:
        """拍照：从指定相机捕获当前场景图像。
        在执行关键操作前后使用，用于查看场景状态、确认物体位置或检查操作结果。

        Args:
            camera_name: 相机名称。可选: overhead_cam(俯视), side_cam(侧面),
                         robot0_frontview(机器人前视), robot0_eye_in_hand(手眼相机)

        Returns:
            截图结果和图像数据。
        """
        print(f"[camera] 拍照: {camera_name}", file=sys.stderr)

        result = capture_screenshot(camera_name)

        if not result.get("success"):
            msg = f"截图失败: {result.get('result', '未知错误')}"
            print(f"[camera] ✗ {msg}", file=sys.stderr)
            return msg

        print(f"[camera] ✓ 截图成功（{camera_name} 视角）", file=sys.stderr)
        response = f"截图成功（{camera_name} 视角）"
        return json.dumps([response, {"_image": result["image"]}])

    print("[camera.py] 摄像头模块已注册", file=sys.stderr)
