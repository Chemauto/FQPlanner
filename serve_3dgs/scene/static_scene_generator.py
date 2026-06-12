"""
static_scene_generator.py - 静态场景生成器（不依赖 RoboCasa）

将 MuJoCo-GS-Web 的环境 XML 与 XLeRobot 合并，
生成 FQPlanner 可直接加载的 scene.xml 和 scene_meta.json。
"""

import json
import os
import xml.etree.ElementTree as ET

import numpy as np


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
XLEROBOT_DIR = os.path.join(ROOT_DIR, "assets", "xlerobot")
SCENE_ASSET_DIR = os.path.join(ROOT_DIR, "assets", "scene_3dgs")
XLEROBOT_XML = os.path.join(XLEROBOT_DIR, "xlerobot.xml")
GENERATED_SCENE = os.path.join(SCENE_ASSET_DIR, "scene.xml")
GENERATED_META = os.path.join(SCENE_ASSET_DIR, "scene_meta.json")

# MuJoCo-GS-Web 项目中环境文件的默认路径
GSWEB_ROOT = os.path.join(os.path.dirname(ROOT_DIR), "MuJoCo-GS-Web")
GSWEB_ENVS = {
    "tabletop": os.path.join(GSWEB_ROOT, "assets", "environments", "tabletop", "scene.xml"),
    "ufc": os.path.join(GSWEB_ROOT, "assets", "environments", "UFC", "scene.xml"),
    "basic": os.path.join(GSWEB_ROOT, "assets", "environments", "basic.xml"),
}


def build_static_scene(env_name="tabletop", env_xml_path=None, output_dir=None):
    """
    静态场景生成主入口。

    Parameters:
        env_name: GS-Web 环境名称 ("tabletop", "ufc", "basic")
        env_xml_path: 自定义环境 XML 路径（优先于 env_name）
        output_dir: 输出目录（默认 assets/scene/）

    Returns:
        (scene_xml_path, meta_json_path)
    """
    # 确定环境 XML 路径
    if env_xml_path:
        xml_path = env_xml_path
    elif env_name in GSWEB_ENVS:
        xml_path = GSWEB_ENVS[env_name]
    else:
        raise ValueError(f"Unknown env_name: {env_name}. Available: {list(GSWEB_ENVS.keys())}")

    if not os.path.exists(xml_path):
        raise FileNotFoundError(f"Environment XML not found: {xml_path}")

    if output_dir is None:
        output_dir = SCENE_ASSET_DIR

    scene_xml = os.path.join(output_dir, "scene.xml")
    meta_json = os.path.join(output_dir, "scene_meta.json")

    # 解析环境 XML 和机器人 XML
    env_root = ET.parse(xml_path).getroot()
    robot_root = ET.parse(XLEROBOT_XML).getroot()

    # 将环境的 worldbody 内容合并到机器人 XML
    _merge_env_into_robot(robot_root, env_root)

    # 后处理
    _set_compiler_paths(robot_root)
    _add_cameras(robot_root)
    _set_statistic(robot_root)
    _set_robot_initial_pose(robot_root)
    _add_missing_robot_inertials(robot_root)
    _set_physics_options(robot_root)

    # 写出文件
    os.makedirs(output_dir, exist_ok=True)
    _indent(robot_root)
    ET.ElementTree(robot_root).write(scene_xml, encoding="utf-8", xml_declaration=True)

    # 生成空的 meta（无物体、无家具）
    meta = {"fixtures": [], "objects": []}
    with open(meta_json, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"[static_scene] 生成完成: {scene_xml}")
    print(f"[static_scene] 环境: {env_name} ({xml_path})")
    return scene_xml, meta_json


