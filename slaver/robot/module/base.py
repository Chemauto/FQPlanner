"""
底盘控制模块 - RoboCasa 仿真
"""

import os
import sys

# 添加项目根目录到 sys.path，以便导入 serve 模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from serve.sim import navigate, get_base_status


def register_tools(mcp):

    @mcp.tool()
    async def navigate_to_target(target: str) -> str:
        """导航到目标位置。

        将机器人底盘导航到场景中的指定位置。
        支持坐标格式："(x, y)" 或 "x, y"

        Args:
            target: 导航目标位置坐标，格式为 "(x, y)" 或 "x, y"

        Returns:
            包含结果消息和状态更新的 JSON 字符串。

        Examples:
            navigate_to_target(target="(1.5, -0.5)")
            navigate_to_target(target="1.5, -0.5")
        """
        print(f"[base] 导航到 '{target}'...", file=sys.stderr)

        # 解析坐标
        try:
            target = target.strip().strip("()")
            parts = [float(x.strip()) for x in target.split(",")]
            if len(parts) < 2:
                return "错误：坐标格式不正确，需要 (x, y) 格式"
            x, y = parts[0], parts[1]
            w = parts[2] if len(parts) > 2 else 0
        except ValueError as e:
            return f"错误：无法解析坐标 '{target}': {e}"

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
