import json
import os
from dataclasses import dataclass

import mujoco
import numpy as np

from scene.scene_generator import build_scene_xml, GENERATED_SCENE, GENERATED_META


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
        self.base_free_joint_id = -1
        self.base_height = None
        self._load_registry()
        self._load_robot_registry()
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

    def _load_robot_registry(self):
        body_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "chassis")
        if body_id < 0:
            return
        joint_adr = self.model.body_jntadr[body_id]
        if joint_adr < 0:
            return
        joint_id = int(joint_adr)
        if self.model.jnt_type[joint_id] == mujoco.mjtJoint.mjJNT_FREE:
            self.base_free_joint_id = joint_id
            qadr = self.model.jnt_qposadr[joint_id]
            self.base_height = float(self.model.qpos0[qadr + 2])

    def reset(self):
        mujoco.mj_resetData(self.model, self.data)
        self.data.ctrl[:] = 0.0
        self._set_initial_arm_pose()
        self._set_initial_objects()
        self.sim.forward()
        self.virtual_ee_pos = self.get_body_pos("Fixed_Jaw_2", fallback="Moving_Jaw_2")
        return {}

    def _set_initial_arm_pose(self):
        arm_pose = {
            "Rotation_R": 0.0,
            "Pitch_R": 2.0,
            "Elbow_R": 0.5,
            "Wrist_Pitch_R": -0.3,
            "Wrist_Roll_R": 0.0,
            "Jaw_R": 0.0,
            "Rotation_L": 0.0,
            "Pitch_L": 2.0,
            "Elbow_L": 0.5,
            "Wrist_Pitch_L": -0.3,
            "Wrist_Roll_L": 0.0,
            "Jaw_L": 0.0,
        }
        for joint_name, value in arm_pose.items():
            joint_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, joint_name)
            if joint_id < 0:
                continue
            qadr = self.model.jnt_qposadr[joint_id]
            self.data.qpos[qadr] = value
            actuator_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_ACTUATOR, joint_name)
            if actuator_id >= 0:
                self.data.ctrl[actuator_id] = value

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
            if self.base_free_joint_id >= 0 and action.size == 3:
                self.move_base_kinematic(Vx=action[0], Vy=action[1], Vw=action[2])
                action = None
            else:
                n = min(action.size, self.model.nu)
                self.data.ctrl[:n] = action[:n]
        if self.grasped_object:
            self.set_object_pos(self.grasped_object, self.virtual_ee_pos)
        mujoco.mj_step(self.model, self.data)
        self._pin_base_freejoint()
        if self.grasped_object:
            self.set_object_pos(self.grasped_object, self.virtual_ee_pos)
            self.sim.forward()

    def move_base_kinematic(self, Vx=0.0, Vy=0.0, Vw=0.0, dt=0.02):
        if self.base_free_joint_id < 0:
            return False
        qadr = self.model.jnt_qposadr[self.base_free_joint_id]
        dadr = self.model.jnt_dofadr[self.base_free_joint_id]
        yaw = self._base_yaw_from_qpos(qadr)
        c = np.cos(yaw)
        s = np.sin(yaw)
        self.data.qpos[qadr] += (c * Vx - s * Vy) * dt
        self.data.qpos[qadr + 1] += (s * Vx + c * Vy) * dt
        yaw += float(Vw) * dt
        self.data.qpos[qadr + 3:qadr + 7] = [np.cos(yaw / 2.0), 0.0, 0.0, np.sin(yaw / 2.0)]
        self.data.qvel[dadr:dadr + 6] = 0.0
        self.sim.forward()
        return True

    def _base_yaw_from_qpos(self, qadr):
        w, x, y, z = self.data.qpos[qadr + 3:qadr + 7]
        return float(np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))

    def _pin_base_freejoint(self):
        if self.base_free_joint_id < 0 or self.base_height is None:
            return
        qadr = self.model.jnt_qposadr[self.base_free_joint_id]
        dadr = self.model.jnt_dofadr[self.base_free_joint_id]
        yaw = self._base_yaw_from_qpos(qadr)
        self.data.qpos[qadr + 2] = self.base_height
        self.data.qpos[qadr + 3:qadr + 7] = [np.cos(yaw / 2.0), 0.0, 0.0, np.sin(yaw / 2.0)]
        self.data.qvel[dadr:dadr + 6] = 0.0
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
