"""
底盘控制模块 - RoboCasa 仿真
"""

import os
import sys

# 添加项目根目录到 sys.path，以便导入 serve 模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from serve.sim import navigate, get_base_status, get_scene


def register_tools(mcp):

    @mcp.tool()
    async def navigate_to_target(target: str) -> str:
        """导航到目标位置。

        将机器人底盘导航到场景中的指定位置。
        支持坐标格式："(x, y)" 或 "x, y"
        支持物体/家具名称，会自动查找其坐标。

        Args:
            target: 导航目标，可以是坐标 "(x, y)" 或物体名称（如 "apple"、"counter"）

        Returns:
            包含结果消息和状态更新的 JSON 字符串。

        Examples:
            navigate_to_target(target="(1.5, -0.5)")
            navigate_to_target(target="apple")
        """
        print(f"[base] 导航到 '{target}'...", file=sys.stderr)

        # 先尝试解析为坐标
        try:
            cleaned = target.strip().strip("()")
            parts = [float(x.strip()) for x in cleaned.split(",")]
            if len(parts) >= 2:
                x, y = parts[0], parts[1]
                w = parts[2] if len(parts) > 2 else 0
                return await _do_navigate(x, y, w, target)
        except ValueError:
            pass  # 不是坐标，尝试按名称查找

        # 按名称查找物体/家具坐标
        x, y, w = _find_target_pos(target)
        if x is None:
            return f"错误：无法找到目标 '{target}'，不是有效的坐标或场景中的物体"

        return await _do_navigate(x, y, w, target)

    async def _do_navigate(x, y, w, target):
        result = navigate(x, y, w)

        if result.get("success"):
            pos = result.get("pos", [0, 0, 0])
            yaw = result.get("yaw", 0)
            response = f"导航成功，当前位置: [{pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}], 朝向: {yaw:.1f}°"
            print(f"[base] ✓ {response}", file=sys.stderr)
            return response
        else:
            msg = result.get("result", f"导航到 {target} 失败，请重试。")
            print(f"[base] ✗ {msg}", file=sys.stderr)
            return msg

    def _find_target_pos(name):
        """在场景中查找物体或家具的坐标"""
        scene = get_scene()
        if not scene or "error" in scene:
            return None, None, None

        # 先在 objects 中查找
        objects = scene.get("objects", {})
        if name in objects:
            pos = objects[name]["pos"]
            return pos[0], pos[1], 0

        # 在 fixtures 中查找（模糊匹配）
        fixtures = scene.get("fixtures", {})
        for fname, finfo in fixtures.items():
            if name in fname or fname in name:
                pos = finfo["pos"]
                return pos[0], pos[1], 0

        return None, None, None

        result = navigate(x, y, w)

        if result.get("success"):
            pos = result.get("pos", [0, 0, 0])
            yaw = result.get("yaw", 0)
            response = f"导航成功，当前位置: [{pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}], 朝向: {yaw:.1f}°"
            print(f"[base] ✓ {response}", file=sys.stderr)
            return response
        else:
            msg = result.get("result", f"导航到 {target} 失败，请重试。")
            print(f"[base] ✗ {msg}", file=sys.stderr)
            return msg

    print("[base.py] 底盘控制模块已注册 (RoboCasa)", file=sys.stderr)
