"""
make_scene.py - 自定义 Kitchen 子类
从本地 scene/config/ 目录读取 layout/style/objects YAML 配置
"""

import os
import yaml
import numpy as np

from robocasa.environments.kitchen.kitchen import Kitchen, KitchenArena
from robocasa.models.fixtures.fixture import FixtureType
import robocasa.utils.camera_utils as CamUtils


class MyKitchen(Kitchen):
    def __init__(self, scene_dir=None, *args, **kwargs):
        self._scene_dir = scene_dir
        super().__init__(*args, **kwargs)

    def _setup_model(self):
        # ① 机器人初始化
        from robosuite.models.robots import PandaOmron

        for robot in self.robots:
            if isinstance(robot.robot_model, PandaOmron):
                robot.init_qpos = (
                    -0.01612974,
                    -1.03446714,
                    -0.02397936,
                    -2.27550888,
                    0.03932365,
                    1.51639493,
                    0.69615947,
                )
                robot.init_torso_qpos = np.array([0.0])

        # ② 从本地 scene/ 目录读取 YAML
        layout_config = self._load_yaml("config/layout.yaml")
        style_config = self._load_yaml("config/style.yaml")

        self.layout_id = 7
        self.style_id = 1
        self._curr_gen_fixtures = self._ep_meta.get("gen_textures")

        # ③ 创建 KitchenArena（传 dict，不走 get_layout_path/get_style_path）
        self.mujoco_arena = KitchenArena(
            layout_id=layout_config,
            style_id=style_config,
            rng=self.rng,
            enable_fixtures=self.enable_fixtures,
            clutter_mode=self.clutter_mode,
            update_fxtr_cfg_dict=self.update_fxtr_cfg_dict,
        )

        # ④ 后续代码与父类完全一致
        self.mujoco_arena.set_origin([0, 0, 0])
        CamUtils.set_cameras(self)

        if self.renderer == "mjviewer":
            camera_config = CamUtils.LAYOUT_CAMS.get(
                self.layout_id, CamUtils.DEFAULT_LAYOUT_CAM
            )
            self.renderer_config = {"cam_config": camera_config}

        self.fixture_cfgs = self.mujoco_arena.get_fixture_cfgs()
        self.fixtures = {cfg["name"]: cfg["model"] for cfg in self.fixture_cfgs}

        from robosuite.models.tasks import ManipulationTask

        self.model = ManipulationTask(
            mujoco_arena=self.mujoco_arena,
            mujoco_robots=[robot.robot_model for robot in self.robots],
            mujoco_objects=list(self.fixtures.values()),
            enable_multiccd=True,
            enable_sleeping_islands=False,
        )

    def _setup_kitchen_references(self):
        """从 objects.yaml 的 fixture_refs 部分注册家具引用"""
        super()._setup_kitchen_references()

        config = self._load_yaml("config/objects.yaml")
        if config is None:
            return

        for ref_cfg in config.get("fixture_refs", []):
            ref_name = ref_cfg["name"]
            fixture_type = FixtureType[ref_cfg["id"]]
            fn_kwargs = {"id": fixture_type}

            if "ref" in ref_cfg:
                parent = self._get_registered_fixture(ref_cfg["ref"])
                if parent is not None:
                    fn_kwargs["ref"] = parent

            self.register_fixture_ref(ref_name, fn_kwargs)

    def _get_obj_cfgs(self):
        """从 objects.yaml 读取物体配置，解析 fixture 字符串引用"""
        config = self._load_yaml("config/objects.yaml")
        if config is None:
            return []

        cfgs = []
        for obj_cfg in config.get("objects", []):
            cfg = dict(obj_cfg)
            placement = cfg.get("placement", {})

            # fixture: "counter" → self.fixture_refs["counter"] 实际对象
            if "fixture" in placement and isinstance(placement["fixture"], str):
                fxtr = self._get_registered_fixture(placement["fixture"])
                if fxtr is not None:
                    placement["fixture"] = fxtr

            # sample_region_kwargs.ref: "stove" → 实际对象
            region_kwargs = placement.get("sample_region_kwargs", {})
            if "ref" in region_kwargs and isinstance(region_kwargs["ref"], str):
                fxtr = self._get_registered_fixture(region_kwargs["ref"])
                if fxtr is not None:
                    region_kwargs["ref"] = fxtr

            cfgs.append(cfg)

        return cfgs

    def _check_success(self):
        return False

    def _get_registered_fixture(self, ref_name):
        """从 fixture_refs 中取出已注册的 fixture 对象"""
        ref_value = self.fixture_refs.get(ref_name)
        if ref_value is None:
            return None
        return ref_value[0] if isinstance(ref_value, tuple) else ref_value

    def _load_yaml(self, filename):
        path = os.path.join(self._scene_dir, filename)
        if not os.path.exists(path):
            return None
        with open(path, "r") as f:
            return yaml.safe_load(f)
