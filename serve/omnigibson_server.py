"""
OmniGibson HTTP Server - 为 FQPlanner 提供仿真执行后端

直接操控仿真状态，绕过 CuRobo 和生成器管道。

支持两种模式：
  基础模式: python omnigibson_server.py Rs_int 5001
  任务模式: python omnigibson_server.py Rs_int 5001 picking_up_trash

API 端点:
    GET  /status            - 健康检查
    GET  /objects           - 列出场景物体
    GET  /robot/state       - 机器人状态
    GET  /camera/viewer     - 观察者视角截图（俯视全景）
    GET  /camera/robot      - 机器人视角截图（第一人称）
    GET  /task/list         - 列出可用 BEHAVIOR 任务
    GET  /task/current      - 当前任务信息
    POST /task/load         - 加载/切换任务
    GET  /scene/profile     - 返回 profile.yaml 格式的场景数据
    POST /action/grasp      - 抓取物体
    POST /action/place_on_top  - 放在物体上面
    POST /action/place_inside  - 放入物体内部
    POST /action/navigate   - 导航到物体
    POST /action/open       - 打开物体
    POST /action/close      - 关闭物体
    POST /action/release    - 释放物体
"""

import os
os.environ["OMNIGIBSON_HEADLESS"] = "True"

import json
import traceback
import base64
import io
from flask import Flask, request, jsonify, send_file

import torch as th
import omnigibson as og
from omnigibson.macros import gm
from omnigibson import object_states

# 性能优化
gm.USE_GPU_DYNAMICS = False
gm.ENABLE_FLATCACHE = True

import queue
import threading

app = Flask(__name__)

# 全局状态
env = None
robot = None
held_object = None
current_scene = None
current_task = None

# 录制状态
recording = False
record_frames = []
record_dir = "/home/fangqi/WorkXCJ/BEHAVIOR-1K/My_code/recordings"

# 主线程动作队列（Flask 工作线程 → 主线程）
_action_queue = queue.Queue()
_action_results = {}  # {request_id: result_dict}

# 物体类别到 profile type 的映射
TABLE_CATEGORIES = {
    "breakfast_table", "coffee_table", "dining_table", "desk",
    "side_table", "console_table", "countertop", "workbench",
}
CONTAINER_CATEGORIES = {
    "fridge", "bottom_cabinet", "top_cabinet", "microwave",
    "oven", "dishwasher", "public_trash_can", "trash_can",
    "suitcase", "box", "crate", "basket", "shelf",
    "cabinet", "drawer",
}

# 中文到英文物体名称映射（LLM 可能传递中文名称）
ZH_EN_MAP = {
    # 家具 - 桌子
    "早餐桌": "breakfast_table", "咖啡桌": "coffee_table", "餐桌": "dining_table",
    "书桌": "desk", "边桌": "side_table", "玄关桌": "console_table",
    "料理台": "countertop", "工作台": "workbench", "桌子": "table",
    # 家具 - 容器
    "冰箱": "fridge", "柜子": "cabinet", "橱柜": "bottom_cabinet",
    "吊柜": "top_cabinet", "微波炉": "microwave", "烤箱": "oven",
    "洗碗机": "dishwasher", "垃圾桶": "trash_can", "公共垃圾桶": "public_trash_can",
    "行李箱": "suitcase", "盒子": "box", "板条箱": "crate",
    "篮子": "basket", "书架": "shelf", "抽屉": "drawer",
    # 常见物体
    "笔记本电脑": "laptop", "笔记本": "laptop", "电脑": "laptop",
    "杯子": "cup", "马克杯": "mug", "碗": "bowl", "盘子": "plate",
    "瓶子": "bottle", "勺子": "spoon", "叉子": "fork", "刀": "knife",
    "苹果": "apple", "香蕉": "banana", "橘子": "orange",
    "书": "book", "手机": "phone", "遥控器": "remote_control",
    "毛巾": "towel", "肥皂": "soap", "牙刷": "toothbrush",
    "枕头": "pillow", "毯子": "blanket",
}


