# serve_3dgs MotrixSim + 3DGS Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace serve_3dgs MuJoCo/DISCOVERSE backends with MotrixSim physics + batch 3DGS rendering as the sole simulation backend for FQPlanner.

**Architecture:** New `backend/sim_env.py` wraps MotrixSim SceneModel/SceneData with MtxBatchSplatRenderer for 3DGS rendering. `tools/arm.py` and `tools/move.py` are rewritten to use MotrixSim API. `service/server.py` keeps its command-queue Flask architecture but swaps the backend. `main.py` simplifies to a single MotrixSim entry point.

**Tech Stack:** MotrixSim (motrixsim_core), gaussian_renderer (MtxBatchSplatRenderer, GSRendererMotrixSim), gsplat, PyTorch+CUDA 12.8, Flask

**Design doc:** `docs/superpowers/specs/2026-06-12-serve-3dgs-motrixsim-migration-design.md`

---

### Task 1: Set up project dependencies

**Files:**
- Create: `serve_3dgs/requirements_3dgs.txt`
- Modify: `serve_3dgs/backend/__init__.py`

- [ ] **Step 1: Create requirements file**

```txt
# serve_3dgs/requirements_3dgs.txt
# MotrixSim physics + 3DGS rendering
motrixsim_core>=0.7.1
torch>=2.7.0
gaussian_renderer>=0.2.0
gsplat>=1.5.3
scipy>=1.14
numpy>=2.0
flask>=3.0
flask-cors>=6.0
rich>=14.0
pyyaml>=6.0
```

- [ ] **Step 2: Update backend/__init__.py docstring**

```python
# serve_3dgs/backend/__init__.py
"""MotrixSim + 3DGS backend runtime package."""
```

- [ ] **Step 3: Install dependencies and verify**

```bash
cd /home/fangqi/WorkXCJ/FQPlanner_Mujoco3DGSNew
pip install -r serve_3dgs/requirements_3dgs.txt
python -c "import motrixsim as mx; import torch; print('MotrixSim OK, CUDA:', torch.cuda.is_available())"
```

Expected: `MotrixSim OK, CUDA: True`

- [ ] **Step 4: Commit**

```bash
git add serve_3dgs/requirements_3dgs.txt serve_3dgs/backend/__init__.py
git commit -m "chore: add MotrixSim + 3DGS dependencies for serve_3dgs"
```

---

### Task 2: Create GSConfig — 3DGS asset path configuration

**Files:**
- Create: `serve_3dgs/backend/gs_config.py`

- [ ] **Step 1: Create gs_config.py**

```python
"""3DGS asset path configuration for Franka Panda scene."""

from pathlib import Path
from typing import Dict


class GSConfig:
    """Manages 3DGS asset paths. Defaults to gs_playground Franka Panda assets."""

    def __init__(self, assets_dir: str):
        self.assets_dir = Path(assets_dir)
        self.robot_dir = self.assets_dir / "models" / "robots" / "manipulation" / "franka_emika_panda_robotiq"
        self.task_dir = self.assets_dir / "models" / "tasks" / "table30" / "_04_hang_toothbrush_cup"

    @property
    def scene_xml(self) -> str:
        return (self.robot_dir / "xmls" / "table30_04_hang_toothbrush_cup.xml").as_posix()

    @property
    def body_gaussians(self) -> Dict[str, str]:
        robot_3dgs = self.robot_dir / "3dgs"
        task_3dgs = self.task_dir / "3dgs"
        d: Dict[str, str] = {}
        for i in range(1, 8):
            d[f"link{i}"] = (robot_3dgs / "franka" / f"link{i}.ply").as_posix()
        for name in ("robotiq_base", "left_driver", "left_coupler", "left_spring_link", "left_follower",
                      "right_driver", "right_coupler", "right_spring_link", "right_follower"):
            d[name] = (robot_3dgs / "robotiq" / f"{name}.ply").as_posix()
        d["toothbrush_cup"] = (task_3dgs / "toothbrush_cup.ply").as_posix()
        d["rack"] = (task_3dgs / "rack.ply").as_posix()
        return d

    @property
    def background_ply(self) -> str:
        return (self.robot_dir / "3dgs" / "background_085.ply").as_posix()
```

