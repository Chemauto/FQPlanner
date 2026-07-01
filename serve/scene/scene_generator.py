"""
scene_generator.py - 厨房场景生成器

职责：
  读取 scene/config 下的配置文件（layout/style/objects/waypoints），
  调用 RoboCasa 生成真实厨房几何和物体模型，合并 XLeRobot 机器人，
  输出最终的 MuJoCo 场景 XML 和元信息 JSON。

输入：
  serve/scene/config/layout.yaml   — 房间布局（墙壁、地面、家具位置）
  serve/scene/config/style.yaml    — 外观风格（材质、颜色、型号）
  serve/scene/config/objects.yaml  — 物体列表（名称、类别、放置规则）
  serve/scene/config/waypoints.yaml — 导航工作点
  assets/xlerobot/xlerobot.xml     — XLeRobot 机器人模型

输出：
  assets/scene/scene.xml           — 合并后的 MuJoCo 场景
  assets/scene/scene_meta.json     — 物体和家具的名称/位置/尺寸元信息

使用：
  from scene.scene_generator import build_scene_xml
  scene_xml = build_scene_xml("serve/scene", seed=42)
"""

import json
import os
import xml.etree.ElementTree as ET

import numpy as np
import yaml


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCENE_ASSET_DIR = os.path.join(ROOT_DIR, "assets", "scene")
GENERATED_SCENE = os.path.join(SCENE_ASSET_DIR, "scene.xml")
GENERATED_META = os.path.join(SCENE_ASSET_DIR, "scene_meta.json")

# 机器人:PandaOmron(Franka Panda 臂 + Omron 移动底座),robosuite 原生装配。
# 底座用 Option F——给 robot0_base 加 freejoint、剥离 3 个移动关节 → 复用现有 freejoint 运动学 nav。
ROBOT_NAME = "PandaOmron"
ROBOT_START_XY = (3.2, -1.5)               # 初始底座 x/y(岛台与台面之间)
BASE_FREEJOINT = "base_freejoint"          # 加在 robot0_base 上,backend 按名找它
_BASE_PLANAR_JOINTS = (                     # 要剥离的 Omron 平面移动关节(被 freejoint 取代)
    "mobilebase0_joint_mobile_forward",
    "mobilebase0_joint_mobile_side",
    "mobilebase0_joint_mobile_yaw",
)


# ============================================================
# 主入口
# ============================================================