def load_objects_from_profile():
    """从 profile.yaml 加载可操作的小物体（不加载场景自带的家具）"""
    import yaml
    profile_path = os.path.join(os.path.dirname(__file__), "profile.yaml")
    if not os.path.exists(profile_path):
        print("[OmniGibson] 警告: profile.yaml 不存在，请先运行 python get_scene_data.py")
        return []

    with open(profile_path, "r", encoding="utf-8") as f:
        profile = yaml.safe_load(f)

    objects = []
    for item in profile.get("scene", []):
        # 只加载可操作的小物体，不加载桌子、容器、位置（这些是场景自带的）
        if item.get("type") != "object":
            continue
        pos = item.get("position")
        if not pos or len(pos) < 3:
            continue

        category = item.get("category", item["name"])

        obj = dict(
            type="DatasetObject",
            name=item["name"],
            category=category,
            position=pos,
            orientation=[0, 0, 0, 1],
        )
        objects.append(obj)

    print(f"[OmniGibson] 从 profile.yaml 加载 {len(objects)} 个可操作物体")
    return objects


def init_omnigibson(scene_model="Rs_int", task_name=None):
    """初始化 OmniGibson 环境"""
    global env, robot, held_object, current_scene, current_task

    import yaml

    config_path = os.path.join(og.example_config_path, "tiago_primitives.yaml")
    with open(config_path, "r") as f:
        cfg = yaml.safe_load(f)

    cfg["scene"]["scene_model"] = scene_model

    if task_name:
        cfg["task"] = {
            "type": "BehaviorTask",
            "activity_name": task_name,
            "activity_definition_id": 0,
            "activity_instance_id": 0,
            "online_object_sampling": False,
        }
        print(f"[OmniGibson] 加载任务: {task_name}")
    else:
        cfg["task"] = {"type": "DummyTask"}
        print(f"[OmniGibson] 基础模式（场景自带物体）")

    print(f"[OmniGibson] 加载场景: {scene_model}")

    if env is not None:
        print("[OmniGibson] 销毁旧环境...")
        og.clear()

    env = og.Environment(configs=cfg)
    env.reset()

    current_scene = scene_model
    current_task = task_name
    held_object = None

    robot = env.robots[0]

    print("[OmniGibson] 可用物体:")
    for obj in env.scene.object_registry.objects:
        pos, _ = obj.get_position_orientation()
        print(f"  - {obj.name} ({obj.category}) @ [{pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}]")

    print(f"[OmniGibson] 初始化完成 (任务: {task_name or '无'})")


def find_object(name):
    """多策略物体查找，支持中英文名称"""
    if env is None:
        return None

    # 先尝试中文翻译
    search_name = ZH_EN_MAP.get(name, name)

    # 策略1: 精确名称匹配
    obj = env.scene.object_registry("name", search_name)
    if obj is not None:
        return obj

    # 策略2: 类别匹配
    try:
        objs = list(env.scene.object_registry("category", search_name))
        if objs:
            return objs[0]
    except Exception:
        pass

    # 策略3: 名称子串匹配
    for obj in env.scene.object_registry.objects:
        if search_name.lower() in obj.name.lower():
            return obj

    # 策略4: 类别子串匹配
    for obj in env.scene.object_registry.objects:
        if hasattr(obj, "category") and obj.category and search_name.lower() in obj.category.lower():
            return obj

    return None


def _sim_step(n=1):
    """推进仿真（仅在主线程中安全调用）"""
    for _ in range(n):
        og.sim.step()


def _execute_on_main(action_fn, timeout=300):
    """在主线程执行动作，等待结果（Flask 工作线程调用）"""
    import uuid
    req_id = str(uuid.uuid4())
    event = threading.Event()
    _action_queue.put((req_id, action_fn, event))
    event.wait(timeout=timeout)
    return _action_results.pop(req_id, {"success": False, "result": "执行超时"})


def _main_thread_loop():
    """主线程循环：处理动作队列 + 定期 step"""
    global record_frames
    print("[主线程] 动作处理循环已启动")
    while True:
        try:
            req_id, action_fn, event = _action_queue.get(timeout=0.1)
            try:
                result = action_fn()
                _action_results[req_id] = result
                # 同步持有的物体到 EEF 位置
                _sync_held_object()
                # 动作执行后 step 一次刷新渲染
                og.sim.step()
                # 录制帧
                if recording:
                    frame = _capture_frame_for_recording()
                    if frame is not None:
                        record_frames.append(frame)
                        print(f"[record] 帧 #{len(record_frames)}")
            except Exception as e:
                _action_results[req_id] = {"success": False, "result": str(e)}
            finally:
                event.set()
        except queue.Empty:
            pass


