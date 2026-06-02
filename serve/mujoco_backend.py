import json
import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import mujoco
import numpy as np
import yaml


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XLEROBOT_DIR = os.path.join(ROOT_DIR, "assets", "xlerobot")
XLEROBOT_XML = os.path.join(XLEROBOT_DIR, "xlerobot.xml")
GENERATED_SCENE = os.path.join(XLEROBOT_DIR, "fqplanner_scene.xml")
GENERATED_META = os.path.join(XLEROBOT_DIR, "fqplanner_scene_meta.json")


@dataclass
class Fixture:
    name: str
    root_body: str
    pos: list
    size: list
    type: str


class MujocoSim:
    def __init__(self, model, data):
        self.model = model
        self.data = data
        self._renderer = None
        self._renderer_size = None
        self._scene_option = mujoco.MjvOption()
        self._scene_option.geomgroup[:] = 0
        self._scene_option.geomgroup[0] = 1
        self._scene_option.geomgroup[1] = 1
        self._scene_option.geomgroup[2] = 1

    def forward(self):
        mujoco.mj_forward(self.model, self.data)

    def render(self, width, height, camera_name="overhead_cam"):
        size = (int(width), int(height))
        if self._renderer is None or self._renderer_size != size:
            if self._renderer is not None:
                self._renderer.close()
            self._renderer = mujoco.Renderer(self.model, height=size[1], width=size[0])
            self._renderer_size = size

        camera_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_CAMERA, camera_name)
        if camera_id < 0:
            camera_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_CAMERA, "overhead_cam")
        self._renderer.update_scene(
            self.data,
            camera=camera_id if camera_id >= 0 else None,
            scene_option=self._scene_option,
        )
        return self._renderer.render()

    def close(self):
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None


class MujocoKitchenEnv:
    def __init__(self, scene_dir, seed=42):
        self.scene_dir = os.path.abspath(scene_dir)
        self.rng = np.random.default_rng(seed)
        self.scene_xml = build_scene_xml(self.scene_dir, seed=seed)
        self.model = mujoco.MjModel.from_xml_path(self.scene_xml)
        self.data = mujoco.MjData(self.model)
        self.sim = MujocoSim(self.model, self.data)
        self.action_dim = self.model.nu
        self.objects = []
        self.obj_body_id = {}
        self.obj_joint_id = {}
        self.fixtures = {}
        self.grasped_object = None
        self.virtual_ee_pos = np.zeros(3)
        self._load_registry()
        self.reset()

    def _load_registry(self):
        with open(GENERATED_META, "r", encoding="utf-8") as f:
            meta = json.load(f)

        self.objects = [item["name"] for item in meta["objects"]]
        for item in meta["objects"]:
            body_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, item["root_body"])
            if body_id >= 0:
                self.obj_body_id[item["name"]] = body_id
                joint_adr = self.model.body_jntadr[body_id]
                if joint_adr >= 0:
                    self.obj_joint_id[item["name"]] = int(joint_adr)

        for item in meta["fixtures"]:
            self.fixtures[item["name"]] = Fixture(
                name=item["name"],
                root_body=item["root_body"],
                pos=item["pos"],
                size=item["size"],
                type=item["type"],
            )

    def reset(self):
        mujoco.mj_resetData(self.model, self.data)
        self.data.ctrl[:] = 0.0
        self._set_initial_objects()
        self.sim.forward()
        self.virtual_ee_pos = self.get_body_pos("Fixed_Jaw_2", fallback="Moving_Jaw_2")
        return {}

    def _set_initial_objects(self):
        with open(GENERATED_META, "r", encoding="utf-8") as f:
            meta = json.load(f)
        initial_pos = {item["name"]: item["pos"] for item in meta["objects"]}
        for obj_name in self.objects:
            joint_id = self.obj_joint_id.get(obj_name)
            if joint_id is None:
                continue
            qadr = self.model.jnt_qposadr[joint_id]
            pos = np.asarray(initial_pos[obj_name], dtype=float)
            self.data.qpos[qadr:qadr + 3] = pos
            self.data.qpos[qadr + 3:qadr + 7] = [1.0, 0.0, 0.0, 0.0]

    def step(self, action=None):
        if action is not None:
            action = np.asarray(action, dtype=float)
            n = min(action.size, self.model.nu)
            self.data.ctrl[:n] = action[:n]
        if self.grasped_object:
            self.set_object_pos(self.grasped_object, self.virtual_ee_pos)
        mujoco.mj_step(self.model, self.data)
        if self.grasped_object:
            self.set_object_pos(self.grasped_object, self.virtual_ee_pos)
            self.sim.forward()

    def close(self):
        self.sim.close()

    def get_body_pos(self, body_name, fallback=None):
        body_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, body_name)
        if body_id < 0 and fallback:
            body_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, fallback)
        if body_id < 0:
            return self.virtual_ee_pos.copy()
        return self.data.xpos[body_id].copy()

    def get_body_quat(self, body_name, fallback=None):
        body_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, body_name)
        if body_id < 0 and fallback:
            body_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, fallback)
        if body_id < 0:
            return np.array([1.0, 0.0, 0.0, 0.0])
        return self.data.xquat[body_id].copy()

    def get_object_pos(self, obj_name):
        return self.data.xpos[self.obj_body_id[obj_name]].copy()

    def set_object_pos(self, obj_name, pos):
        joint_id = self.obj_joint_id[obj_name]
        qadr = self.model.jnt_qposadr[joint_id]
        self.data.qpos[qadr:qadr + 3] = np.asarray(pos, dtype=float)
        self.data.qpos[qadr + 3:qadr + 7] = [1.0, 0.0, 0.0, 0.0]
        self.sim.forward()


