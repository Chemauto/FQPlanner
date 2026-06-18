# serve_3dgs — MotrixSim + 3DGS Backend

`serve_3dgs/` provides the same HTTP service contract used by the upper layers
(`master`, `slaver`, `agent`, `robot_api`) while loading a MotrixSim scene with
3D Gaussian rendering assets.

## Scene Assets

The default scene is fully local to this repository:

```text
assets/scene_3dgs/
├── config.json
└── nav_scene_1/
    ├── 3dgs/point_cloud.ply   # 3DGS 点云（从 HuggingFace 下载）
    ├── mjcf/scene.xml
    └── meshes/
```

`point_cloud.ply`（~234 MB）存放在 HuggingFace，需要手动下载：

```bash
# 使用 huggingface-cli 下载（推荐）
pip install huggingface_hub
huggingface-cli download ChemAuto/gs_playground point_cloud.ply \
  --local-dir assets/scene_3dgs/nav_scene_1/3dgs/

# 或者直接 wget
wget -O assets/scene_3dgs/nav_scene_1/3dgs/point_cloud.ply \
  https://huggingface.co/ChemAuto/gs_playground/resolve/main/point_cloud.ply
```

`assets/scene_3dgs/config.json` controls the active navigation scene. Replacing
the scene should normally mean changing this file and the files it references.

The robot model remains shared with the rest of the project:

```text
assets/xlerobot/xlerobot.xml
assets/xlerobot/*.stl
```

## Startup

From the repository root:

```bash
python serve_3dgs/main.py
python serve_3dgs/main.py --no-viewer
```

From this directory:

```bash
python main.py
python main.py --no-viewer
```

To use another local scene config:

```bash
python serve_3dgs/main.py --scene_config assets/scene_3dgs/config.json
```

## Runtime Path

```text
main.py
  -> backend.GSConfig
  -> backend.SimEnv
  -> service.server
  -> tools.move / tools.arm
```

`GSConfig` resolves scene files. `SimEnv` builds the MotrixSim scene by loading
the local navigation MJCF, attaching the local XLeRobot MJCF, and binding the
scene 3DGS PLY as a static background. `service/server.py` keeps the existing
HTTP API shape for upper-layer compatibility.