def _do_navigate(obj):
    """传送机器人到物体附近"""
    obj_pos, _ = obj.get_position_orientation()
    robot_pos = obj_pos.clone()
    robot_pos[0] -= 1.0
    robot_pos[2] = 0.0

    yaw = th.atan2(obj_pos[1] - robot_pos[1], obj_pos[0] - robot_pos[0])
    from omnigibson.utils.transform_utils import euler2quat
    robot_orn = euler2quat(th.tensor([0, 0, yaw]))

    robot.set_position_orientation(robot_pos, robot_orn)


def _do_grasp(obj):
    """抓取物体（传送到 EEF，不使用 OmniGibson 的辅助抓取机制）"""
    global held_object

    if held_object is not None:
        raise RuntimeError("已经抓取了物体，请先释放")

    arm = robot.default_arm
    eef_pos = robot.get_eef_position(arm)
    obj.set_position_orientation(position=eef_pos)

    # 只用全局变量追踪，不设置 robot._ag_obj_in_hand（避免触发辅助抓取机制）
    held_object = obj.name


def _do_release():
    """释放物体"""
    global held_object

    if held_object is None:
        raise RuntimeError("没有抓取任何物体")

    held_object = None


def _sync_held_object():
    """将持有的物体同步到 EEF 位置（每个物理步进调用）"""
    if held_object is None:
        return
    obj = find_object(held_object)
    if obj is None:
        return
    arm = robot.default_arm
    eef_pos = robot.get_eef_position(arm)
    obj.set_position_orientation(position=eef_pos)


def _do_place_on_top(target_obj):
    """把抓取的物体放在目标上面（传送）"""
    global held_object

    if held_object is None:
        raise RuntimeError("没有抓取任何物体，无法放置")

    obj = find_object(held_object)
    if obj is None:
        raise RuntimeError("找不到持有的物体")

    # 计算目标上方位置
    target_pos, _ = target_obj.get_position_orientation()
    target_bbox = target_obj.aabb
    if target_bbox is not None:
        top_z = float(target_bbox[1][2])  # 最高点
    else:
        top_z = float(target_pos[2]) + 0.5
    place_pos = target_pos.clone()
    place_pos[2] = top_z + 0.05  # 略高于顶部

    obj.set_position_orientation(position=place_pos)
    held_object = None


def _do_place_inside(target_obj):
    """把抓取的物体放入目标内部（传送）"""
    global held_object

    if held_object is None:
        raise RuntimeError("没有抓取任何物体，无法放置")

    obj = find_object(held_object)
    if obj is None:
        raise RuntimeError("找不到持有的物体")

    # 放到目标中心位置
    target_pos, _ = target_obj.get_position_orientation()
    target_bbox = target_obj.aabb
    if target_bbox is not None:
        center = (target_bbox[0] + target_bbox[1]) / 2
        center[2] = float(target_bbox[0][2]) + 0.1  # 底部稍上方
    else:
        center = target_pos.clone()
    obj.set_position_orientation(position=center)

    held_object = None


def _do_open(obj):
    """打开物体"""
    obj.states[object_states.Open].set_value(True)


def _do_close(obj):
    """关闭物体"""
    obj.states[object_states.Open].set_value(False)


# ============ 辅助函数 ============


def capture_image(sensor):
    """从 VisionSensor 捕获 RGB 图像并编码为 PNG bytes"""
    import numpy as np
    import cv2

    obs, _ = sensor.get_obs()
    rgb = obs.get("rgb")
    if rgb is None:
        return None
    if rgb.shape[-1] == 4:
        rgb = rgb[..., :3]
    try:
        arr = rgb.cpu().numpy()
    except AttributeError:
        arr = np.array(rgb)
    arr = arr.astype("uint8")
    arr_bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    success, encoded = cv2.imencode(".png", arr_bgr)
    if not success:
        return None
    buf = io.BytesIO(encoded.tobytes())
    buf.seek(0)
    return buf


def _capture_frame_for_recording():
    """捕获一帧 RGB numpy 数组用于录制（不 step，直接取当前渲染状态）"""
    import numpy as np
    try:
        cam = og.sim.viewer_camera
        obs, _ = cam.get_obs()
        rgb = obs.get("rgb")
        if rgb is None:
            cam = _get_robot_camera()
            if cam is None:
                return None
            obs, _ = cam.get_obs()
            rgb = obs.get("rgb")
            if rgb is None:
                return None
        if rgb.shape[-1] == 4:
            rgb = rgb[..., :3]
        try:
            arr = rgb.cpu().numpy()
        except AttributeError:
            arr = np.array(rgb)
        return arr.astype("uint8")
    except Exception:
        return None


