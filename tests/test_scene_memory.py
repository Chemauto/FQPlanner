import sys
import tempfile
import unittest
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVE_DIR = PROJECT_ROOT / "serve"
if str(SERVE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVE_DIR))

from scene import scene_memory


class FakeEnv:
    obj_body_id = {"apple": 1, "mug": 2}

    def get_object_pos(self, name):
        return {"apple": [0.0, 0.0, 0.9], "mug": [2.0, 0.0, 0.9]}[name]


class SceneMemoryTests(unittest.TestCase):
    def test_build_initial_state_assigns_objects_to_nearest_waypoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp)
            (cfg / "waypoints.yaml").write_text(
                yaml.safe_dump({
                    "waypoints": [
                        {"name": "nav_a", "pos": [0.1, 0.0, 0.0], "serves": ["counter"]},
                        {"name": "nav_b", "pos": [2.1, 0.0, 0.0], "serves": ["island"]},
                    ]
                }),
                encoding="utf-8",
            )
            (cfg / "objects.yaml").write_text(
                yaml.safe_dump({
                    "objects": [
                        {"name": "apple", "placement": {"fixture": "counter"}},
                        {"name": "mug", "placement": {"fixture": "island"}},
                    ]
                }),
                encoding="utf-8",
            )

            old_waypoints = scene_memory.WAYPOINTS_PATH
            old_dir = scene_memory._DIR
            try:
                scene_memory.WAYPOINTS_PATH = str(cfg / "waypoints.yaml")
                scene_memory._DIR = str(cfg)
                state = scene_memory.build_initial_state(FakeEnv())
            finally:
                scene_memory.WAYPOINTS_PATH = old_waypoints
                scene_memory._DIR = old_dir

        self.assertEqual(state["locations"]["nav_a"]["objects"], ["apple"])
        self.assertEqual(state["locations"]["nav_b"]["objects"], ["mug"])
        self.assertEqual(state["locations"]["robot_hand"]["objects"], [])


if __name__ == "__main__":
    unittest.main()
