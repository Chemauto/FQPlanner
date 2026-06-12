"""MotrixSim + 3DGS simulation environment for Franka Panda scene."""

from __future__ import annotations

import os
from typing import Dict, Optional, Tuple

_CUDA_HOME = "/usr/local/cuda-12.4"
if os.path.isfile(os.path.join(_CUDA_HOME, "bin", "nvcc")):
    os.environ["CUDA_HOME"] = _CUDA_HOME
    _cuda_bin = os.path.join(_CUDA_HOME, "bin")
    _lib64 = os.path.join(_CUDA_HOME, "lib64")
    if _cuda_bin not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _cuda_bin + os.pathsep + os.environ.get("PATH", "")
    if _lib64 not in os.environ.get("LD_LIBRARY_PATH", ""):
        os.environ["LD_LIBRARY_PATH"] = _lib64 + os.pathsep + os.environ.get("LD_LIBRARY_PATH", "")

_GS_VENV_BIN = "/home/fangqi/WorkXCJ/gs_playground/.venv/bin"
if os.path.isdir(_GS_VENV_BIN):
    os.environ["PATH"] = _GS_VENV_BIN + os.pathsep + os.environ.get("PATH", "")

import numpy as np
import torch


def configure_torch_cuda_arch() -> None:
    if os.environ.get("TORCH_CUDA_ARCH_LIST"):
        return
    if not torch.cuda.is_available():
        return
    archs = {
        f"{major}.{minor}"
        for device_idx in range(torch.cuda.device_count())
        for major, minor in [torch.cuda.get_device_capability(device_idx)]
    }
    if archs:
        os.environ["TORCH_CUDA_ARCH_LIST"] = ";".join(sorted(archs))


configure_torch_cuda_arch()

import motrixsim as mx
from gaussian_renderer import BatchSplatConfig, MtxBatchSplatRenderer
from motrixsim import SceneData, forward_kinematic

from .gs_config import GSConfig