- [ ] **Step 2: Verify assets exist**

```bash
python -c "
from serve_3dgs.backend.gs_config import GSConfig
cfg = GSConfig('/home/fangqi/WorkXCJ/gs_playground/demo/live_demo/assets')
import os
assert os.path.exists(cfg.scene_xml), f'Missing: {cfg.scene_xml}'
assert os.path.exists(cfg.background_ply), f'Missing: {cfg.background_ply}'
for name, path in cfg.body_gaussians.items():
    assert os.path.exists(path), f'Missing {name}: {path}'
print('All 3DGS assets verified:', len(cfg.body_gaussians), 'body gaussians + background')
"
```

Expected: `All 3DGS assets verified: 18 body gaussians + background`

- [ ] **Step 3: Commit**

```bash
git add serve_3dgs/backend/gs_config.py
git commit -m "feat(serve_3dgs): add GSConfig for Franka Panda 3DGS assets"
```

---

### Task 3: Create SimEnv — MotrixSim + 3DGS core environment

**Files:**
- Create: `serve_3dgs/backend/sim_env.py`

This is the most critical file. It wraps MotrixSim model/data and 3DGS rendering.

- [ ] **Step 1: Create sim_env.py**

```python
"""MotrixSim simulation environment with 3DGS rendering."""

from __future__ import annotations

import os
from typing import Dict, Optional, Tuple

import motrixsim as mx
import numpy as np
import torch

from .gs_config import GSConfig


def _configure_torch_cuda_arch() -> None:
    if os.environ.get("TORCH_CUDA_ARCH_LIST"):
        return
    if not torch.cuda.is_available():
        return
    archs = {
        f"{major}.{minor}"
        for d in range(torch.cuda.device_count())
        for major, minor in [torch.cuda.get_device_capability(d)]
    }
    if archs:
        os.environ["TORCH_CUDA_ARCH_LIST"] = ";".join(sorted(archs))


_configure_torch_cuda_arch()

from gaussian_renderer import BatchSplatConfig, MtxBatchSplatRenderer


class SimEnv:
    """Wraps MotrixSim SceneModel + SceneData with 3DGS batch rendering."""

    def __init__(self, model_xml: str, gs_cfg: GSConfig, batch_size: int = 1):
        world = mx.msd.from_file(model_xml)
        self.model: mx.SceneModel = world.build()
        self.data: mx.SceneData = mx.SceneData(self.model, batch=(batch_size,))

        self.gs_renderer = MtxBatchSplatRenderer(
            BatchSplatConfig(body_gaussians=gs_cfg.body_gaussians, minibatch=batch_size),
            self.model,
        )
        self.bg_renderer = MtxBatchSplatRenderer(
            BatchSplatConfig(background_ply=gs_cfg.background_ply, minibatch=batch_size),
            self.model,
        )

        self.data.reset(self.model)
        mx.forward_kinematic(self.model, self.data)

        self._grasped_object: Optional[str] = None
        self._bg_imgs: Optional[object] = None
        self._link_name_to_idx: Dict[str, int] = {}
        for i, name in enumerate(self.model.link_names):
            if name:
                self._link_name_to_idx[name] = i

    @property
    def grasped_object(self) -> Optional[str]:
        return self._grasped_object

    @grasped_object.setter
    def grasped_object(self, value: Optional[str]):
        self._grasped_object = value

    def step(self, n: int = 1) -> None:
        for _ in range(n):
            mx.step(self.model, self.data)

    def forward_kinematic(self) -> None:
        mx.forward_kinematic(self.model, self.data)

    def get_link_poses(self) -> np.ndarray:
        poses = self.model.get_link_poses(self.data)
        return poses.reshape(-1, poses.shape[-1])

    def get_body_xpos(self, body_name: str) -> np.ndarray:
        idx = self._link_name_to_idx.get(body_name)
        if idx is None:
            raise KeyError(f"Body '{body_name}' not found in model. Available: {list(self._link_name_to_idx.keys())}")
        poses = self.model.get_link_poses(self.data)
        pose = poses.reshape(-1, poses.shape[-1])
        return pose[idx, :3].copy()

    def get_body_xquat(self, body_name: str) -> np.ndarray:
        idx = self._link_name_to_idx.get(body_name)
        if idx is None:
            raise KeyError(f"Body '{body_name}' not found")
        poses = self.model.get_link_poses(self.data)
        pose = poses.reshape(-1, poses.shape[-1])
        return pose[idx, 3:7].copy()

    def get_camera_pose(self, cam_id: int) -> Tuple[np.ndarray, np.ndarray, float]:
        cam = self.model.cameras[cam_id]
        pose = np.asarray(cam.get_pose(self.data), dtype=np.float32)
        if pose.ndim > 1:
            pose = pose.reshape(-1, pose.shape[-1])[0]
        pos = pose[:3].astype(np.float32)
        quat = pose[3:7].astype(np.float32)
        fovy = float(getattr(cam, "fovy", 45.0))
        return pos, quat, fovy

    def render_frame(self, cam_id: int = 0, width: int = 640, height: int = 480) -> np.ndarray:
        self.forward_kinematic()
        link_poses = self.model.get_link_poses(self.data)
        shape = link_poses.shape
        pose_flat = link_poses.reshape(-1, shape[-1])
        body_pos = pose_flat[:, :3]
        body_quat = pose_flat[:, 3:7]

        cam_pos, cam_quat, fovy = self.get_camera_pose(cam_id)

        device = self.gs_renderer.device
        cam_pos_t = torch.from_numpy(cam_pos[None, None, :]).to(device=device, dtype=torch.float32)
        cam_xmat = self._quat_to_xmat(cam_quat)
        cam_xmat_t = torch.from_numpy(cam_xmat[None, None, :, :]).to(device=device, dtype=torch.float32)
        fovy_np = np.array([[fovy]], dtype=np.float32)

        if self._bg_imgs is None:
            bg_gsb = self.bg_renderer.batch_update_gaussians(body_pos[None], body_quat[None])
            self._bg_imgs, _ = self.bg_renderer.batch_env_render(
                bg_gsb, cam_pos_t, cam_xmat_t, height, width, fovy_np
            )

        gsb = self.gs_renderer.batch_update_gaussians(body_pos[None], body_quat[None])
        rgb_t, _ = self.gs_renderer.batch_env_render(
            gsb, cam_pos_t, cam_xmat_t, height, width, fovy_np, bg_imgs=self._bg_imgs
        )

        rgb = rgb_t.detach().cpu().numpy()
        if rgb.ndim == 5 and rgb.shape[2] == 3:
            rgb = np.transpose(rgb, (0, 1, 3, 4, 2))
        if rgb.ndim == 5 and rgb.shape[1] == 1:
            rgb = rgb.squeeze(1)
        if rgb.ndim == 5:
            rgb = rgb[0]
        if rgb.ndim == 4 and rgb.shape[0] == 1:
            rgb = rgb[0]
        if rgb.ndim == 4 and rgb.shape[-1] != 3:
            rgb = np.transpose(rgb, (0, 2, 3, 1))
        if rgb.ndim == 3 and rgb.shape[-1] != 3:
            rgb = np.transpose(rgb, (1, 2, 0))

        return (np.clip(rgb, 0.0, 1.0) * 255.0).astype(np.uint8)

    @staticmethod
    def _quat_to_xmat(quat_xyzw: np.ndarray) -> np.ndarray:
        x, y, z, w = quat_xyzw
        n = x * x + y * y + z * z + w * w
        if n < 1e-12:
            return np.eye(3, dtype=np.float32)
        s = 2.0 / n
        xx, yy, zz = x * x * s, y * y * s, z * z * s
        xy, xz, yz = x * y * s, x * z * s, y * z * s
        wx, wy, wz = w * x * s, w * y * s, w * z * s
        return np.array(
            [
                [1.0 - yy - zz, xy - wz, xz + wy],
                [xy + wz, 1.0 - xx - zz, yz - wx],
                [xz - wy, yz + wx, 1.0 - xx - yy],
            ],
            dtype=np.float32,
        )
```

