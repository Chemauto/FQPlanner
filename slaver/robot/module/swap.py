"""
打扫控制模块 - 模拟打扫
"""

import asyncio
import random
import sys


def register_tools(mcp):

    @mcp.tool()
    async def clean_area(area_name: str = None) -> str:
        """打扫区域。

        机器人打扫指定区域

        Args:
            area_name: 要打扫的区域名称（如 "卧室"、"客厅"），可选。

        Returns:
            打扫结果，成功或失败信息。
        """
        target = area_name or "区域"
        print(f"[swap.clean_area] 开始打扫 '{target}'...", file=sys.stderr)

        await asyncio.sleep(5)

        if random.random() < 0.8:
            result = f"成功打扫了 {target}。"
            print(f"[swap.clean_area] {result}", file=sys.stderr)
            return result
        else:
            result = f"打扫 {target} 失败，请重试。"
            print(f"[swap.clean_area] {result}", file=sys.stderr)
            return result

    print("[swap.py] 打扫控制模块已注册", file=sys.stderr)