def _after_action(action_name):
    """动作执行后的钩子：录制帧 + 打印日志"""
    global record_frames
    if recording:
        frame = _capture_frame_for_recording()
        if frame is not None:
            record_frames.append(frame)
            print(f"[record] 录制帧 #{len(record_frames)} ({action_name})")


def _save_recording():
    """保存录制的帧为 mp4 视频"""
    import imageio
    import os
    global record_frames
    if not record_frames:
        return None
    os.makedirs(record_dir, exist_ok=True)
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    fpath = os.path.join(record_dir, f"task_{timestamp}.mp4")
    writer = imageio.get_writer(fpath, fps=1)
    for frame in record_frames:
        writer.append_data(frame)
    writer.close()
    n_frames = len(record_frames)
    record_frames = []
    print(f"[record] 视频已保存: {fpath} ({n_frames} 帧)")
    return fpath
    return path_saved


def get_object_category_type(category):
    if category in TABLE_CATEGORIES:
        return "table"
    elif category in CONTAINER_CATEGORIES:
        return "container"
    return None


def build_scene_profile():
    """根据当前场景物体生成 profile.yaml 格式数据"""
    tables = []
    containers = []
    standalone = []

    for obj in env.scene.object_registry.objects:
        category = getattr(obj, "category", "")
        name = obj.name

        if category in ("ceilings", "floors", "walls", "agent"):
            continue
        if category in ("door", "openable_window", "electric_switch",
                         "floor_lamp", "table_lamp", "mirror", "picture",
                         "towel_rack", "shower_stall", "toilet",
                         "pedestal_sink", "furniture_sink", "carpet"):
            continue

        pos, _ = obj.get_position_orientation()
        obj_type = get_object_category_type(category)

        entry = {
            "name": name,
            "category": category,
            "type": obj_type,
            "position": [round(p, 2) for p in pos.tolist()],
            "description": category.replace("_", " "),
        }

        if obj_type == "table":
            tables.append(entry)
        elif obj_type == "container":
            containers.append(entry)
        else:
            standalone.append(entry)

    locations = [
        {"name": "livingRoom", "type": "location", "position": [0.0, 0.4, 0.0], "description": "客厅"},
        {"name": "bedroom", "type": "location", "position": [0.0, 0.8, 0.0], "description": "卧室"},
        {"name": "kitchen", "type": "location", "position": [0.4, 0.0, 0.0], "description": "厨房"},
        {"name": "bathroom", "type": "location", "position": [0.4, 0.8, 0.0], "description": "浴室"},
        {"name": "entrance", "type": "location", "position": [0.0, 0.0, 0.0], "description": "入口"},
    ]

    return {
        "tables": tables,
        "containers": containers,
        "standalone_objects": standalone,
        "locations": locations,
    }


def _get_robot_camera():
    from omnigibson.sensors import VisionSensor
    cameras = [s for s in robot.sensors.values() if isinstance(s, VisionSensor)]
    return cameras[0] if cameras else None


def _capture_viewer():
    try:
        cam = og.sim.viewer_camera
        img_buf = capture_image(cam)
        if img_buf is not None:
            return img_buf, "viewer"
    except Exception:
        pass
    cam = _get_robot_camera()
    if cam is not None:
        img_buf = capture_image(cam)
        if img_buf is not None:
            return img_buf, "robot"
    return None, None


def _capture_top_down():
    """捕获俯视视角截图"""
    try:
        import torch

        cam = og.sim.viewer_camera
        # 保存原始位置
        original_pos, original_ori = cam.get_position_orientation()

        # 设置俯视位置（场景上方，朝下看）
        # 场景中心大约在 [0, 0, 0]，上方 8 米
        top_down_pos = torch.tensor([0.0, 0.0, 8.0])

        # 朝下看：使用正确的四元数
        # OmniGibson 四元数格式：(x, y, z, w)
        # 绕 X 轴旋转 180 度：(1, 0, 0, 0)
        top_down_ori = torch.tensor([1.0, 0.0, 0.0, 0.0])

        # 设置相机位置
        cam.set_position_orientation(top_down_pos, top_down_ori)

        # 强制更新渲染
        og.sim.render()

        # 多步渲染确保图像更新
        for _ in range(5):
            og.sim.step()
            og.sim.render()

        img_buf = capture_image(cam)

        # 恢复原始位置
        cam.set_position_orientation(original_pos, original_ori)
        og.sim.render()

        return img_buf
    except Exception as e:
        print(f"[OmniGibson] 俯视截图失败: {e}")
        import traceback
        traceback.print_exc()
        return None