- [ ] **Step 2: Test SimEnv loads and renders**

```bash
cd /home/fangqi/WorkXCJ/FQPlanner_Mujoco3DGSNew
python -c "
from serve_3dgs.backend.gs_config import GSConfig
from serve_3dgs.backend.sim_env import SimEnv
cfg = GSConfig('/home/fangqi/WorkXCJ/gs_playground/demo/live_demo/assets')
print('Loading MotrixSim model...')
env = SimEnv(cfg.scene_xml, cfg_cfg)
print('Model loaded. Links:', len(env.model.link_names))
print('DOF pos shape:', env.data.dof_pos.shape)
env.step(10)
print('Step OK')
print('Available bodies:', list(env._link_name_to_idx.keys())[:10])
"
```

Expected: Model loads, steps successfully, shows link names.

- [ ] **Step 3: Commit**

```bash
git add serve_3dgs/backend/sim_env.py
git commit -m "feat(serve_3dgs): add SimEnv with MotrixSim + 3DGS rendering"
```

---

### Task 4: Rewrite tools/arm.py for MotrixSim

**Files:**
- Modify: `serve_3dgs/tools/arm.py`

The existing arm.py uses MuJoCo-specific `env.sim.model/data`, `env.data.ctrl`, `env.sim.model.body(name).jntadr`, etc. Rewrite to use `env.model.link_names`, `env.data.dof_pos`, `env.data.actuator_ctrls`.

