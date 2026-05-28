"""
放置/释放控制模块 - RoboCasa 仿真
"""

import os
import sys
OBJECT_NAME_MAP = {
    "苹果": "apple",
    "杯子": "cup", 
    "碗": "bowl",
    "锅": "pot",
    "马克杯": "mug",
    "海绵": "sponge",
}
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from serve.sim import (
    place_object as _place_object,
    open_gripper as _open_gripper,
    get_objects,
)
def _find_fixture_pos(target_name):
    """在 fixtures 里找最匹配的家具位置"""
    import requests
    resp = requests.get("http://127.0.0.1:5001/fixtures", timeout=3)
    if resp.status_code != 200:
        return None
    fixtures = resp.json()
    
    # 精确匹配
    if target_name in fixtures:
        return fixtures[target_name]["pos"]
    
    # 模糊匹配：找包含 target_name 且包含 "main" 的键
    candidates = [k for k in fixtures if target_name in k and "main" in k]
    if not candidates:
        candidates = [k for k in fixtures if target_name in k]
    if candidates:
        return fixtures[candidates[0]]["pos"]
    return None

def register_tools(mcp):

    @mcp.tool()
    async def place_on_top(obj_name: str, target_name: str) -> str:
        obj_name = OBJECT_NAME_MAP.get(obj_name, obj_name)
        target_name = OBJECT_NAME_MAP.get(target_name, target_name)
        
        import requests
        
        # 先查可操作物体
        objects = get_objects()
        target_pos = None
        
        if objects and target_name in objects:
            target_pos = objects[target_name]["pos"]
            place_pos = [target_pos[0], target_pos[1], target_pos[2] + 0.05]
        else:
            # fallback 到 fixtures 模糊匹配
            target_pos = _find_fixture_pos(target_name)
            if target_pos is None:
                return f"未找到目标 '{target_name}'"
            place_pos = [target_pos[0], target_pos[1], target_pos[2] + 0.15]
        
        result = _place_object(obj_name, place_pos)
        if result.get("success"):
            return result.get("result", f"成功将 {obj_name} 放在 {target_name} 上面")
        else:
            return result.get("result", "放置失败，请重试。")

    @mcp.tool()
    async def place_object(obj_name: str, x: float, y: float, z: float) -> str:
        """将物体放置到指定坐标位置。

        Args:
            obj_name: 要放置的物体名称
            x: 目标位置 x 坐标
            y: 目标位置 y 坐标
            z: 目标位置 z 坐标

        Returns:
            放置结果，成功或失败信息。
        """
        target_pos = [x, y, z]
        obj_name = OBJECT_NAME_MAP.get(obj_name, obj_name)      # 加这行
        print(f"[place] 将 '{obj_name}' 放到 {target_pos}...", file=sys.stderr)

        result = _place_object(obj_name, target_pos)

        if result.get("success"):
            response = result.get("result", f"成功将 {obj_name} 放到目标位置")
            print(f"[place] ✓ {response}", file=sys.stderr)
            return response
        else:
            msg = result.get("result", f"放置失败，请重试。")
            print(f"[place] ✗ {msg}", file=sys.stderr)
            return msg

    # @mcp.tool()
    # async def release_object() -> str:
    #     """释放当前抓取的物体（打开夹爪）。

    #     Returns:
    #         操作结果。
    #     """
    #     print("[place] 释放物体...", file=sys.stderr)
    #     result = _open_gripper()

    #     if result.get("success"):
    #         response = "成功释放物体"
    #         print(f"[place] ✓ {response}", file=sys.stderr)
    #         return response
    #     else:
    #         msg = result.get("result", "释放物体失败，请重试。")
    #         print(f"[place] ✗ {msg}", file=sys.stderr)
    #         return msg

    # print("[place.py] 放置/释放控制模块已注册 (RoboCasa)", file=sys.stderr)
