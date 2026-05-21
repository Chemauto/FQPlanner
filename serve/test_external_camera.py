"""
测试独立外部相机 - 第一步：和机器人相机同参数，验证能拿到图像
"""
import os
os.environ["OMNIGIBSON_HEADLESS"] = "True"

import torch as th
import omnigibson as og
from omnigibson.macros import gm

gm.USE_GPU_DYNAMICS = False
gm.ENABLE_FLATCACHE = True

import yaml
import cv2

config_path = os.path.join(og.example_config_path, "tiago_primitives.yaml")
with open(config_path, "r") as f:
    cfg = yaml.safe_load(f)

cfg["scene"]["scene_model"] = "Rs_int"
cfg["task"] = {"type": "DummyTask"}

# 添加外部传感器 - 放在 cfg["env"] 下面
cfg["env"]["external_sensors"] = [
    {
        "sensor_type": "VisionSensor",
        "name": "external_top_down",
        "relative_prim_path": "/external_top_down",
        "modalities": ["rgb"],
        "sensor_kwargs": {
            "image_height": 128,
            "image_width": 128,
        },
        "position": [0, 0, 1.5],  # 先放机器人头顶高度附近
        "orientation": [0, 0, 0, 1],  # 默认朝向（和机器人相机一样）
        "pose_frame": "scene",
    }
]

print("[TEST] 初始化环境（带外部传感器）...")
env = og.Environment(configs=cfg)
env.reset()

robot = env.robots[0]
print(f"[TEST] 机器人: {robot.name}")

# 检查外部传感器是否加载成功
if hasattr(env, '_external_sensors'):
    print(f"[TEST] 外部传感器: {list(env._external_sensors.keys())}")
    ext_cam = env._external_sensors.get("external_top_down")
    if ext_cam is not None:
        print(f"[TEST] 外部相机已加载: {ext_cam.name}")

        # 推进几步让传感器有数据
        for _ in range(5):
            og.sim.step()

        # 获取外部相机图像
        obs, _ = ext_cam.get_obs()
        print(f"[TEST] 外部相机 obs keys: {list(obs.keys())}")
        rgb = obs.get("rgb")
        if rgb is not None:
            print(f"[TEST] 外部相机 RGB shape: {rgb.shape}, dtype: {rgb.dtype}")

            # 保存图像
            import numpy as np
            arr = rgb.cpu().numpy() if hasattr(rgb, 'cpu') else np.array(rgb)
            if arr.shape[-1] == 4:
                arr = arr[..., :3]
            arr = arr.astype("uint8")
            arr_bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

            save_path = "/home/fangqi/WorkXCJ/FQPlanner/serve/test_external_camera.png"
            cv2.imwrite(save_path, arr_bgr)
            print(f"[TEST] 外部相机图像已保存: {save_path}")
        else:
            print("[TEST] 外部相机 RGB 为 None!")
    else:
        print("[TEST] 未找到 external_top_down 传感器")
else:
    print("[TEST] env 没有 _external_sensors 属性")

# 对比：获取机器人相机图像
from omnigibson.sensors import VisionSensor
robot_cams = [s for s in robot.sensors.values() if isinstance(s, VisionSensor)]
if robot_cams:
    robot_cam = robot_cams[0]
    obs, _ = robot_cam.get_obs()
    rgb = obs.get("rgb")
    if rgb is not None:
        import numpy as np
        arr = rgb.cpu().numpy() if hasattr(rgb, 'cpu') else np.array(rgb)
        if arr.shape[-1] == 4:
            arr = arr[..., :3]
        arr = arr.astype("uint8")
        arr_bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

        save_path = "/home/fangqi/WorkXCJ/FQPlanner/serve/test_robot_camera.png"
        cv2.imwrite(save_path, arr_bgr)
        print(f"[TEST] 机器人相机图像已保存: {save_path}")
        print(f"[TEST] 机器人相机 RGB shape: {rgb.shape}")

print("[TEST] 完成")
og.clear()
