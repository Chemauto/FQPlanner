"""
摄像头模块 - 场景截图 + VLM 分析
"""

import json
import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

# 加载 .env（确保 MCP 子进程也能读到 API key）
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
load_dotenv(os.path.join(_project_root, '.env'))

from serve.sim import capture_screenshot

# ============================================================
# 配置
# ============================================================

# 默认相机
CAMERA_SOURCE = "robot0_frontview"

# VLM 配置
VLM_MODEL = "mimo-v2.5"
VLM_API_BASE = "https://api.xiaomimimo.com/v1"

def _call_vlm(image_b64: str, context: str = "") -> tuple:
    """调用 VLM 分析图像，返回 (status, description)。
    status: "normal" 或 "abnormal"
    description: VLM 对场景的一句话描述
    """
    try:
        if context:
            prompt = f"""你是机器人场景监控系统。当前任务：{context}

请分析这张图片，判断任务执行后场景是否符合预期。
- normal：场景状态符合任务预期
- abnormal：场景状态不符合预期、有异常

请先用一句话描述你看到的场景，然后最后一行只回复 normal 或 abnormal。"""
        else:
            prompt = """你是机器人场景监控系统。请分析这张图片，判断场景是否正常。
- normal：物体在预期位置，没有异常
- abnormal：物体位置不对、有障碍物、场景异常

请先用一句话描述你看到的场景，然后最后一行只回复 normal 或 abnormal。"""

        api_key = os.environ.get("CLOUD_API_KEY", "")
        client = OpenAI(api_key=api_key, base_url=VLM_API_BASE)
        response = client.chat.completions.create(
            model=VLM_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                        },
                    ],
                }
            ],
            max_tokens=1000,
            temperature=0,
        )
        raw_content = response.choices[0].message.content
        result = raw_content.strip() if raw_content else ""
        print(f"[camera] VLM 原始输出: {repr(raw_content)}", file=sys.stderr)
        print(f"[camera] VLM 处理后: {repr(result)}", file=sys.stderr)

        if not result:
            return "normal", "VLM 返回空内容，无法判断场景状态"

        # 提取最后一行判断状态，其余作为描述
        lines = result.split("\n")
        status_line = lines[-1].strip().lower()
        status = "abnormal" if "abnormal" in status_line else "normal"
        description = "\n".join(lines[:-1]).strip() if len(lines) > 1 else result
        return status, description
    except Exception as e:
        print(f"[camera] VLM 调用失败: {e}", file=sys.stderr)
        return "normal", f"VLM 调用失败: {e}"


def register_tools(mcp):

    @mcp.tool()
    async def capture_image(camera_name: str = CAMERA_SOURCE, context: str = "") -> str:
        """拍照：从指定相机捕获当前场景图像，并用 VLM 分析场景状态。
        注意：每个任务最多拍照1次。拍照后必须立即执行具体操作（导航/抓取/放置），不要连续拍照。

        Args:
            camera_name: 相机名称。可选: overhead_cam(俯视), side_cam(侧面),
                         robot0_frontview(机器人前视), robot0_eye_in_hand(手眼相机)
            context: 当前任务描述，用于 VLM 判断场景是否正常。例如："正在抓取马克杯"、"已导航到水槽附近"

        Returns:
            截图结果和场景分析。
        """
        print(f"[camera] 拍照: {camera_name}", file=sys.stderr)

        result = capture_screenshot(camera_name)

        if not result.get("success"):
            msg = f"截图失败: {result.get('result', '未知错误')}"
            print(f"[camera] ✗ {msg}", file=sys.stderr)
            return json.dumps([msg, {"_status": "failure"}])

        image_b64 = result["image"]

        # VLM 分析场景（传入任务上下文）
        print(f"[camera] VLM 分析场景... (context: {context})", file=sys.stderr)
        scene_status, vlm_description = _call_vlm(image_b64, context)
        print(f"[camera] VLM 结果: {scene_status}, 描述: {vlm_description}", file=sys.stderr)

        # 统一返回 none 状态，让 Slaver 正常完成，把 VLM 描述传给 Master 决策
        response = f"截图成功（{camera_name} 视角），VLM 判断: {scene_status}，场景描述: {vlm_description}"
        return json.dumps([response, {"_status": "none", "_image": image_b64}])

    print("[camera.py] 摄像头模块已注册 (VLM 分析)", file=sys.stderr)