def build_scene_xml(scene_dir, seed=42):
    """
    场景生成主入口。

    流程：
      1. 加载配置文件
      2. 用 RoboCasa 创建厨房 Arena（墙壁、地板、固定家具）
      3. 按配置放置物体（pot/cup/apple 等）
      4. 导出厨房 MJCF，合并到 XLeRobot XML
      5. 后处理：相机、初始位姿、碰撞修复、隐藏非视觉几何
      6. 写出 scene.xml 和 scene_meta.json
    """
    os.environ.setdefault("NUMBA_DISABLE_JIT", "1")

    from robocasa.models.objects.kitchen_object_utils import sample_kitchen_object
    from robocasa.models.scenes import KitchenArena
    from robosuite.models.objects import MujocoXMLObject
    from robosuite.models.tasks import ManipulationTask

    rng = np.random.default_rng(seed)

    # ---- 1. 加载配置 ----
    layout = _load_yaml(os.path.join(scene_dir, "config", "layout.yaml")) or {}
    style = _load_yaml(os.path.join(scene_dir, "config", "style.yaml")) or {}
    objects_cfg = _load_yaml(os.path.join(scene_dir, "config", "objects.yaml")) or {}
    waypoints_cfg = _load_yaml(os.path.join(scene_dir, "config", "waypoints.yaml")) or {}
    scene_state = _load_yaml(os.path.join(scene_dir, "config", "scene_state_initial.yaml")) or {}

    # ---- 2. 创建 RoboCasa 厨房 Arena ----
    arena = KitchenArena(layout_id=layout, style_id=style, rng=rng, clutter_mode=0)
    arena.set_origin([0, 0, 0])
    fixture_cfgs = arena.get_fixture_cfgs()
    fixtures = [cfg["model"] for cfg in fixture_cfgs]

    # ---- 3. 放置物体 ----
    waypoints = {
        item["name"]: item
        for item in waypoints_cfg.get("waypoints", [])
        if item.get("name") and item.get("pos")
    }
    object_to_wp = _object_waypoint_map(waypoints, scene_state)
    fixture_refs = _resolve_fixture_refs(objects_cfg.get("fixture_refs", []), fixture_cfgs)

    object_models = []
    object_meta = []
    count_at_wp = {}
    placed_by_fixture = {}

    for obj_cfg in objects_cfg.get("objects", []):
        name = obj_cfg.get("name")
        group = obj_cfg.get("obj_groups", name)
        if not name:
            continue

        # 从 RoboCasa 物体库采样对应类别的 MJCF 模型
        kwargs, _info = sample_kitchen_object(
            groups=group,
            rng=rng,
            obj_registries=("objaverse", "lightwheel"),
        )
        mjcf_path = kwargs.pop("mjcf_path")
        scale = kwargs.pop("scale", None)
        obj = MujocoXMLObject(
            mjcf_path,
            name=name,
            joints="default",
            obj_type="all",
            duplicate_collision_geoms=True,
            scale=scale,
        )

        # 计算物体初始位置（在家具表面采样，避免重叠）
        pos = _object_initial_pos(
            name=name,
            obj_cfg=obj_cfg,
            object_to_wp=object_to_wp,
            waypoints=waypoints,
            count_at_wp=count_at_wp,
            fixture_refs=fixture_refs,
            placed_by_fixture=placed_by_fixture,
            rng=rng,
        )
        obj.set_pos(pos)
        object_models.append(obj)
        object_meta.append({
            "name": name,
            "root_body": obj.root_body,
            "pos": pos,
            "type": group,
        })

    # ---- 4. 装配 PandaOmron + 合并厨房 ----
    # robosuite 原生把机器人 merge 进 ManipulationTask(不再手工合并单独的机器人 XML)。
    robot_model = _assemble_pandaomron(seed)
    task = ManipulationTask(
        mujoco_arena=arena,
        mujoco_robots=[robot_model],
        mujoco_objects=fixtures + object_models,
        enable_multiccd=True,
        enable_sleeping_islands=False,
    )
    robot_root = ET.fromstring(task.get_xml())

    # ---- 5. 后处理(PandaOmron) ----
    _pandaomron_freejoint_base(robot_root)      # robot0_base 加 freejoint、剥离移动关节+actuator
    _rename_robot_cameras(robot_root)           # robotview→head_cam, eye_in_hand→right_arm_cam, +left_arm_cam
    _add_cameras(robot_root)                    # + overhead_cam(全局俯视)
    _set_statistic(robot_root)                  # MuJoCo viewer 中心点
    _hide_eef_targets(robot_root)               # 藏 IK target 标记(left/right_eef_target)
    _hide_robot_sites(robot_root)               # 藏机器人调试 site(夹爪绿柱/中心红点)
    _hide_nonvisual_geoms(robot_root)           # 藏 RoboCasa 自己的碰撞子块/registry/backing(随机彩色半透明块)
    _hide_collision_geoms(robot_root)           # 藏 PandaOmron 自身碰撞几何(绿臂/黄底座/红盒)
    _set_physics_options(robot_root)            # timestep/gravity/接触容量

    # ---- 6. 写出文件 ----
    fixture_meta = []
    for cfg in fixture_cfgs:
        fxtr = cfg["model"]
        root_body = getattr(fxtr, "root_body", cfg["name"])
        fixture_meta.append({
            "name": cfg["name"],
            "root_body": root_body,
            "pos": _list(getattr(fxtr, "pos", [0, 0, 0])),
            "size": _list(getattr(fxtr, "size", [0, 0, 0])),
            "type": type(fxtr).__name__,
        })

    os.makedirs(SCENE_ASSET_DIR, exist_ok=True)
    _indent(robot_root)
    ET.ElementTree(robot_root).write(GENERATED_SCENE, encoding="utf-8", xml_declaration=True)
    with open(GENERATED_META, "w", encoding="utf-8") as f:
        json.dump({"fixtures": fixture_meta, "objects": object_meta}, f, ensure_ascii=False, indent=2)
    return GENERATED_SCENE