- [ ] **Step 1: Read the current arm.py to identify all MuJoCo-specific calls**

Key MuJoCo patterns to replace:
- `env.sim.model._model.body(name).jntadr` → `env.model.link_names.index(name)`, then find dof offset
- `env.sim.model._model.body(name).xpos` → `env.get_body_xpos(name)`
- `env.sim.data.qpos` → `env.data.dof_pos`
- `env.sim.data.ctrl` → `env.data.actuator_ctrls`
- `env.sim.forward()` → `env.forward_kinematic()`
- `env.step()` → `env.step()`
- `env.virtual_ee_pos` → store on SimEnv or ArmController

- [ ] **Step 2: Rewrite arm.py**

Replace the entire file with MotrixSim-compatible implementation. Key functions:

```python
"""Arm control tools for MotrixSim backend."""

import numpy as np
from typing import Optional, Dict

from ..backend.sim_env import SimEnv


def get_arm_info(env: SimEnv) -> dict:
    """Returns arm state: ee_pos, gripper state, joint positions."""
    env.forward_kinematic()
    try:
        ee_pos = env.get_body_xpos("virtual_ee")
    except KeyError:
        ee_pos = env.get_body_xpos("link7")
    try:
        ee_quat = env.get_body_xquat("virtual_ee")
    except KeyError:
        ee_quat = env.get_body_xquat("link7")

    info = {
        "ee_pos": ee_pos.tolist(),
        "ee_quat": ee_quat.tolist(),
        "arm_qpos": env.data.dof_pos.tolist(),
        "grasped_object": env.grasped_object,
    }
    return info


def move_arm(env: SimEnv, target_pos: np.ndarray, max_steps: int = 200,
             pos_threshold: float = 0.03, gain: float = 1.5) -> bool:
    """Virtual end-effector positioning. Steps env toward target."""
    for _ in range(max_steps):
        env.forward_kinematic()
        try:
            ee_pos = env.get_body_xpos("virtual_ee")
        except KeyError:
            ee_pos = env.get_body_xpos("link7")
        error = target_pos - ee_pos
        dist = np.linalg.norm(error)
        if dist < pos_threshold:
            return True
        delta = error * gain * 0.01
        ee_pos += delta
        try:
            _set_ee_pos(env, ee_pos)
        except (KeyError, NotImplementedError):
            break
        env.step(1)
    return False


def _set_ee_pos(env: SimEnv, target_pos: np.ndarray) -> None:
    """Set virtual end-effector position (stub - needs IK or direct body manipulation)."""
    raise NotImplementedError("Virtual EE positioning requires IK solver for MotrixSim")


def open_gripper(env: SimEnv, steps: int = 10) -> None:
    """Open gripper by setting actuator ctrl."""
    _set_gripper_ctrl(env, 0.0)
    env.step(steps)


def close_gripper(env: SimEnv, steps: int = 10) -> None:
    """Close gripper by setting actuator ctrl."""
    _set_gripper_ctrl(env, 1.0)
    env.step(steps)


def _set_gripper_ctrl(env: SimEnv, value: float) -> None:
    """Set gripper actuator control."""
    for i, name in enumerate(getattr(env.model, 'actuator_names', [])):
        if name and ("jaw" in name.lower() or "gripper" in name.lower()):
            env.data.actuator_ctrls[i] = value
            return
    if env.data.actuator_ctrls.size > 0:
        env.data.actuator_ctrls[-1] = value


def get_obj_pos(env: SimEnv, obj_name: str) -> np.ndarray:
    return env.get_body_xpos(obj_name)


def is_grasped(env: SimEnv, obj_name: str, threshold: float = 0.035) -> bool:
    return env.grasped_object == obj_name


def grasp(env: SimEnv, obj_name: str, snap_threshold: float = 0.15) -> dict:
    """Grasp object: approach → close gripper → mark as grasped."""
    env.forward_kinematic()
    obj_pos = get_obj_pos(env, obj_name)

    try:
        ee_pos = env.get_body_xpos("virtual_ee")
    except KeyError:
        ee_pos = env.get_body_xpos("link7")

    dist = np.linalg.norm(obj_pos - ee_pos)
    if dist > snap_threshold:
        return {"success": False, "reason": f"Object too far: {dist:.3f} > {snap_threshold}"}

    close_gripper(env, steps=20)
    env.grasped_object = obj_name
    return {"success": True}


def place(env: SimEnv, obj_name: str, target_pos: np.ndarray,
          snap_threshold: float = 0.15) -> dict:
    """Place object: open gripper → mark as released."""
    if env.grasped_object != obj_name:
        return {"success": False, "reason": f"Not grasping {obj_name}"}
    open_gripper(env, steps=20)
    env.grasped_object = None
    return {"success": True}
```

