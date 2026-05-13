"""
抓取控制模块 - 模拟抓取
"""

import asyncio
import random
import sys


def register_tools(mcp):

    @mcp.tool()
    async def grasp_object(object_name: str = None) -> str:
        """抓取物体。

        机器人抓取指定物体

        Args:
            object_name: 要抓取的物体名称（如 "苹果"、"方块"），可选。一次只能抓取一个物体。

        Returns:
            抓取结果，成功或失败信息。
        """
        target = object_name 
        print(f"[grasp.grasp_object] 开始抓取 '{target}'...", file=sys.stderr)

        await asyncio.sleep(5)

        if random.random() < 0.8:
            result = f"成功抓取了 {target}。"
            print(f"[grasp.grasp_object] {result}", file=sys.stderr)
            return result
        else:
            result = f"抓取 {target} 失败，请重试。"
            print(f"[grasp.grasp_object] {result}", file=sys.stderr)
            return result

    print("[grasp.py] 抓取控制模块已注册", file=sys.stderr)