# ============================================================
# PandaOmron 装配 + 后处理
# ============================================================

def _assemble_pandaomron(seed=42):
    """robosuite 原生装配 PandaOmron 机器人模型:Panda 臂 + Omron 移动底座 + PandaGripper。

    对应旧 create_scene 的 robots="PandaOmron",但只要模型(不建 env),交给 ManipulationTask merge。
    """
    from robosuite.models.robots import create_robot
    from robosuite.models.bases import robot_base_factory
    from robosuite.models.grippers import gripper_factory

    robot = create_robot(ROBOT_NAME, idn=0)
    robot.add_base(robot_base_factory(robot.default_base, idn=0))
    for arm in robot.arms:
        robot.add_gripper(gripper_factory(robot.default_gripper[arm], idn=f"0_{arm}"),
                          robot.eef_name[arm])
    robot.set_base_xpos([ROBOT_START_XY[0], ROBOT_START_XY[1], 0.0])
    return robot


def _pandaomron_freejoint_base(root):
    """Option F:给 robot0_base 加 freejoint、剥离 Omron 3 个平面移动关节(forward/side/yaw)及其
    actuator/sensor。这样底座变成一个可直接设 qpos 的自由体,复用现有 freejoint 运动学 nav,
    读位置精确无偏移。torso_height 关节保留(不影响平面运动)。"""
    # 1) robot0_base 加 freejoint(初始位姿由 set_base_xpos 写在 body pos 上)
    for b in root.iter("body"):
        if b.get("name") == "robot0_base" and b.find("freejoint") is None:
            b.insert(0, ET.Element("freejoint", {"name": BASE_FREEJOINT}))
        if b.get("name") == "mobilebase0_base":
            for j in list(b.findall("joint")):
                if j.get("name") in _BASE_PLANAR_JOINTS:
                    b.remove(j)
    # 2) 删掉引用这些关节的 actuator / sensor(否则编译报 "unknown transmission target")
    strip = set(_BASE_PLANAR_JOINTS)
    for parent in root.iter():
        for child in list(parent):
            if child.tag in ("motor", "position", "velocity", "general") and child.get("joint") in strip:
                parent.remove(child)
            elif child.get("joint") in strip and child.tag not in ("body", "geom", "camera"):
                parent.remove(child)


def _rename_robot_cameras(root):
    """给 PandaOmron 配测试台沿用的相机名(camera.yaml / 四宫格 / segmentation 全不用动):
      - head_cam:新挂在 robot0_base 上,抬高俯视工作区(PandaOmron 自带 robotview 看的是机器人自己,
        感知没用),转头扫描时扫周围台面 = 感知主相机。
      - right_arm_cam ← robot0_eye_in_hand(腕部手眼)。
      - left_arm_cam:复制 head_cam(单臂没左腕,凑四宫格第 4 格)。
    """
    # eye_in_hand → right_arm_cam
    for cam in root.iter("camera"):
        if cam.get("name") == "robot0_eye_in_hand":
            cam.set("name", "right_arm_cam")

    # 在 robot0_base 里加 head_cam(local 系:抬高 1.75m、前下俯,看工作区台面)
    base = root.find(".//body[@name='robot0_base']")
    if base is not None and root.find(".//camera[@name='head_cam']") is None:
        head = ET.SubElement(base, "camera", {
            "name": "head_cam", "pos": "0.35 0 1.75",
            "xyaxes": _xyaxes("0.35 0 1.75", "2.6 0 0.55"), "fovy": "70",
        })
        # 单臂没左腕:复制 head_cam 当 left_arm_cam,四宫格第 4 格不空
        dup = ET.SubElement(base, "camera", dict(head.attrib))
        dup.set("name", "left_arm_cam")