- [ ] **Step 3: Verify import and basic function calls**

```bash
cd /home/fangqi/WorkXCJ/FQPlanner_Mujoco3DGSNew
python -c "
from serve_3dgs.backend.gs_config import GSConfig
from serve_3dgs.backend.sim_env import SimEnv
from serve_3dgs.tools.arm import get_arm_info, open_gripper, close_gripper
cfg = GSConfig('/home/fangqi/WorkXCJ/gs_playground/demo/live_demo/assets')
env = SimEnv(cfg.scene_xml, cfg)
info = get_arm_info(env)
print('Arm info keys:', list(info.keys()))
print('EE pos:', info['ee_pos'])
"
```

Expected: Prints arm info with EE position.

- [ ] **Step 4: Commit**

```bash
git add serve_3dgs/tools/arm.py
git commit -m "feat(serve_3dgs): rewrite arm.py for MotrixSim backend"
```

---

### Task 5: Rewrite tools/move.py for MotrixSim

**Files:**
- Modify: `serve_3dgs/tools/move.py`

Replace MuJoCo wheel actuator ctrl with MotrixSim floating base API.

- [ ] **Step 1: Rewrite move.py**

```python
"""Base movement tools for MotrixSim backend."""

import math
import numpy as np
from typing import Optional, Dict


def get_base_info(env) -> dict:
    """Get base position, yaw, and velocities from MotrixSim floating base."""
    env.forward_kinematic()

    pos = np.zeros(3, dtype=np.float32)
    quat = np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32)
    vel = np.zeros(6, dtype=np.float32)

    if env.model.floating_bases:
        base = env.model.floating_bases[0]
        pos = np.asarray(base.get_translation(env.data), dtype=np.float32).copy()
        rot = np.asarray(base.get_rotation(env.data), dtype=np.float32).copy()
        vel = np.asarray(base.get_dof_vel(env.data), dtype=np.float32).copy()
        quat = rot

    yaw = math.atan2(2.0 * (quat[1]*quat[3] + quat[0]*quat[2]),
                     1.0 - 2.0 * (quat[1]**2 + quat[2]**2))

    return {
        "pos": pos.tolist(),
        "yaw_rad": yaw,
        "yaw_deg": math.degrees(yaw),
        "vx": float(vel[0]) if vel.size > 0 else 0.0,
        "vy": float(vel[1]) if vel.size > 1 else 0.0,
        "wz": float(vel[5]) if vel.size > 5 else 0.0,
    }


def set_base_velocity(env, vx: float = 0.0, vy: float = 0.0, wz: float = 0.0) -> None:
    """Directly set floating base velocity."""
    if env.model.floating_bases:
        base = env.model.floating_bases[0]
        vel = np.asarray(base.get_dof_vel(env.data), dtype=np.float32).copy()
        if vel.size >= 6:
            vel[0] = vx
            vel[1] = vy
            vel[5] = wz
            base.set_dof_vel(env.data, vel)


def move(env, Vx: float = 0.0, Vy: float = 0.0, Vw: float = 0.0, steps: int = 1) -> None:
    """Set base velocity and step simulation."""
    set_base_velocity(env, Vx, Vy, Vw)
    env.step(steps)


def stop_base(env) -> None:
    """Zero all base velocities."""
    set_base_velocity(env, 0.0, 0.0, 0.0)


def nav(env, x: float, y: float, target_yaw: float = None,
        speed: float = 0.5, Kp: float = 2.5, Kd: float = 0.3,
        pos_threshold: float = 0.1, yaw_threshold: float = 3.0,
        max_steps: int = 800) -> dict:
    """PD-controlled navigation to target position."""
    for _ in range(max_steps):
        info = get_base_info(env)
        dx = x - info["pos"][0]
        dy = y - info["pos"][1]
        dist = math.sqrt(dx**2 + dy**2)

        if dist < pos_threshold:
            if target_yaw is not None:
                yaw_err = target_yaw - info["yaw_rad"]
                yaw_err = (yaw_err + math.pi) % (2 * math.pi) - math.pi
                if abs(math.degrees(yaw_err)) < yaw_threshold:
                    stop_base(env)
                    return {"success": True, "pos": info["pos"], "yaw_rad": info["yaw_rad"]}
            else:
                stop_base(env)
                return {"success": True, "pos": info["pos"], "yaw_rad": info["yaw_rad"]}

        heading = math.atan2(dy, dx)
        yaw_err = heading - info["yaw_rad"]
        yaw_err = (yaw_err + math.pi) % (2 * math.pi) - math.pi

        forward = speed * math.cos(yaw_err) * min(dist, 0.5)
        wz = Kp * yaw_err

        set_base_velocity(env, forward, 0.0, wz)
        env.step(1)

    stop_base(env)
    return {"success": False, "reason": "max_steps reached"}
```

