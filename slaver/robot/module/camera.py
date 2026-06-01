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
        注意：每个任务最多拍照1次。拍照后必须立即执行具体操作（导航/抓取/放置），不要连续拍照。
        仅在需要确认场景状态时使用，不要用它替代导航或抓取操作。

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
            return json.dumps([msg, {"_status": "failure"}])

        print(f"[camera] ✓ 截图成功（{camera_name} 视角）", file=sys.stderr)
        response = f"截图成功（{camera_name} 视角）"
        # 相机正常完成返回 none，不触发任何特殊处理
        return json.dumps([response, {"_status": "none", "_image": result["image"]}])

    @mcp.tool()
    async def report_issue(issue: str) -> str:
        """上报异常：当通过相机或其他方式发现问题时，向主控报告。

        例如：物体位置异常、场景状态不符合预期、发现新的障碍物等。

        Args:
            issue: 异常描述

        Returns:
            上报结果。
        """
        print(f"[camera] 上报异常: {issue}", file=sys.stderr)
        return json.dumps([f"已上报异常: {issue}", {"_status": "recall"}])

    print("[camera.py] 摄像头模块已注册", file=sys.stderr)