class SimEnv:
    def __init__(self, model_xml: str, gs_cfg: GSConfig, batch_size: int = 1):
        self._gs_cfg = gs_cfg
        self._batch_size = batch_size

        scene = mx.msd.from_file(model_xml)

        try:
            floor_xml = """<mujoco model="floor">
  <worldbody>
    <geom name="floor" type="plane" size="10 10 0.01" rgba="0.5 0.5 0.5 1" contype="1" conaffinity="1"/>
  </worldbody>
</mujoco>"""
            scene.attach(mx.msd.from_str(floor_xml))
        except (RuntimeError, Exception):
            pass

        self.model = scene.build()
        self.data = SceneData(self.model, batch=(batch_size,))

        self._gs_renderer = None
        self._bg_renderer = None
        if gs_cfg.body_gaussians:
            self._gs_renderer = MtxBatchSplatRenderer(
                BatchSplatConfig(body_gaussians=gs_cfg.body_gaussians, background_ply=None, minibatch=batch_size),
                self.model,
            )
        if gs_cfg.background_ply:
            self._bg_renderer = MtxBatchSplatRenderer(
                BatchSplatConfig(body_gaussians={}, background_ply=gs_cfg.background_ply, minibatch=batch_size),
                self.model,
            )
        self._bg_imgs = None

        self._link_name_to_idx: Dict[str, int] = {
            name: idx for idx, name in enumerate(self.model.link_names)
        }

        self._grasped_object = None

        self.data.reset(self.model)
        forward_kinematic(self.model, self.data)

    def step(self, n: int = 1) -> None:
        for _ in range(n):
            mx.step(self.model, self.data)

    def forward_kinematic(self) -> None:
        forward_kinematic(self.model, self.data)

    def get_link_poses(self) -> np.ndarray:
        poses = self.model.get_link_poses(self.data)
        return np.asarray(poses)

    def get_body_xpos(self, body_name: str) -> np.ndarray:
        idx = self._link_name_to_idx[body_name]
        poses = self.model.get_link_poses(self.data)
        if poses.ndim == 3:
            return np.asarray(poses[0, idx, :3])
        return np.asarray(poses[idx, :3])

    def get_body_xquat(self, body_name: str) -> np.ndarray:
        idx = self._link_name_to_idx[body_name]
        poses = self.model.get_link_poses(self.data)
        if poses.ndim == 3:
            return np.asarray(poses[0, idx, 3:7])
        return np.asarray(poses[idx, 3:7])

    def get_camera_pose(self, cam_id: int = 0) -> Tuple[np.ndarray, np.ndarray, float]:
        cam = self.model.cameras[int(cam_id)]
        pose = np.asarray(cam.get_pose(self.data), dtype=np.float32)
        if pose.ndim == 1:
            pose = pose[None, :]
        if pose.ndim >= 3:
            pose = pose.reshape(pose.shape[0], -1, pose.shape[-1])[:, 0, :]
        pos = pose[:, :3].astype(np.float32)
        quat = pose[:, 3:7].astype(np.float32)
        quat /= np.linalg.norm(quat, axis=1, keepdims=True) + 1e-12
        return pos, quat, float(getattr(cam, "fovy", 45.0))

    def render_frame(self, cam_id: int = 0, width: int = 640, height: int = 480) -> np.ndarray:
        if self._gs_renderer is None and self._bg_renderer is None:
            return np.zeros((height, width, 3), dtype=np.uint8)

        self.forward_kinematic()
        link_poses = self.model.get_link_poses(self.data)
        body_pos = link_poses[..., :3]
        body_quat = link_poses[..., 3:7]

        cam_pos, cam_quat, fovy = self.get_camera_pose(cam_id)
        cam_xmat = np.stack([self._quat_to_xmat(q) for q in cam_quat], axis=0)

        active_renderer = self._gs_renderer or self._bg_renderer
        device = active_renderer.device
        cam_pos_t = torch.from_numpy(cam_pos[:, None, :]).to(device=device, dtype=torch.float32)
        cam_xmat_t = torch.from_numpy(cam_xmat[:, None, :, :]).to(device=device, dtype=torch.float32)
        fovy_np = np.full((cam_pos.shape[0], 1), fovy, dtype=np.float32)

        if self._bg_renderer is not None and self._bg_imgs is None:
            bg_gsb = self._bg_renderer.batch_update_gaussians(body_pos, body_quat)
            self._bg_imgs, _ = self._bg_renderer.batch_env_render(
                bg_gsb, cam_pos_t, cam_xmat_t, int(height), int(width), fovy_np
            )

        if self._gs_renderer is not None:
            gsb = self._gs_renderer.batch_update_gaussians(body_pos, body_quat)
            rgb_t, _ = self._gs_renderer.batch_env_render(
                gsb, cam_pos_t, cam_xmat_t, int(height), int(width), fovy_np, bg_imgs=self._bg_imgs
            )
        elif self._bg_imgs is not None:
            rgb_t = self._bg_imgs
        else:
            return np.zeros((height, width, 3), dtype=np.uint8)
        rgb = rgb_t.detach().cpu().numpy() if isinstance(rgb_t, torch.Tensor) else np.asarray(rgb_t)
        # rgb shape: (Nenv, Ncam, H, W, 3)
        rgb = rgb[0, 0]  # (H, W, 3)
        return (np.clip(rgb, 0.0, 1.0) * 255.0).astype(np.uint8)

    @staticmethod
    def _quat_to_xmat(quat_xyzw: np.ndarray) -> np.ndarray:
        x, y, z, w = np.asarray(quat_xyzw, dtype=np.float64)
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

    @property
    def grasped_object(self) -> Optional[str]:
        return self._grasped_object

    @grasped_object.setter
    def grasped_object(self, value: Optional[str]):
        self._grasped_object = value
