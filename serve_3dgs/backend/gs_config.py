"""3DGS asset path configuration."""

from pathlib import Path
from typing import Dict, Optional

FQPLANNER_ROOT = Path("/home/fangqi/WorkXCJ/FQPlanner_Mujoco3DGSNew")


class GSConfig:
    """Manages 3DGS asset paths for MotrixSim backend."""

    def __init__(self, assets_dir: Optional[str] = None, scene: str = "tabletop"):
        self.scene = scene
        self._assets_dir = Path(assets_dir) if assets_dir else None

        if scene == "tabletop":
            self.mjcf_path = str(FQPLANNER_ROOT / "assets" / "scene_3dgs" / "scene.xml")
            self._background_ply = None
        elif scene == "kitchen":
            self.mjcf_path = str(FQPLANNER_ROOT / "assets" / "scene" / "scene.xml")
            self._background_ply = None
        elif scene == "xlerobot":
            self.mjcf_path = str(FQPLANNER_ROOT / "assets" / "xlerobot" / "xlerobot.xml")
            self._background_ply = None
        elif scene == "franka":
            self._assets_dir = Path(assets_dir) if assets_dir else Path("/home/fangqi/WorkXCJ/gs_playground/demo/live_demo/assets")
            self.mjcf_path = str(self._assets_dir / "models" / "robots" / "manipulation" / "franka_emika_panda_robotiq" / "xmls" / "table30_04_hang_toothbrush_cup.xml")
            self._background_ply = str(self._assets_dir / "models" / "robots" / "manipulation" / "franka_emika_panda_robotiq" / "3dgs" / "background_085.ply")
        else:
            self.mjcf_path = scene
            self._background_ply = None

    @property
    def scene_xml(self) -> str:
        return self.mjcf_path

    @property
    def body_gaussians(self) -> Dict[str, str]:
        if self.scene == "franka" and self._assets_dir:
            task_dir = self._assets_dir / "models" / "tasks" / "table30" / "_04_hang_toothbrush_cup"
            robot_3dgs = self._assets_dir / "models" / "robots" / "manipulation" / "franka_emika_panda_robotiq" / "3dgs"
            d: Dict[str, str] = {}
            for i in range(1, 8):
                d[f"link{i}"] = (robot_3dgs / "franka" / f"link{i}.ply").as_posix()
            for name in ("robotiq_base", "left_driver", "left_coupler", "left_spring_link", "left_follower",
                          "right_driver", "right_coupler", "right_spring_link", "right_follower"):
                d[name] = (robot_3dgs / "robotiq" / f"{name}.ply").as_posix()
            task_3dgs = task_dir / "3dgs"
            d["toothbrush_cup"] = (task_3dgs / "toothbrush_cup.ply").as_posix()
            d["rack"] = (task_3dgs / "rack.ply").as_posix()
            return d
        return {}

    @property
    def background_ply(self) -> Optional[str]:
        return self._background_ply
