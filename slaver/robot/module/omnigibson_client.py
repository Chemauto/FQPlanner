"""
OmniGibson HTTP 客户端 - FQPlanner MCP 工具使用

将此文件复制到 FQPlanner/slaver/robot/module/ 目录下。

使用 urllib 标准库，无需额外安装依赖。
"""

import json
import urllib.request
import urllib.error

# 默认服务器地址（可通过 set_server_url 修改）
SERVER_URL = "http://127.0.0.1:5001"
TIMEOUT = 120


def set_server_url(url):
    global SERVER_URL
    SERVER_URL = url


def call_omnigibson(endpoint, data=None):
    """
    调用 OmniGibson 服务器 API

    Args:
        endpoint: API 路径 (如 "/action/grasp")
        data: POST 数据 (dict), None 则为 GET 请求

    Returns:
        dict: 服务器返回的 JSON 结果
            {"success": True/False, "result": "..."}
    """
    url = f"{SERVER_URL}{endpoint}"

    try:
        if data is not None:
            req = urllib.request.Request(
                url,
                data=json.dumps(data).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        else:
            req = urllib.request.Request(url)

        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))

    except urllib.error.URLError as e:
        return {"success": False, "result": f"OmniGibson 服务器连接失败: {e}"}
    except Exception as e:
        return {"success": False, "result": f"请求错误: {e}"}


def load_task(task_name, scene=None):
    """加载 BEHAVIOR 任务

    Args:
        task_name: 任务名称 (如 "picking_up_trash")
        scene: 场景名称 (可选，默认使用当前场景)

    Returns:
        dict: {"success": True, "objects": [...], "object_count": N}
    """
    data = {"task_name": task_name}
    if scene:
        data["scene"] = scene
    return call_omnigibson("/task/load", data)


def list_tasks(filter_text=None):
    """列出可用的 BEHAVIOR 任务

    Args:
        filter_text: 过滤关键词 (可选)

    Returns:
        dict: {"success": True, "tasks": [...], "count": N}
    """
    endpoint = "/task/list"
    if filter_text:
        endpoint += f"?filter={filter_text}"
    return call_omnigibson(endpoint)


def get_task_current():
    """获取当前任务信息

    Returns:
        dict: {"success": True, "task": "...", "scene": "..."}
    """
    return call_omnigibson("/task/current")


def get_scene_profile():
    """获取当前场景的 profile 数据

    Returns:
        dict: {"success": True, "profile": {"tables": [...], "containers": [...], ...}}
    """
    return call_omnigibson("/scene/profile")


def get_viewer_image_base64():
    """获取观察者视角截图（base64 编码）

    Returns:
        dict: {"success": True, "image": "base64...", "format": "png"}
    """
    return call_omnigibson("/camera/viewer_base64")


def get_robot_image_base64():
    """获取机器人视角截图（base64 编码）

    Returns:
        dict: {"success": True, "image": "base64...", "format": "png"}
    """
    return call_omnigibson("/camera/robot_base64")


def save_viewer_image(filepath):
    """获取观察者视角截图并保存到文件

    Args:
        filepath: 保存路径 (如 "screenshot.png")

    Returns:
        bool: 是否成功
    """
    url = f"{SERVER_URL}/camera/viewer"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            with open(filepath, "wb") as f:
                f.write(resp.read())
        return True
    except Exception:
        return False


def save_robot_image(filepath):
    """获取机器人视角截图并保存到文件

    Args:
        filepath: 保存路径 (如 "robot_view.png")

    Returns:
        bool: 是否成功
    """
    url = f"{SERVER_URL}/camera/robot"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            with open(filepath, "wb") as f:
                f.write(resp.read())
        return True
    except Exception:
        return False