def _hide_collision_geoms(root):
    """把机器人/家具的碰撞几何移到 group 4(MujocoSim 只渲染 group 0/1/2 → 不渲染),
    但不动 contype/conaffinity(物理碰撞照常)。否则 PandaOmron 的绿色臂碰撞网格、黄色底座
    碰撞柱、红色 RoboCasa 碰撞盒会盖在相机视野里(robot 视觉是 *_vis 在 group1,碰撞在 group0)。"""
    for geom in root.iter("geom"):
        name = geom.get("name", "").lower()
        rgba = _rgba_values(geom.get("rgba"))
        is_collision_name = "collision" in name or name.endswith("_col") or "_col_" in name
        # robot 碰撞用纯色标注:绿 0 .5 0 / 黄 .5 .5 0;RoboCasa 碰撞盒常是红
        is_col_rgba = bool(rgba and rgba[3] > 0.9 and (
            (rgba[0] < 0.05 and 0.4 < rgba[1] < 0.6 and rgba[2] < 0.05) or
            (0.4 < rgba[0] < 0.6 and 0.4 < rgba[1] < 0.6 and rgba[2] < 0.05) or
            (rgba[0] >= 0.45 and rgba[1] <= 0.05 and rgba[2] <= 0.05)))
        if is_collision_name or is_col_rgba:
            geom.set("group", "4")


def _hide_eef_targets(root):
    """藏掉 IK target 标记 body(left/right_eef_target)的可见几何,避免渲染里出现悬浮小球。"""
    for b in root.iter("body"):
        if b.get("name") in ("left_eef_target", "right_eef_target"):
            for g in b.iter("geom"):
                g.set("rgba", "0 0 0 0")
                g.set("group", "4")


def _hide_robot_sites(root):
    """把机器人调试 site 的 alpha 设 0(夹爪 grip_site_cylinder 绿柱、right_center 红点等),
    否则会在相机视野里出现绿带/悬浮色块。site 只是标记,不影响物理。"""
    for site in root.iter("site"):
        nm = site.get("name") or ""
        if nm.startswith(("gripper0", "robot0", "mobilebase0")):
            rgba = (site.get("rgba") or "").split()
            if len(rgba) == 4:
                rgba[3] = "0"
                site.set("rgba", " ".join(rgba))


def _set_physics_options(root):
    """设置物理参数(timestep/gravity/接触容量),与原 XLeRobot 场景一致,保证厨房大场景稳定。
    并把 inertiagrouprange 扩到含 group 4:机器人质量来自 group0 碰撞几何(无显式 inertial),
    _hide_collision_geoms 把它们移到 group 4 不渲染,inertia range 覆盖 4 才不会丢质量。"""
    compiler = root.find("compiler")
    if compiler is not None:
        compiler.set("inertiagrouprange", "0 5")
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


def _find_parent(root, target):
    """ElementTree 无 getparent:线性找 target 的父节点。"""
    for parent in root.iter():
        for child in parent:
            if child is target:
                return parent
    return None


# ============================================================
# 后处理：相机 / 统计
# ============================================================