def _merge_env_into_robot(robot_root, env_root):
    """
    将 GS-Web 环境 XML 的内容合并到机器人 XML 中。

    合并 asset（材质/纹理）、worldbody（碰撞体）、default 等节点。
    """
    # 合并 <asset>
    src_asset = env_root.find("asset")
    if src_asset is not None:
        dst_asset = robot_root.find("asset")
        if dst_asset is None:
            dst_asset = ET.SubElement(robot_root, "asset")
        existing = {(c.tag, c.get("name")) for c in dst_asset if c.get("name")}
        for child in list(src_asset):
            name = child.get("name")
            key = (child.tag, name)
            if name and key in existing:
                continue
            dst_asset.append(child)
            if name:
                existing.add(key)

    # 合并 <worldbody>
    src_world = env_root.find("worldbody")
    dst_world = robot_root.find("worldbody")
    if src_world is not None and dst_world is not None:
        for child in list(src_world):
            # 跳过已有的同名 body/geom
            name = child.get("name")
            if name and dst_world.find(f".//*[@name='{name}']") is not None:
                continue
            # GS-Web 环境用 group=3（原设计是隐形碰撞体，靠 3DGS 做视觉）
            # 在 FQPlanner 中无 3DGS，需要改成 group=1 才能在 viewer 中显示
            _make_geom_visible(child)
            dst_world.append(child)

    # 不合并 <default>：XLeRobot 已有完整的 default 定义，
    # GS-Web 的 default 里有同 tag 无名 geom 会与 XLeRobot 冲突。

    # 合并 <visual>
    src_visual = env_root.find("visual")
    if src_visual is not None:
        dst_visual = robot_root.find("visual")
        if dst_visual is None:
            dst_visual = ET.SubElement(robot_root, "visual")
        for attr, val in src_visual.items():
            if dst_visual.get(attr) is None:
                dst_visual.set(attr, val)
        for child in list(src_visual):
            existing = dst_visual.find(child.tag)
            if existing is None:
                dst_visual.append(child)


def _set_compiler_paths(root):
    """设置 meshdir 指向 xlerobot 目录。"""
    compiler = root.find("compiler")
    if compiler is None:
        compiler = ET.SubElement(root, "compiler")
    compiler.set("angle", "radian")
    compiler.set("meshdir", "../xlerobot/")


def _add_cameras(root):
    """添加全局顶视相机。"""
    world = root.find("worldbody")
    if world is None:
        return
    existing = world.find(".//camera[@name='overhead_cam']")
    if existing is None:
        ET.SubElement(world, "camera", {
            "name": "overhead_cam",
            "pos": "0 0 5",
            "xyaxes": "1 0 0 0 0 1",
            "fovy": "60",
        })


def _set_statistic(root):
    """设置 MuJoCo viewer 默认视角。"""
    statistic = root.find("statistic")
    if statistic is None:
        statistic = ET.SubElement(root, "statistic")
    statistic.set("center", "0 0 0.5")
    statistic.set("extent", "3")


def _set_robot_initial_pose(root):
    """设置机器人初始位置在场景中央。"""
    chassis = root.find(".//body[@name='chassis']")
    if chassis is None:
        return
    current_pos = [float(v) for v in chassis.get("pos", "0 0 0.035").split()]
    z = current_pos[2] if len(current_pos) >= 3 else 0.035
    chassis.set("pos", f"0 0 {z}")


def _add_missing_robot_inertials(root):
    """给缺少 inertial 的机器人相机 body 补充极小惯量。"""
    for name in (
        "Right_Arm_Camera",
        "Left_Arm_Camera",
        "head_camera_link",
        "head_camera_rgb_frame",
        "head_camera_depth_frame",
    ):
        body = root.find(f".//body[@name='{name}']")
        if body is None or body.find("inertial") is not None:
            continue
        ET.SubElement(body, "inertial", {
            "pos": "0 0 0",
            "mass": "0.001",
            "diaginertia": "1e-6 1e-6 1e-6",
        })


def _set_physics_options(root):
    """设置物理参数。"""
    option = root.find("option")
    if option is None:
        option = ET.SubElement(root, "option")
    option.set("timestep", "0.002")
    option.set("gravity", "0 0 -9.80665")
    option.set("integrator", "implicitfast")

    size = root.find("size")
    if size is None:
        size = ET.SubElement(root, "size")
    size.set("nconmax", "5000")
    size.set("njmax", "5000")


def _indent(elem, level=0):
    """递归缩进 XML 元素。"""
    i = "\n" + level * "  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        for child in elem:
            _indent(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = i
    if level and (not elem.tail or not elem.tail.strip()):
        elem.tail = i


def _make_geom_visible(elem):
    """递归将 geom 的 group=3 改为 group=1，使其在 viewer 中可见。"""
    if elem.tag == "geom" and elem.get("group") == "3":
        elem.set("group", "1")
        # 同时把透明度调高，让碰撞体可见
        rgba = elem.get("rgba")
        if rgba and rgba.endswith("0.01"):
            elem.set("rgba", rgba.replace("0.01", "0.5"))
    for child in elem:
        _make_geom_visible(child)
