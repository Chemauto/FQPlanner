"""
utils.py - 纯 MuJoCo 场景工具函数
"""

import numpy as np

from mujoco_backend import MujocoKitchenEnv


def create_scene(scene_dir="scene", seed=42):
    """从本地 scene/config 创建纯 MuJoCo 厨房场景。"""
    return MujocoKitchenEnv(scene_dir=scene_dir, seed=seed)


def init_device(env, device_type="keyboard"):
    raise NotImplementedError("纯 MuJoCo 后端暂不使用 robosuite 设备接口")


def run_interactive(env, device):
    raise NotImplementedError("纯 MuJoCo 后端暂不使用 robosuite 遥操作循环")


def get_all_fixtures(env):
    return list(env.fixtures.keys())


def get_fixture_pos(env, name):
    results = {}
    for n, fxtr in env.fixtures.items():
        if name in n:
            results[n] = np.array(fxtr.pos, dtype=float)
    return results


def get_fixture_size(env, name):
    results = {}
    for n, fxtr in env.fixtures.items():
        if name in n:
            results[n] = np.array(fxtr.size, dtype=float)
    return results


def get_fixture_detail(env, name):
    results = {}
    for n, fxtr in env.fixtures.items():
        if name in n:
            results[n] = {
                "pos": np.array(fxtr.pos, dtype=float),
                "size": np.array(fxtr.size, dtype=float),
                "type": fxtr.type,
            }
    return results


def get_robot_ee_pos(env):
    return env.get_body_pos("Fixed_Jaw_2", fallback="Moving_Jaw_2")


def get_robot_base_pos(env):
    return env.get_body_pos("chassis")


def print_fixtures(env):
    print(f"\n{'名称':<42s} {'类型':<20s} {'位置 [x,y,z]':<30s} {'尺寸 [宽,深,高]'}")
    print("-" * 130)
    for name, fxtr in env.fixtures.items():
        pos = np.array2string(np.array(fxtr.pos, dtype=float), precision=3)
        size = np.array2string(np.array(fxtr.size, dtype=float), precision=3)
        print(f"  {name:<40s} {fxtr.type:<20s} {pos:<30s} {size}")


def print_summary(env):
    print("\n关键家具位置:")
    for label, kw in {
        "台面": "counter",
        "炉灶": "stove",
        "水槽": "sink",
        "橱柜": "cab",
        "岛台": "island",
    }.items():
        for n in [n for n in env.fixtures if kw in n.lower()][:3]:
            pos = np.array2string(np.array(env.fixtures[n].pos, dtype=float), precision=3)
            print(f"  {label} {n}: {pos}")

    ee_pos = np.array2string(get_robot_ee_pos(env), precision=3)
    print(f"\n机器人末端位置: {ee_pos}")

