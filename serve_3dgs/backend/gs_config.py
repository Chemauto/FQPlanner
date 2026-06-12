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
