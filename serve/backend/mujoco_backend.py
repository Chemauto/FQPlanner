import json
import os
from dataclasses import dataclass

import mujoco
import numpy as np

from scene.scene_generator import build_scene_xml, GENERATED_SCENE, GENERATED_META

# 门 joint 命名后缀(RoboCasa 约定):有其一即视为"带门容器"。
# open_container_door 转这些 joint,list_containers 用它判定哪些 fixture 是容器。
_DOOR_JOINT_SUFFIXES = ("_doorhinge", "_leftdoorhinge", "_rightdoorhinge", "_door_joint", "_slidejoint")


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
        self._seg_renderer = None
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

    def render_segmentation(self, camera_name="head_cam"):
        """渲染 segmentation mask → (H,W,2) int32:[...,0]=geom id, [...,1]=mjtObj type。
        用独立低分辨率 seg renderer(懒加载),与 RGB renderer 分开;同进程双 renderer 在 macOS
        已验证稳定。用于'机器人相机看到哪些物体'的部分可观测感知。"""
        if self._seg_renderer is None:
            self._seg_renderer = mujoco.Renderer(self.model, height=120, width=160)
            self._seg_renderer.enable_segmentation_rendering()
        camera_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_CAMERA, camera_name)
        if camera_id < 0:
            camera_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_CAMERA, "head_cam")
        self._seg_renderer.update_scene(
            self.data,
            camera=camera_id if camera_id >= 0 else None,
            scene_option=self._scene_option,
        )
        return self._seg_renderer.render()

    def close(self):
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None
        if self._seg_renderer is not None:
            self._seg_renderer.close()
            self._seg_renderer = None


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
        self._arm_hold = []  # [(qadr, value)] PandaOmron 臂/夹爪初始位姿,每步重置=运动学冻结(臂力矩驱动会下垂)
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
        # PandaOmron:底座根 body 是 robot0_base,scene_generator 给它加了 base_freejoint
        # (剥离了 Omron 平面移动关节),所以复用现有 freejoint 运动学 nav。
        body_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, "robot0_base")
        if body_id < 0:
            return
        joint_adr = self.model.body_jntadr[body_id]
        if joint_adr < 0:
            return
        joint_id = int(joint_adr)
        if self.model.jnt_type[joint_id] == mujoco.mjtJoint.mjJNT_FREE:
            self.base_free_joint_id = joint_id
            qadr = self.model.jnt_qposadr[joint_id]
            # 记录初始高度（仅用于参考，不再钉 z）
            self.base_height = self._compute_ground_height(body_id) or float(self.model.qpos0[qadr + 2])

    def _compute_ground_height(self, chassis_body_id):
        """计算 chassis freejoint 的 z 高度，使轮子/脚轮恰好触地

        对于每个接触 geom：chassis_z + body_z + geom_z - radius = 0
        所以：chassis_z = -(body_z + geom_z) + radius
        取最大值（最高的 chassis 位置使所有接触 geom 都在地面以上）。
        """
        model = self.model
        max_z = None
        for i in range(model.ngeom):
            body_id = int(model.geom_bodyid[i])
            if body_id == chassis_body_id:
                continue
            if int(model.body_parentid[body_id]) != chassis_body_id:
                continue
            if model.geom_contype[i] == 0 and model.geom_conaffinity[i] == 0:
                continue
            body_z = model.body_pos[body_id][2]
            geom_z = model.geom_pos[i][2]
            r = model.geom_size[i][0]
            chassis_z = -(body_z + geom_z) + r
            if max_z is None or chassis_z > max_z:
                max_z = chassis_z
        return max_z

    def reset(self):
        mujoco.mj_resetData(self.model, self.data)
        self.data.ctrl[:] = 0.0
        self._set_initial_arm_pose()
        self._set_initial_objects()
        self.sim.forward()
        if self.base_free_joint_id >= 0:
            self.settle_base(steps=2000)
        # PandaOmron 末端:gripper eef body(抓取吸附点),回退到 hand body
        self.virtual_ee_pos = self.get_body_pos("gripper0_right_eef", fallback="robot0_right_hand")
        return {}

    def _set_initial_arm_pose(self):
        # PandaOmron 臂初始位姿(robosuite PandaOmron.init_qpos)+ torso 抬高 + 夹爪张开。
        # 臂是力矩驱动(ctrl=0 会因重力下垂),所以记进 _arm_hold 每步重置=运动学冻结,
        # 让臂保持自然姿态、随底座刚性移动(和抓取物体的吸附是同一思路)。
        import math
        arm_pose = {
            "robot0_joint1": 0.0,
            "robot0_joint2": math.pi / 16.0 - 0.2,
            "robot0_joint3": 0.0,
            "robot0_joint4": -math.pi / 2.0 - math.pi / 3.0,
            "robot0_joint5": 0.0,
            "robot0_joint6": math.pi - 0.4,
            "robot0_joint7": math.pi / 4.0,
            "mobilebase0_joint_torso_height": 0.2,
            "gripper0_right_finger_joint1": 0.04,
            "gripper0_right_finger_joint2": -0.04,
        }
        self._arm_hold = []
        for joint_name, value in arm_pose.items():
            joint_id = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, joint_name)
            if joint_id < 0:
                continue
            qadr = int(self.model.jnt_qposadr[joint_id])
            dadr = int(self.model.jnt_dofadr[joint_id])
            self.data.qpos[qadr] = value
            self._arm_hold.append((qadr, dadr, float(value)))

    def _hold_arm_pose(self):
        """把臂/夹爪 qpos 钉回初始位姿、清零角速度(力矩臂否则重力下垂)。=运动学冻结,臂随底座刚性移动。"""
        for qadr, dadr, value in self._arm_hold:
            self.data.qpos[qadr] = value
            self.data.qvel[dadr] = 0.0

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
        self._hold_arm_pose()
        mujoco.mj_step(self.model, self.data)
        self._hold_arm_pose()  # 力矩臂每步会下垂,step 后再钉回=保持初始姿态
        if self.grasped_object:
            self.set_object_pos(self.grasped_object, self.virtual_ee_pos)
        self.sim.forward()

    def _stabilize_base(self):
        """只锁 pitch/roll，不锁 z，让物理引擎自然处理轮子-地面接触"""
        if self.base_free_joint_id < 0:
            return
        qadr = self.model.jnt_qposadr[self.base_free_joint_id]
        dadr = self.model.jnt_dofadr[self.base_free_joint_id]
        # 恢复 quaternion，只保留 yaw（防止 pitch/roll 积累）
        yaw = self._base_yaw_from_qpos(qadr)
        self.data.qpos[qadr + 3:qadr + 7] = [np.cos(yaw / 2.0), 0.0, 0.0, np.sin(yaw / 2.0)]
        # 只清 pitch/roll 角速度
        self.data.qvel[dadr + 3] = 0.0  # wx: roll
        self.data.qvel[dadr + 4] = 0.0  # wy: pitch
        self.sim.forward()

    def settle_base(self, steps=2000):
        """启动时调用，让机器人自然沉降到地面。每步冻结臂,否则力矩臂在沉降中下垂塌掉。"""
        for _ in range(steps):
            self._hold_arm_pose()
            mujoco.mj_step(self.model, self.data)
            self._hold_arm_pose()
        self._stabilize_base()

    def _base_yaw_from_qpos(self, qadr):
        w, x, y, z = self.data.qpos[qadr + 3:qadr + 7]
        return float(np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z)))

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
        # 清零该物体 6 个速度自由度(3 线+3 角):否则抓取跟随/瞬移的残留速度会让
        # 物体放下后继续滑走(薄 fixture 如 stovetop 上尤其明显 → 滑出边缘致裁判假阴性)。
        dadr = self.model.jnt_dofadr[joint_id]
        self.data.qvel[dadr:dadr + 6] = 0.0
        self.sim.forward()

    def _container_door_joint_ids(self, container):
        """返回该 fixture 名下存在的门 joint id 列表(无门则空)= 判定是否容器。"""
        jids = []
        for suffix in _DOOR_JOINT_SUFFIXES:
            jid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_JOINT, container + suffix)
            if jid >= 0:
                jids.append(jid)
        return jids

    def open_container_door(self, container):
        """转开容器的门 joint(doorhinge/door_joint/slidejoint),返回开的门名列表。
        门 range abs 最大端=开;真转门 → 渲染正确 + 真机可复现。"""
        opened = []
        for jid in self._container_door_joint_ids(container):
            qadr = self.model.jnt_qposadr[jid]
            lo, hi = float(self.model.jnt_range[jid][0]), float(self.model.jnt_range[jid][1])
            self.data.qpos[qadr] = hi if abs(hi) >= abs(lo) else lo
            opened.append(mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_JOINT, jid))
        if opened:
            self.sim.forward()
        return opened

    def list_containers(self, min_height=1.2):
        """列出可藏物的容器:有门 joint 且足够高(head_cam≈1.18m 够不到,藏里面转头看不到)。

        返回 [{name, pos}],按 x 排序(稳定遍历顺序)。min_height 滤掉矮柜/抽屉——
        它们低到 head_cam 能扫到,藏不住,不构成"逐柜翻找"的搜索成本。真机=高墙柜。
        """
        out = []
        for name, fx in self.fixtures.items():
            if not self._container_door_joint_ids(name):
                continue
            pos = np.asarray(fx.pos, dtype=float)
            if float(pos[2]) < float(min_height):
                continue
            out.append({"name": name, "pos": pos.tolist()})
        out.sort(key=lambda c: (c["pos"][0], c["pos"][1]))
        return out

    def container_top(self, container):
        """容器上方位置(开门后把里面物体抬出来露到这=可见可抓)。无此 body 返回 None。"""
        bid = mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_BODY, container)
        if bid < 0:
            return None
        pos = self.data.xpos[bid].copy()
        pos[2] += 0.5
        return pos