- [ ] **Step 2: Verify import**

```bash
cd /home/fangqi/WorkXCJ/FQPlanner_Mujoco3DGSNew
python -c "
from serve_3dgs.backend.gs_config import GSConfig
from serve_3dgs.backend.sim_env import SimEnv
from serve_3dgs.tools.move import get_base_info, stop_base
cfg = GSConfig('/home/fangqi/WorkXCJ/gs_playground/demo/live_demo/assets')
env = SimEnv(cfg.scene_xml, cfg)
info = get_base_info(env)
print('Base info:', info)
"
```

- [ ] **Step 3: Commit**

```bash
git add serve_3dgs/tools/move.py
git commit -m "feat(serve_3dgs): rewrite move.py for MotrixSim floating base"
```

---

### Task 6: Adapt service/server.py for MotrixSim

**Files:**
- Modify: `serve_3dgs/service/server.py`

This is a large file (1182 lines). The key changes:

1. **Remove** all MuJoCo-specific imports (`mujoco`)
2. **Remove** `_base_cmd` dict's `data.ctrl` writes — replace with `tools.move.set_base_velocity()`
3. **Remove** `apply_base_velocity` freejoint qvel writing — replace with `tools.move.set_base_velocity()`
4. **Remove** `GET /map_data` and `GET /scan` endpoints
5. **Replace** screenshot/camera rendering with `env.render_frame()`
6. **Keep** command queue architecture, Flask routes, `_step_active_command` logic
7. **Update** `process_commands` to call new tools

- [ ] **Step 1: Identify all MuJoCo-specific code blocks in server.py**