def build_scene_xml(scene_dir, seed=42):
    """Export a real RoboCasa kitchen MJCF, then merge the local XLeRobot MJCF."""
    os.environ.setdefault("NUMBA_DISABLE_JIT", "1")

    from robocasa.models.objects.kitchen_object_utils import sample_kitchen_object
    from robocasa.models.scenes import KitchenArena
    from robosuite.models.objects import MujocoXMLObject
    from robosuite.models.tasks import ManipulationTask

    rng = np.random.default_rng(seed)
    layout = _load_yaml(os.path.join(scene_dir, "config", "layout.yaml")) or {}
    style = _load_yaml(os.path.join(scene_dir, "config", "style.yaml")) or {}
    objects_cfg = _load_yaml(os.path.join(scene_dir, "config", "objects.yaml")) or {}
    waypoints_cfg = _load_yaml(os.path.join(scene_dir, "config", "waypoints.yaml")) or {}
    scene_state = _load_yaml(os.path.join(scene_dir, "config", "scene_state_initial.yaml")) or {}

    waypoints = {
        item["name"]: item
        for item in waypoints_cfg.get("waypoints", [])
        if item.get("name") and item.get("pos")
    }
    object_to_wp = _object_waypoint_map(waypoints, scene_state)

    arena = KitchenArena(layout_id=layout, style_id=style, rng=rng, clutter_mode=0)
    arena.set_origin([0, 0, 0])
    fixture_cfgs = arena.get_fixture_cfgs()
    fixtures = [cfg["model"] for cfg in fixture_cfgs]

    object_models = []
    object_meta = []
    count_at_wp = {}
    placed_by_fixture = {}
    fixture_refs = _resolve_fixture_refs(objects_cfg.get("fixture_refs", []), fixture_cfgs)
    for obj_cfg in objects_cfg.get("objects", []):
        name = obj_cfg.get("name")
        group = obj_cfg.get("obj_groups", name)
        if not name:
            continue
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

    task = ManipulationTask(
        mujoco_arena=arena,
        mujoco_robots=[],
        mujoco_objects=fixtures + object_models,
        enable_multiccd=True,
        enable_sleeping_islands=False,
    )
    robocasa_root = ET.fromstring(task.get_xml())
    robot_root = ET.parse(XLEROBOT_XML).getroot()
    _merge_robocasa_into_robot(robot_root, robocasa_root)
    _add_cameras(robot_root)
    _set_statistic(robot_root)
    _set_robot_initial_pose(robot_root)
    _hide_nonvisual_geoms(robot_root)

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

    os.makedirs(XLEROBOT_DIR, exist_ok=True)
    _indent(robot_root)
    ET.ElementTree(robot_root).write(GENERATED_SCENE, encoding="utf-8", xml_declaration=True)
    with open(GENERATED_META, "w", encoding="utf-8") as f:
        json.dump({"fixtures": fixture_meta, "objects": object_meta}, f, ensure_ascii=False, indent=2)
    return GENERATED_SCENE


