import unittest

import numpy as np

from serve_3dgs.backend.gs_config import GSConfig
from serve_3dgs.backend.sim_env import SimEnv


def _camera_id(env, camera_name):
    for idx, camera in enumerate(env.model.cameras.cameras):
        if getattr(camera, "name", "") == camera_name:
            return idx
    raise AssertionError(f"camera not found: {camera_name}")


class SimEnvCameraTest(unittest.TestCase):
    def test_robot_mounted_cameras_follow_base_motion(self):
        cfg = GSConfig(scene="xlerobot")
        env = SimEnv(cfg.scene_xml, cfg)

        before = {
            name: env.get_camera_pose(_camera_id(env, name))[0].copy()
            for name in ("head_cam", "right_arm_cam", "left_arm_cam")
        }

        qpos = env.data.dof_pos.copy()
        qpos[0, 0] += 1.0
        env.data.set_dof_pos(qpos, env.model)
        env.forward_kinematic()

        for name, old_pos in before.items():
            new_pos = env.get_camera_pose(_camera_id(env, name))[0]
            delta = new_pos - old_pos
            np.testing.assert_allclose(delta[0, 0], 1.0, atol=1e-5, err_msg=name)


if __name__ == "__main__":
    unittest.main()