Lines to change (approximate):
- Imports: remove `import mujoco`, add `from ..backend.sim_env import SimEnv`
- `_env_holder` and global state: keep as-is
- `apply_base_velocity()` (line 236-290): Replace freejoint qvel + ctrl writes with `tools.move.set_base_velocity(env, Vx, Vy, Vw)`
- `process_commands()` (line 491): Update tool calls (`move_arm`, `grasp`, `place`, `nav`, `move`)
- `_step_active_command()` (line 368): Update nav/grasp/place phases to use new tools
- `GET /map_data` (line 1049): Remove
- `GET /scan` (line 1059): Remove
- `POST /screenshot` (line 1133): Replace `env.sim.render()` with `env.render_frame()`
- `GET /camera/latest` (line 1155): Replace with `env.render_frame()`
- `GET /state_qpos` (line 636): Read `env.data.dof_pos` directly

- [ ] **Step 2: Apply changes to server.py**

Due to the file size (1182 lines), make targeted edits:

**a) Replace imports (top of file):**
Remove `import mujoco as mj` and MuJoCo-related imports. Keep Flask, numpy, threading, etc. Add:
```python
import base64, io, time, threading, json, math, numpy as np
from flask import Flask, request, jsonify, send_file
from PIL import Image
```

**b) Replace `apply_base_velocity()` function:**
Replace the entire function body with:
```python
def apply_base_velocity(env):
    now = time.time()
    if now >= _base_cmd.get("expires_at", 0):
        return False
    from ..tools.move import set_base_velocity
    set_base_velocity(env, _base_cmd["Vx"], _base_cmd["Vy"], _base_cmd["Vw"])
    return True
```

**c) Replace screenshot rendering in process_commands:**
Replace `env.sim.render()` calls with:
```python
from ..backend.sim_env import SimEnv
rgb = env.render_frame(cam_id=cam_id, width=w, height=h)
img = Image.fromarray(rgb)
buf = io.BytesIO()
img.save(buf, format='JPEG', quality=85)
return base64.b64encode(buf.getvalue()).decode('utf-8')
```

**d) Remove `/map_data` and `/scan` routes:**
Delete both route functions entirely.

**e) Update `get_base_action()`:**
Replace ctrl-based logic:
```python
def get_base_action():
    now = time.time()
    if now >= _base_cmd.get("expires_at", 0):
        return None
    return (_base_cmd["Vx"], _base_cmd["Vy"], _base_cmd["Vw"])
```

- [ ] **Step 3: Verify server starts**

```bash
cd /home/fangqi/WorkXCJ/FQPlanner_Mujoco3DGSNew
python -c "
from serve_3dgs.backend.gs_config import GSConfig
from serve_3dgs.backend.sim_env import SimEnv
from serve_3dgs.service.server import start_server, app
print('Server module loaded OK')
print('Routes:', [r.rule for r in app.url_map.iter_rules()])
"
```

Expected: Prints route list without `/map_data` and `/scan`.

- [ ] **Step 4: Commit**

```bash
git add serve_3dgs/service/server.py
git commit -m "feat(serve_3dgs): adapt server.py for MotrixSim + 3DGS backend"
```

---

### Task 7: Rewrite main.py — Single MotrixSim entry point

**Files:**
- Modify: `serve_3dgs/main.py`

- [ ] **Step 1: Rewrite main.py**

Replace entire file:

```python
"""serve_3dgs — MotrixSim + 3DGS simulation backend for FQPlanner."""

from __future__ import annotations

import argparse
import threading

from serve_3dgs.backend.gs_config import GSConfig
from serve_3dgs.backend.sim_env import SimEnv
from serve_3dgs.service.server import start_server, process_commands, apply_base_velocity


def main() -> None:
    parser = argparse.ArgumentParser(description="serve_3dgs - MotrixSim + 3DGS backend")
    parser.add_argument("--port", type=int, default=5002)
    parser.add_argument("--gs_assets", type=str,
                        default="/home/fangqi/WorkXCJ/gs_playground/demo/live_demo/assets")
    parser.add_argument("--no-viewer", action="store_true")
    parser.add_argument("--gs_w", type=int, default=640)
    parser.add_argument("--gs_h", type=int, default=480)
    parser.add_argument("--physics_steps_per_loop", type=int, default=10)
    args = parser.parse_args()

    gs_cfg = GSConfig(args.gs_assets)
    print(f"Loading scene: {gs_cfg.scene_xml}")
    env = SimEnv(gs_cfg.scene_xml, gs_cfg)
    print(f"Model loaded: {env.model.num_links} links, {env.model.num_dof_pos} DOFs")

    start_server(env, port=args.port)
    print(f"HTTP server started on port {args.port}")

    try:
        from motrixsim.render import RenderApp

        if not args.no_viewer:
            print("Starting viewer (close window to exit)...")
            with RenderApp() as render:
                render.launch(env.model)
                render.sync(env.data)
                while not render.is_closed:
                    with _env_lock():
                        process_commands(env)
                        apply_base_velocity(env)
                    for _ in range(args.physics_steps_per_loop):
                        env.step()
                    env.forward_kinematic()
                    render.sync(env.data)
        else:
            print("Running headless (Ctrl+C to stop)...")
            while True:
                process_commands(env)
                apply_base_velocity(env)
                for _ in range(args.physics_steps_per_loop):
                    env.step()
    except ImportError:
        print("RenderApp not available, running headless...")
        while True:
            process_commands(env)
            apply_base_velocity(env)
            for _ in range(args.physics_steps_per_loop):
                env.step()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify main.py runs (headless)**

```bash
cd /home/fangqi/WorkXCJ/FQPlanner_Mujoco3DGSNew
timeout 15 python -m serve_3dgs.main --no-viewer 2>&1 || true
```

Expected: Prints "Loading scene...", "Model loaded...", "HTTP server started...", "Running headless...", then times out after 15s.

- [ ] **Step 3: Commit**

```bash
git add serve_3dgs/main.py
git commit -m "feat(serve_3dgs): rewrite main.py as single MotrixSim entry point"
```

---

### Task 8: Clean up — Delete old backends, verify end-to-end

**Files:**
- Delete: `serve_3dgs/discoverse_backend/` (entire directory)
- Modify: `robot_api/config.yaml` — update `mujoco_3dgs` backend config

- [ ] **Step 1: Delete discoverse_backend directory**

```bash
rm -rf /home/fangqi/WorkXCJ/FQPlanner_Mujoco3DGSNew/serve_3dgs/discoverse_backend
```

- [ ] **Step 2: Update robot_api/config.yaml**

In `robot_api/config.yaml`, update the `mujoco_3dgs` entry:
```yaml
  mujoco_3dgs:
    enabled: 1
    provide_state: 1
    accept_action: 1
    required: 1
    url: "http://127.0.0.1:5002"
    timeout: 30
```

- [ ] **Step 3: End-to-end smoke test**

```bash
cd /home/fangqi/WorkXCJ/FQPlanner_Mujoco3DGSNew
timeout 20 python -m serve_3dgs.main --no-viewer &
SERVER_PID=$!
sleep 10

echo "=== Test /status ==="
curl -s http://127.0.0.1:5002/status | python -m json.tool

echo "=== Test /base_status ==="
curl -s http://127.0.0.1:5002/base_status | python -m json.tool

echo "=== Test /screenshot ==="
curl -s -X POST http://127.0.0.1:5002/screenshot | head -c 100
echo "..."

kill $SERVER_PID 2>/dev/null
wait $SERVER_PID 2>/dev/null
```

Expected: `/status` returns arm info with ee_pos, `/base_status` returns pos/yaw, `/screenshot` returns base64 JPEG data.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat(serve_3dgs): remove discoverse_backend, update robot_api config"
```

---

### Task 9: Final integration test

- [ ] **Step 1: Run full server and test robot_api connection**

```bash
cd /home/fangqi/WorkXCJ/FQPlanner_Mujoco3DGSNew
timeout 30 python -m serve_3dgs.main --no-viewer &
SERVER_PID=$!
sleep 15

python -c "
from robot_api.client import RobotClient
client = RobotClient()
print('Scene:', client.get_scene())
print('Status:', client.get_arm_status())
print('Base:', client.get_base_status())
"

kill $SERVER_PID 2>/dev/null
wait $SERVER_PID 2>/dev/null
```

- [ ] **Step 2: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix(serve_3dgs): integration test fixes"
```
