"""
抓取控制模块 - XLeRobot MuJoCo 仿真
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from serve.service.client import grasp_object as _grasp_object


def register_tools(mcp):

    @mcp.tool()
    async def grasp_object(object_name: str = None) -> str:
        """抓取物体。

        机器人抓取指定物体。仅当机器人当前没有抓取任何物体时使用。
        如果已经抓取了物体，需要先使用 release_object 释放。

        Args:
            object_name: 要抓取的物体名称（如 "mug"、"apple"）。一次只能抓取一个物体。

        Returns:
            抓取结果，成功或失败信息。
        """
        target = object_name or "unknown_object"
        print(f"[grasp] 开始抓取 '{target}'...", file=sys.stderr)

        result = _grasp_object(target)

        if result.get("success"):
            response = result.get("result", f"成功抓取 {target}")
            print(f"[grasp] ✓ {response}", file=sys.stderr)
            return json.dumps([response, {"_status": "success"}])
        else:
            msg = result.get("result", f"抓取 {target} 失败，请重试。")
            print(f"[grasp] ✗ {msg}", file=sys.stderr)
            return json.dumps([msg, {"_status": "failure"}])

    print("[grasp.py] 抓取控制模块已注册 (XLeRobot MuJoCo)", file=sys.stderr)