def _merge_robocasa_into_robot(robot_root, robocasa_root):
    for tag in ("asset", "worldbody", "actuator", "sensor", "tendon", "equality", "contact"):
        src = robocasa_root.find(tag)
        if src is None:
            continue
        dst = robot_root.find(tag)
        if dst is None:
            dst = ET.SubElement(robot_root, tag)
        existing_names = {(child.tag, child.get("name")) for child in dst if child.get("name")}
        for child in list(src):
            name = child.get("name")
            key = (child.tag, name)
            if name and key in existing_names:
                continue
            dst.append(child)
            if name:
                existing_names.add(key)

    option = robot_root.find("option")
    if option is None:
        option = ET.SubElement(robot_root, "option")
    option.set("timestep", "0.002")
    option.set("gravity", "0 0 -9.80665")
    option.set("integrator", "implicitfast")

    size = robot_root.find("size")
    if size is None:
        size = ET.SubElement(robot_root, "size")
    size.set("nconmax", "5000")
    size.set("njmax", "5000")


def _add_cameras(root):
    world = root.find("worldbody")
    if world is None:
        world = ET.SubElement(root, "worldbody")
    for name, pos, target, fovy in [
        ("overhead_cam", "3.2 -2.5 6.5", "3.2 -2.5 0.0", "45"),
        ("side_cam", "3.2 -7.0 2.5", "3.2 -2.5 0.8", "55"),
        ("robot0_frontview", "1.2 -5.2 1.7", "3.2 -2.5 0.7", "60"),
        ("robot0_eye_in_hand", "2.0 -3.4 1.3", "3.2 -2.5 0.8", "60"),
    ]:
        if world.find(f"./camera[@name='{name}']") is None:
            ET.SubElement(world, "camera", {
                "name": name,
                "pos": pos,
                "xyaxes": _xyaxes(pos, target),
                "fovy": fovy,
            })


def _set_statistic(root):
    statistic = root.find("statistic")
    if statistic is None:
        statistic = ET.SubElement(root, "statistic")
    statistic.set("center", "3.2 -2.5 0.8")
    statistic.set("extent", "5")


def _set_robot_initial_pose(root):
    chassis = root.find(".//body[@name='chassis']")
    if chassis is None:
        return
    chassis.set("pos", "3.2 -1.5 0.035")
    chassis.set("quat", "0.707108 0 0 0.707108")


def _hide_nonvisual_geoms(root):
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

        # Preserve the chassis body box (torso visual)
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


def _rgba_values(value):
    if not value:
        return None
    try:
        vals = [float(v) for v in value.split()]
    except ValueError:
        return None
    return vals if len(vals) == 4 else None


def _resolve_fixture_refs(ref_cfgs, fixture_cfgs):
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


def _fixture_pos(fixture):
    return np.asarray(getattr(fixture, "pos", [0.0, 0.0, 0.0]), dtype=float)


def _fixture_size(fixture):
    return np.asarray(getattr(fixture, "size", [0.5, 0.5, 0.5]), dtype=float)


def _object_waypoint_map(waypoints, scene_state):
    object_to_wp = {}
    for wp in waypoints.values():
        for served in wp.get("serves", []):
            object_to_wp.setdefault(served, wp["name"])
    for wp_name, state in scene_state.get("locations", {}).items():
        for obj_name in state.get("objects", []) or []:
            object_to_wp.setdefault(obj_name, wp_name)
    return object_to_wp


def _object_initial_pos(name, obj_cfg, object_to_wp, waypoints, count_at_wp, fixture_refs, placed_by_fixture, rng):
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
    fixture_name = placement.get("fixture")
    fixture = fixture_refs.get(fixture_name)
    ref_name = (placement.get("sample_region_kwargs") or {}).get("ref")
    ref_fixture = fixture_refs.get(ref_name)
    if fixture_name == "counter" and ref_fixture is not None:
        return _select_fixture_from_refs(fixture_refs, "COUNTER", ref_fixture)
    return fixture


def _select_fixture_from_refs(fixture_refs, fixture_id, ref_fixture):
    fixture_cfgs = fixture_refs.get("__fixture_cfgs", [])
    selected = _select_fixture(fixture_cfgs, fixture_id, ref_fixture=ref_fixture)
    return selected or fixture_refs.get(str(fixture_id).lower())


def _sample_placement_pos(name, placement, fixture, fixture_refs, placed_by_fixture, rng):
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
    if ref_fixture is None:
        return 0.0
    fixture_pos = _fixture_pos(fixture)
    ref_pos = _fixture_pos(ref_fixture)
    direction = np.sign(ref_pos[axis] - fixture_pos[axis])
    if direction == 0:
        direction = 1.0
    return float(direction * region_size[axis] / 2.0)


def _xyaxes(pos, target):
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
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _list(value):
    if value is None:
        return [0.0, 0.0, 0.0]
    return np.asarray(value, dtype=float).tolist()


def _indent(elem, level=0):
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