# ============ API 端点 ============


@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "success": True,
        "status": "running",
        "scene": current_scene,
        "task": current_task,
        "held_object": held_object,
    })


@app.route("/objects", methods=["GET"])
def list_objects():
    category = request.args.get("category")
    name = request.args.get("name")

    objects = []
    for obj in env.scene.object_registry.objects:
        obj_category = obj.category if hasattr(obj, "category") else None
        obj_info = {"name": obj.name, "category": obj_category}

        if category and obj_category != category:
            continue
        if name and name.lower() not in obj.name.lower():
            continue

        objects.append(obj_info)

    return jsonify({"success": True, "objects": objects, "count": len(objects)})


@app.route("/robot/state", methods=["GET"])
def robot_state():
    pos, ori = robot.get_position_orientation()
    return jsonify({
        "success": True,
        "position": pos.tolist(),
        "orientation": ori.tolist(),
        "held_object": held_object,
    })


@app.route("/task/list", methods=["GET"])
def task_list():
    task_filter = request.args.get("filter", "")

    try:
        from bddl.activity import get_all_activities
        activities = sorted(get_all_activities())
    except Exception:
        import glob
        bddl_base = os.path.join(os.path.dirname(og.__file__), "..", "bddl3", "bddl", "activity_definitions")
        if not os.path.isdir(bddl_base):
            bddl_base = "/home/fangqi/WorkXCJ/BEHAVIOR-1K/bddl3/bddl/activity_definitions"
        if os.path.isdir(bddl_base):
            activities = sorted(os.listdir(bddl_base))
        else:
            activities = []

    if task_filter:
        activities = [a for a in activities if task_filter.lower() in a.lower()]

    return jsonify({"success": True, "tasks": activities, "count": len(activities)})


@app.route("/task/current", methods=["GET"])
def task_current():
    info = {
        "success": True,
        "scene": current_scene,
        "task": current_task,
        "held_object": held_object,
    }
    if env and hasattr(env, "task") and hasattr(env.task, "activity_name"):
        info["activity_name"] = env.task.activity_name
    return jsonify(info)


@app.route("/task/load", methods=["POST"])
def task_load():
    global held_object

    data = request.get_json() or {}
    task_name = data.get("task_name", "")
    scene_name = data.get("scene", current_scene or "Rs_int")

    if not task_name:
        return jsonify({"success": False, "result": "缺少 task_name 参数"})

    print(f"[API] 加载任务: {task_name} (场景: {scene_name})")

    try:
        held_object = None
        init_omnigibson(scene_name, task_name)

        objects = []
        for obj in env.scene.object_registry.objects:
            cat = getattr(obj, "category", None)
            if cat in ("ceilings", "floors", "walls", "agent"):
                continue
            objects.append({"name": obj.name, "category": cat})

        return jsonify({
            "success": True,
            "result": f"已加载任务: {task_name}",
            "task": task_name,
            "scene": scene_name,
            "objects": objects,
            "object_count": len(objects),
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "result": f"加载任务失败: {str(e)}"})


@app.route("/scene/profile", methods=["GET"])
def scene_profile():
    try:
        profile = build_scene_profile()
        return jsonify({"success": True, "profile": profile})
    except Exception as e:
        return jsonify({"success": False, "result": str(e)})


@app.route("/camera/viewer", methods=["GET"])
def camera_viewer():
    def do():
        og.sim.step()  # 刷新渲染
        img_buf, source = _capture_viewer()
        if img_buf is None:
            return {"success": False, "result": "无法获取截图", "_binary": None}
        return {"success": True, "_binary": img_buf}
    result = _execute_on_main(do)
    if not result.get("success"):
        return jsonify(result)
    return send_file(result["_binary"], mimetype="image/png")


