"""
make_scene.py - 纯 MuJoCo 场景生成兼容入口

保留文件名是为了兼容旧导入；运行时不再依赖 RoboCasa。
"""

from mujoco_backend import build_scene_xml


def make_scene_xml(scene_dir):
    return build_scene_xml(scene_dir)