def _add_cameras(root):
    """
    添加全局场景相机（顶视 overhead_cam）。

    机器人自带相机（head_cam、right_arm_cam、left_arm_cam）由 _rename_robot_cameras
    从 PandaOmron 的 robotview/eye_in_hand 改名而来，跟随机器人移动。
    这里只加全局固定的 overhead 相机（仿真俯视，真机没有），用于截图和地图生成。
    """
    world = root.find("worldbody")
    if world is None:
        world = ET.SubElement(root, "worldbody")
    for name, pos, target, fovy in [
        ("overhead_cam", "3.2 -2.25 8.2", "3.2 -2.25 0.0", "62"),
    ]:
        existing = world.find(f"./camera[@name='{name}']")
        camera = existing if existing is not None else ET.SubElement(world, "camera", {"name": name})
        camera.set("pos", pos)
        camera.set("xyaxes", _xyaxes(pos, target))
        camera.set("fovy", fovy)


def _set_statistic(root):
    """设置 MuJoCo viewer 默认视角的中心点和范围。"""
    statistic = root.find("statistic")
    if statistic is None:
        statistic = ET.SubElement(root, "statistic")
    statistic.set("center", "3.2 -2.5 0.8")
    statistic.set("extent", "5")


# ============================================================
# 后处理：隐藏非视觉几何 / 恢复碰撞(PandaOmron 场景暂不调用,保留备用)
# ============================================================

def _hide_nonvisual_geoms(root):
    """
    将非视觉几何移到 group=4 并设为透明，避免在 viewer 和渲染中出现。

    隐藏的几何类型：
      - 红色碰撞体（RoboCasa 默认碰撞几何）
      - 透明调试几何（alpha <= 0.01）
      - Registry / bbox 辅助几何
      - Backing 墙体背面
      - 带 "collision" 关键字的碰撞 mesh
      - 末端执行器 target 标记
      - 半透明辅助几何（alpha < 0.99，无材质，group=0）

    保留 chassis body box（机器人躯干可见部分）。
    """
    for geom in root.iter("geom"):
        name = geom.get("name", "").lower()
        rgba = _rgba_values(geom.get("rgba"))
        is_red_collision = bool(rgba and rgba[0] >= 0.45 and rgba[1] <= 0.05 and rgba[2] <= 0.05)
        is_transparent_debug = bool(rgba and rgba[3] <= 0.01)
        is_registry_geom = "_reg" in name or "reg_" in name or name.endswith("_bbox")
        is_backing_geom = "backing" in name
        is_collision_geom = "collision" in name
        is_target_geom = "eef_target" in name
        is_translucent_helper = bool(
            rgba
            and rgba[3] < 0.99
            and geom.get("material") is None
            and geom.get("group", "0") == "0"
        )

        is_chassis_body_box = (
            geom.get("type") == "box"
            and geom.get("pos") == "-0.03 0 0.44"
            and geom.get("size") == "0.2 0.2 0.38"
        )

        if (
            not is_chassis_body_box
            and (
                is_red_collision
                or is_transparent_debug
                or is_registry_geom
                or is_backing_geom
                or is_collision_geom
                or is_target_geom
                or is_translucent_helper
            )
        ):
            geom.set("group", "4")
            geom.set("rgba", "0 0 0 0")


def _enable_robocasa_collisions(root):
    """
    恢复 RoboCasa 碰撞几何的物理碰撞属性。

    GS-Web 模型的全局默认 <default> 设了 contype=0 conaffinity=0，
    会让 RoboCasa 的地面、台面、物体碰撞体继承成"无碰撞"，导致物体穿过台面下掉。
    此函数遍历 group=4 的几何：
      - registry/bbox/backing/eef_target 辅助几何 → 保持无碰撞
      - 其余碰撞体 → 恢复 contype=1 conaffinity=1
    """
    for geom in root.iter("geom"):
        name = geom.get("name", "").lower()
        group = geom.get("group")
        if group != "4":
            continue
        if "_reg" in name or "reg_" in name or name.endswith("_bbox"):
            geom.set("contype", "0")
            geom.set("conaffinity", "0")
            continue
        if "backing" in name or "eef_target" in name:
            geom.set("contype", "0")
            geom.set("conaffinity", "0")
            continue
        geom.set("contype", "1")
        geom.set("conaffinity", "1")
        geom.set("condim", geom.get("condim", "4"))
        geom.set("friction", geom.get("friction", "1 0.005 0.0001"))