@app.route("/camera/robot", methods=["GET"])
def camera_robot():
    def do():
        og.sim.step()
        cam = _get_robot_camera()
        if cam is None:
            return {"success": False, "result": "机器人没有摄像头传感器", "_binary": None}
        img_buf = capture_image(cam)
        if img_buf is None:
            return {"success": False, "result": "无法获取机器人视角", "_binary": None}
        return {"success": True, "_binary": img_buf}
    result = _execute_on_main(do)
    if not result.get("success"):
        return jsonify(result)
    return send_file(result["_binary"], mimetype="image/png")


@app.route("/camera/viewer_base64", methods=["GET"])
def camera_viewer_base64():
    def do():
        og.sim.step()
        img_buf, source = _capture_viewer()
        if img_buf is None:
            return {"success": False, "result": "无法获取截图"}
        b64 = base64.b64encode(img_buf.read()).decode("utf-8")
        return {"success": True, "image": b64, "format": "png", "source": source}
    return jsonify(_execute_on_main(do))


@app.route("/camera/robot_base64", methods=["GET"])
def camera_robot_base64():
    def do():
        og.sim.step()
        cam = _get_robot_camera()
        if cam is None:
            return {"success": False, "result": "机器人没有摄像头传感器"}
        img_buf = capture_image(cam)
        if img_buf is None:
            return {"success": False, "result": "无法获取机器人视角"}
        b64 = base64.b64encode(img_buf.read()).decode("utf-8")
        return {"success": True, "image": b64, "format": "png"}
    return jsonify(_execute_on_main(do))


@app.route("/camera/top_down", methods=["GET"])
def camera_top_down():
    """俯视视角截图"""
    def do():
        og.sim.step()
        img_buf = _capture_top_down()
        if img_buf is None:
            return {"success": False, "result": "无法获取俯视截图", "_binary": None}
        return {"success": True, "_binary": img_buf}
    result = _execute_on_main(do)
    if not result.get("success"):
        return jsonify(result)
    return send_file(result["_binary"], mimetype="image/png")


@app.route("/camera/top_down_base64", methods=["GET"])
def camera_top_down_base64():
    """俯视视角截图（base64）"""
    def do():
        og.sim.step()
        img_buf = _capture_top_down()
        if img_buf is None:
            return {"success": False, "result": "无法获取俯视截图"}
        b64 = base64.b64encode(img_buf.read()).decode("utf-8")
        return {"success": True, "image": b64, "format": "png"}
    return jsonify(_execute_on_main(do))


# ============ 仿真控制端点 ============


@app.route("/sim/step", methods=["POST"])
def sim_step():
    """推进仿真一步（通过主线程执行）"""
    def do():
        _sim_step(1)
        return {"success": True, "result": "仿真已推进一步"}
    return jsonify(_execute_on_main(do))


@app.route("/sim/step_and_capture", methods=["POST"])
def sim_step_and_capture():
    """推进仿真一步并返回截图（通过主线程执行）"""
    def do():
        _sim_step(1)
        img_buf = capture_image(og.sim.viewer_camera)
        if img_buf is None:
            return {"success": False, "result": "无法获取截图"}
        b64 = base64.b64encode(img_buf.read()).decode("utf-8")
        return {"success": True, "image": b64, "format": "png"}
    return jsonify(_execute_on_main(do))


# ============ 录制端点 ============


@app.route("/record/start", methods=["POST"])
def record_start():
    global recording, record_frames
    recording = True
    record_frames = []
    return jsonify({"success": True, "result": "录制已开始"})


@app.route("/record/stop", methods=["POST"])
def record_stop():
    global recording
    recording = False
    fpath = _save_recording()
    if fpath:
        return jsonify({"success": True, "result": f"录制已停止，视频保存到: {fpath}"})
    return jsonify({"success": False, "result": "没有录制任何帧"})


@app.route("/record/status", methods=["GET"])
def record_status():
    return jsonify({
        "success": True,
        "recording": recording,
        "frames": len(record_frames),
    })


# ============ Action 端点（通过主线程队列执行） ============


@app.route("/action/navigate", methods=["POST"])
def action_navigate():
    data = request.get_json() or {}
    target_name = data.get("target_name", "")
    print(f"[API] navigate {target_name}")

    def do():
        obj = find_object(target_name)
        if obj is None:
            return {"success": False, "result": f"物体 '{target_name}' 不在场景中"}
        _do_navigate(obj)
        robot_pos, _ = robot.get_position_orientation()
        coords = [round(float(p), 2) for p in robot_pos]
        return {"success": True, "result": json.dumps(
            [f"成功导航到 {target_name}", {"position": target_name, "coordinates": coords}],
            ensure_ascii=False)}

    return jsonify(_execute_on_main(do))


@app.route("/action/grasp", methods=["POST"])
def action_grasp():
    data = request.get_json() or {}
    object_name = data.get("object_name", "")
    print(f"[API] grasp {object_name}")

    def do():
        obj = find_object(object_name)
        if obj is None:
            return {"success": False, "result": f"物体 '{object_name}' 不在场景中"}
        _do_grasp(obj)
        return {"success": True, "result": json.dumps(
            [f"成功抓取了 {object_name}", {"holding": obj.name}],
            ensure_ascii=False)}

    return jsonify(_execute_on_main(do))


@app.route("/action/place_on_top", methods=["POST"])
def action_place_on_top():
    data = request.get_json() or {}
    target_name = data.get("target_name", "")
    print(f"[API] place_on_top {target_name}")

    def do():
        obj = find_object(target_name)
        if obj is None:
            return {"success": False, "result": f"物体 '{target_name}' 不在场景中"}
        old_held = held_object
        _do_place_on_top(obj)
        return {"success": True, "result": json.dumps(
            [f"成功将 {old_held} 放在 {target_name} 上面", {"holding": None}],
            ensure_ascii=False)}

    return jsonify(_execute_on_main(do))


@app.route("/action/place_inside", methods=["POST"])
def action_place_inside():
    data = request.get_json() or {}
    target_name = data.get("target_name", "")
    print(f"[API] place_inside {target_name}")

    def do():
        obj = find_object(target_name)
        if obj is None:
            return {"success": False, "result": f"物体 '{target_name}' 不在场景中"}
        old_held = held_object
        _do_place_inside(obj)
        return {"success": True, "result": json.dumps(
            [f"成功将 {old_held} 放入 {target_name} 内部", {"holding": None}],
            ensure_ascii=False)}

    return jsonify(_execute_on_main(do))


@app.route("/action/open", methods=["POST"])
def action_open():
    data = request.get_json() or {}
    target_name = data.get("target_name", "")
    print(f"[API] open {target_name}")

    def do():
        obj = find_object(target_name)
        if obj is None:
            return {"success": False, "result": f"物体 '{target_name}' 不在场景中"}
        _do_open(obj)
        return {"success": True, "result": json.dumps(
            [f"成功打开了 {target_name}", {"position": target_name}],
            ensure_ascii=False)}

    return jsonify(_execute_on_main(do))


@app.route("/action/close", methods=["POST"])
def action_close():
    data = request.get_json() or {}
    target_name = data.get("target_name", "")
    print(f"[API] close {target_name}")

    def do():
        obj = find_object(target_name)
        if obj is None:
            return {"success": False, "result": f"物体 '{target_name}' 不在场景中"}
        _do_close(obj)
        return {"success": True, "result": json.dumps(
            [f"成功关闭了 {target_name}", {"position": target_name}],
            ensure_ascii=False)}

    return jsonify(_execute_on_main(do))


@app.route("/action/release", methods=["POST"])
def action_release():
    print("[API] release")

    def do():
        old_held = held_object
        _do_release()
        return {"success": True, "result": json.dumps(
            [f"成功释放了 {old_held}", {"holding": None}],
            ensure_ascii=False)}

    return jsonify(_execute_on_main(do))


if __name__ == "__main__":
    import sys

    scene = sys.argv[1] if len(sys.argv) > 1 else "Rs_int"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 5001
    task = sys.argv[3] if len(sys.argv) > 3 else None

    print("=" * 60)
    print("OmniGibson HTTP Server (Direct State Manipulation)")
    print(f"场景: {scene}  端口: {port}")
    if task:
        print(f"任务: {task}")
    else:
        print("任务: 无（基础模式，只有家具）")
    print("=" * 60)

    init_omnigibson(scene, task)

    print(f"\n服务器启动: http://127.0.0.1:{port}")
    print("按 Ctrl+C 停止")
    print("=" * 60)

    # Flask 放后台线程，主线程跑动作队列
    flask_thread = threading.Thread(target=lambda: app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False), daemon=True)
    flask_thread.start()

    # 主线程处理动作队列 + sim.step()
    _main_thread_loop()