# ============================================================
# 物体放置：家具查找 / 位置采样 / 避重叠
# ============================================================

def _object_waypoint_map(waypoints, scene_state):
    """
    构建 物体名 → 工作点名 的映射。

    优先用 waypoints 里的 serves 字段，再用 scene_state 的 locations。
    """
    object_to_wp = {}
    for wp in waypoints.values():
        for served in wp.get("serves", []):
            object_to_wp.setdefault(served, wp["name"])
    for wp_name, state in scene_state.get("locations", {}).items():
        for obj_name in state.get("objects", []) or []:
            object_to_wp.setdefault(obj_name, wp_name)
    return object_to_wp


def _object_initial_pos(name, obj_cfg, object_to_wp, waypoints, count_at_wp, fixture_refs, placed_by_fixture, rng):
    """
    计算物体初始世界坐标 [x, y, z]。

    优先使用 objects.yaml 中的 placement 配置（指定家具 + 区域），
    否则用 waypoint 兜底。
    """
    placement = obj_cfg.get("placement") or {}
    fixture = _placement_fixture(placement, fixture_refs)
    if fixture is not None:
        return _sample_placement_pos(name, placement, fixture, fixture_refs, placed_by_fixture, rng)

    wp_name = object_to_wp.get(name)
    wp = waypoints.get(wp_name or "")
    if wp:
        x, y = wp["pos"]
        offset_index = count_at_wp.get(wp["name"], 0)
        count_at_wp[wp["name"]] = offset_index + 1
        x = float(x) + 0.08 * (offset_index % 3 - 1)
        y = float(y) + 0.08 * (offset_index // 3)
        return [x, y, 1.05]
    return [3.0, -2.5, 1.05]


def _placement_fixture(placement, fixture_refs):
    """根据 placement 配置找到对应家具对象。"""
    fixture_name = placement.get("fixture")
    fixture = fixture_refs.get(fixture_name)
    ref_name = (placement.get("sample_region_kwargs") or {}).get("ref")
    ref_fixture = fixture_refs.get(ref_name)
    if fixture_name == "counter" and ref_fixture is not None:
        return _select_fixture_from_refs(fixture_refs, "COUNTER", ref_fixture)
    return fixture


def _select_fixture_from_refs(fixture_refs, fixture_id, ref_fixture):
    """从 fixture 列表里按类型和参考家具选择最匹配的 fixture。"""
    fixture_cfgs = fixture_refs.get("__fixture_cfgs", [])
    selected = _select_fixture(fixture_cfgs, fixture_id, ref_fixture=ref_fixture)
    return selected or fixture_refs.get(str(fixture_id).lower())


def _sample_placement_pos(name, placement, fixture, fixture_refs, placed_by_fixture, rng):
    """
    在家具表面采样物体位置。

    根据家具的 pos/size 计算可放置区域，支持：
      - 固定偏移（pos: [1.0, -1.0]）
      - 参考家具方向（pos: ["ref", ...]）
      - 随机采样并避让已放置物体（最小间距 0.35m）
    """
    center = _fixture_pos(fixture)
    size = _fixture_size(fixture)
    pos_cfg = placement.get("pos")
    ref_name = (placement.get("sample_region_kwargs") or {}).get("ref")
    ref_fixture = fixture_refs.get(ref_name)

    if pos_cfg is None and ref_fixture is None:
        region_size = np.maximum(size[:2] - 0.20, 0.08)
    else:
        region_size = np.asarray(placement.get("size") or size[:2], dtype=float)
        region_size = np.minimum(region_size, np.maximum(size[:2] - 0.12, 0.08))

    fixture_key = getattr(fixture, "root_body", getattr(fixture, "name", str(id(fixture))))
    if isinstance(pos_cfg, (list, tuple)) and len(pos_cfg) >= 2:
        xy = center[:2].copy()
        xy += _placement_offset(
            pos_cfg=pos_cfg,
            fixture=fixture,
            ref_fixture=ref_fixture,
            region_size=region_size,
            rng=rng,
        )
    else:
        xy = _sample_nonoverlapping_xy(
            center=center[:2],
            region_size=region_size,
            existing=placed_by_fixture.setdefault(fixture_key, []),
            rng=rng,
        )

    offset = np.asarray(placement.get("offset") or [0.0, 0.0], dtype=float)
    if offset.size >= 2:
        xy += offset[:2]

    placed_by_fixture.setdefault(fixture_key, []).append(np.asarray(xy, dtype=float))
    top_z = center[2] + size[2] / 2.0
    z = top_z + 0.08
    return [float(xy[0]), float(xy[1]), float(z)]


def _sample_nonoverlapping_xy(center, region_size, existing, rng, min_dist=0.35):
    """在家具区域内随机采样位置，保证与已放置物体的间距 >= min_dist。"""
    center = np.asarray(center, dtype=float)
    region_size = np.asarray(region_size, dtype=float)
    for _ in range(80):
        xy = center + rng.uniform(-0.5, 0.5, size=2) * region_size
        if all(np.linalg.norm(xy - prev) >= min_dist for prev in existing):
            return xy

    grid_cols = max(2, int(np.ceil(np.sqrt(len(existing) + 1))))
    grid_rows = max(2, int(np.ceil((len(existing) + 1) / grid_cols)))
    idx = len(existing)
    col = idx % grid_cols
    row = idx // grid_cols
    x = center[0] - region_size[0] / 2.0 + (col + 0.5) * region_size[0] / grid_cols
    y = center[1] - region_size[1] / 2.0 + (row + 0.5) * region_size[1] / grid_rows
    return np.array([x, y], dtype=float)


def _placement_offset(pos_cfg, fixture, ref_fixture, region_size, rng):
    """计算 placement.pos 配置指定的偏移量（支持数值和 "ref" 关键字）。"""
    out = np.zeros(2)
    for axis, spec in enumerate(pos_cfg[:2]):
        if spec is None:
            out[axis] = rng.uniform(-0.5, 0.5) * region_size[axis]
        elif spec == "ref":
            out[axis] = _ref_axis_offset(axis, fixture, ref_fixture, region_size)
        else:
            out[axis] = float(spec) * region_size[axis] / 2.0
    return out


def _ref_axis_offset(axis, fixture, ref_fixture, region_size):
    """计算朝向参考家具方向的偏移。"""
    if ref_fixture is None:
        return 0.0
    fixture_pos = _fixture_pos(fixture)
    ref_pos = _fixture_pos(ref_fixture)
    direction = np.sign(ref_pos[axis] - fixture_pos[axis])
    if direction == 0:
        direction = 1.0
    return float(direction * region_size[axis] / 2.0)


# ============================================================
# 家具查找 / 匹配
# ============================================================

def _resolve_fixture_refs(ref_cfgs, fixture_cfgs):
    """
    将 objects.yaml 中的 fixture_refs 配置解析为实际 fixture 对象。

    输入格式：
      fixture_refs:
        - name: counter
          id: COUNTER

    输出：{name: fixture_model} 字典，加上 __fixture_cfgs 备用。
    """
    refs = {"__fixture_cfgs": fixture_cfgs}
    for ref_cfg in ref_cfgs or []:
        name = ref_cfg.get("name")
        fixture_id = ref_cfg.get("id")
        if not name or not fixture_id:
            continue
        refs[name] = _select_fixture(
            fixture_cfgs=fixture_cfgs,
            fixture_id=fixture_id,
            ref_fixture=None,
            prefer_name=name,
        )
    return refs


def _select_fixture(fixture_cfgs, fixture_id, ref_fixture=None, prefer_name=None):
    """从 fixture 配置列表中按类型和名称匹配最合适的 fixture。"""
    candidates = []
    id_upper = str(fixture_id).upper()
    for cfg in fixture_cfgs:
        model = cfg["model"]
        cls_name = type(model).__name__.lower()
        cfg_name = cfg["name"].lower()
        if _fixture_matches(id_upper, cls_name, cfg_name, prefer_name):
            candidates.append(model)
    if not candidates:
        return None
    if ref_fixture is not None:
        ref_pos = _fixture_pos(ref_fixture)
        return min(candidates, key=lambda fxtr: np.linalg.norm(_fixture_pos(fxtr)[:2] - ref_pos[:2]))
    if prefer_name:
        preferred = [fxtr for fxtr in candidates if prefer_name.lower() in getattr(fxtr, "name", "").lower()]
        if preferred:
            return max(preferred, key=lambda fxtr: np.prod(_fixture_size(fxtr)[:2]))
    return max(candidates, key=lambda fxtr: np.prod(_fixture_size(fxtr)[:2]))


def _fixture_matches(fixture_id, cls_name, cfg_name, prefer_name=None):
    """判断一个 fixture 是否匹配目标 fixture_id。"""
    if fixture_id == "COUNTER":
        return "counter" in cls_name and "corner" not in cfg_name
    if fixture_id == "ISLAND":
        return "counter" in cls_name and "island" in cfg_name
    if fixture_id == "STOVE":
        return "stove" in cls_name or "stovetop" in cls_name
    if fixture_id == "SINK":
        return "sink" in cls_name
    if fixture_id == "CABINET":
        return "cabinet" in cls_name or "cab" in cfg_name
    needle = fixture_id.lower()
    if prefer_name and prefer_name.lower() in cfg_name:
        return True
    return needle in cls_name or needle in cfg_name


# ============================================================
# 通用工具函数
# ============================================================

def _fixture_pos(fixture):
    """获取 fixture 的世界坐标。"""
    return np.asarray(getattr(fixture, "pos", [0.0, 0.0, 0.0]), dtype=float)


def _fixture_size(fixture):
    """获取 fixture 的尺寸 [宽, 深, 高]。"""
    return np.asarray(getattr(fixture, "size", [0.5, 0.5, 0.5]), dtype=float)


def _xyaxes(pos, target):
    """根据相机位置和目标点计算 MuJoCo 相机的 xyaxes 参数。"""
    pos_v = np.array([float(x) for x in pos.split()])
    target_v = np.array([float(x) for x in target.split()])
    forward = target_v - pos_v
    forward /= np.linalg.norm(forward)
    up = np.array([0.0, 0.0, 1.0])
    right = np.cross(forward, up)
    if np.linalg.norm(right) < 1e-6:
        right = np.array([1.0, 0.0, 0.0])
    right /= np.linalg.norm(right)
    cam_up = np.cross(right, forward)
    return " ".join(f"{v:.6g}" for v in np.r_[right, cam_up])


def _load_yaml(path):
    """加载 YAML 配置文件，文件不存在时返回 None。"""
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _list(value):
    """将 value 转为 [x, y, z] 列表，None 时返回 [0, 0, 0]。"""
    if value is None:
        return [0.0, 0.0, 0.0]
    return np.asarray(value, dtype=float).tolist()


def _rgba_values(value):
    """解析 rgba 字符串 "r g b a" 为 [float x 4]，失败返回 None。"""
    if not value:
        return None
    try:
        vals = [float(v) for v in value.split()]
    except ValueError:
        return None
    return vals if len(vals) == 4 else None


def _indent(elem, level=0):
    """递归缩进 XML 元素，使输出文件可读。"""
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
