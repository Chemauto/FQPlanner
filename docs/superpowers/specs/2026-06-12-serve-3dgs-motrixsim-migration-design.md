# serve_3dgs MotrixSim + 3DGS Migration Design

**Date:** 2026-06-12
**Status:** Approved
**Scope:** Replace serve_3dgs MuJoCo/DISCOVERSE backends with MotrixSim + 3DGS rendering

## Background

FQPlanner's `serve_3dgs/` currently supports two backends:
- `backend/` — Standard MuJoCo (native rendering)
- `discoverse_backend/` — DISCOVERSE simulator with 3DGS rendering

Neither provides the high-throughput batch 3DGS rendering needed for visual RL training. The gs_playground project demonstrates a MotrixSim + gaussian_renderer + gsplat pipeline that achieves up to 10^4 FPS at 640x480.

## Decision

- **Delete** `serve_3dgs/backend/` (MuJoCo) and `serve_3dgs/discoverse_backend/` (DISCOVERSE)
- **Create** new `serve_3dgs/backend/` with MotrixSim + 3DGS as the sole backend
- **Robot model:** Franka Panda + Robotiq (from gs_playground assets)
- **3DGS assets:** Reuse gs_playground's Franka `.ply` files
- **Purpose:** Replace `serve/` as the primary simulation backend for FQPlanner

## Architecture

### Directory Structure

```
serve_3dgs/
├── main.py                    # Single MotrixSim backend entry point
├── backend/                   # New: MotrixSim + 3DGS (replaces old MuJoCo backend)
│   ├── __init__.py
│   ├── sim_env.py             # MotrixSim SceneModel/SceneData + MtxBatchSplatRenderer
│   └── gs_config.py           # 3DGS asset path configuration (Franka Panda .ply mapping)
├── service/
│   └── server.py              # Flask API with command queue, adapted for MotrixSim
├── tools/
│   ├── arm.py                 # Arm control via MotrixSim dof_pos / forward_kinematic / step
│   └── move.py                # Base control via MotrixSim floating base
├── scene/
│   └── (no scene_generator)   # Reuse gs_playground Franka MJCF directly
└── ...
```

### Data Flow

```
main.py
  → SimEnv(model_xml, gs_cfg)          # MotrixSim + 3DGS init
  → SimServer(env, port=5002)          # Flask HTTP API
  → Command loop:
      process_commands()               # arm.grasp / arm.move_to / move.nav
      apply_base_velocity()            # cmd_vel → floating base dof_vel
      env.step(n)                       # MotrixSim physics
      env.forward_kinematic()           # Update link world poses
      [optional] RenderApp viewer      # 3DGS texture display
```

## Component Details

### 1. backend/sim_env.py — Core MotrixSim Environment

Encapsulates MotrixSim `SceneModel` + `SceneData` + 3DGS renderers.

```python
class SimEnv:
    def __init__(self, model_xml: str, gs_cfg: GSConfig):
        world = mx.msd.from_file(model_xml)
        self.model: mx.SceneModel = world.build()
        self.data: mx.SceneData = mx.SceneData(self.model)

        self.gs_renderer = MtxBatchSplatRenderer(
            BatchSplatConfig(body_gaussians=gs_cfg.body_gaussians, ...),
            self.model
        )
        self.bg_renderer = MtxBatchSplatRenderer(
            BatchSplatConfig(background_ply=gs_cfg.background_ply, ...),
            self.model
        )

        self.data.reset(self.model)
        self._grasped_object = None
        self.bg_imgs = None

    def step(self, n: int = 1) -> None
    def forward_kinematic(self) -> None
    def get_link_poses(self) -> np.ndarray       # (num_links, 7) [x,y,z,i,j,k,w]
    def render_frame(self, cam_id, width, height) -> np.ndarray  # (H,W,3) uint8 RGB
    def get_body_xpos(self, body_name) -> np.ndarray
    def get_camera_pose(self, cam_id) -> Tuple[pos, quat_xyzw, fovy]
```

Key interface: exposes `model` and `data` for tools layer direct access (same pattern as serve/ exposing `mj_model`/`mj_data`).

### 2. backend/gs_config.py — 3DGS Asset Configuration

Points to gs_playground's Franka Panda assets by default.

```python
class GSConfig:
    def __init__(self, assets_dir: str):
        self.assets_dir = Path(assets_dir)
        self.robot_dir = self.assets_dir / "models/robots/manipulation/franka_emika_panda_robotiq"
        self.task_dir = self.assets_dir / "models/tasks/table30/_04_hang_toothbrush_cup"

    @property
    def body_gaussians(self) -> Dict[str, str]:
        # Maps MotrixSim link names to .ply files
        return {
            "link1": ".../3dgs/franka/link1.ply", ..., "link7": "...",
            "robotiq_base": "...", "left_driver": "...", ...,
            "toothbrush_cup": "...", "rack": "...",
        }

    @property
    def background_ply(self) -> str:
        return ".../3dgs/background_085.ply"

    def scene_xml(self, scene_name: str) -> str:
        return (self.robot_dir / "xmls" / "table30_04_hang_toothbrush_cup.xml").as_posix()
```

### 3. tools/arm.py — Arm Control

MuJoCo API → MotrixSim API mapping:

| MuJoCo | MotrixSim |
|--------|-----------|
| `data.qpos[jnt_adr]` | `env.data.dof_pos[dof_idx]` |
| `mj_forward(model, data)` | `mx.forward_kinematic(env.model, env.data)` |
| `mj_step(model, data)` | `mx.step(env.model, env.data)` |
| `data.body(name).xpos` | `env.get_body_xpos(name)` via link_names |
| `model.body(name).jntadr` | `env.model.link_names.index(name)` |

```python
class ArmController:
    def __init__(self, env: SimEnv)
    def get_arm_info(self) -> dict           # ee_pos, gripper, joint_positions
    def move_arm(self, target_pos, steps) -> None   # Virtual EE positioning
    def grasp(self, object_name) -> None    # approach → close gripper → lift
    def place(self, target_pos) -> None     # move → open gripper → retreat
```

Joint indexing: MotrixSim uses `link_names` list (not `model.jnt(name).qposadr`). Floating base DOFs are handled via `FloatingBase` API, not as regular joints.

### 4. tools/move.py — Base Control

Franka Panda is fixed-base. Base control uses MotrixSim floating base API directly.

```python
class MoveController:
    def __init__(self, env: SimEnv)
    def get_base_info(self) -> dict          # pos, yaw, velocities
    def set_base_velocity(self, vx, vy, wz) -> None   # Direct floating base vel
    def nav(self, target_x, target_y, ...) -> bool     # PD navigation
    def stop_base(self) -> None
```

Key difference from MuJoCo version: no wheel actuator `ctrl[0/1]`. Direct `FloatingBase.set_dof_vel()`. When XLeRobot differential drive is needed later, switch to actuator ctrl.

### 5. service/server.py — HTTP API

Preserves command queue architecture. Key changes:

| Endpoint | Change |
|----------|--------|
| `POST /screenshot` | `env.render_frame(cam_id, w, h)` instead of MuJoCo renderer |
| `GET /camera/latest` | Same 3DGS rendering |
| `POST /grasp` / `/place` | Calls `self.arm.grasp()` / `self.arm.place()` |
| `POST /nav` | Calls `self.move.nav()` |
| `POST /cmd_vel` | Calls `self.move.set_base_velocity()` |
| `GET /status` | Calls `self.arm.get_arm_info()` |
| `GET /base_status` | Calls `self.move.get_base_info()` |
| `GET /state_qpos` | Reads `env.data.dof_pos` |
| `GET /map_data` | **Removed** (MotrixSim lacks MuJoCo geom raycast) |
| `GET /scan` | **Removed** (depends on map_data) |

Main loop:
```python
while True:
    process_commands()      # Dequeue and execute
    apply_base_velocity()   # cmd_vel expiry check
    env.step(n)              # MotrixSim physics
```

### 6. main.py — Entry Point

```python
def main():
    gs_cfg = GSConfig(args.gs_assets)
    env = SimEnv(gs_cfg.scene_xml(args.scene), gs_cfg)
    server = SimServer(env, port=args.port)
    server_thread = Thread(target=server.run, daemon=True)
    server_thread.start()

    if not args.no_viewer:
        with RenderApp() as render:
            render.launch(env.model)
            while not render.is_closed:
                server.tick()
                env.forward_kinematic()
                render.sync(env.data)
    else:
        while True:
            server.tick()
```

No `--backend` selection. Single MotrixSim backend.

## Scene Model

Reuse gs_playground's Franka Panda tabletop scene:

```
gs_playground/demo/live_demo/assets/
├── models/robots/manipulation/franka_emika_panda_robotiq/
│   ├── xmls/table30_04_hang_toothbrush_cup.xml    # Main MJCF
│   ├── 3dgs/franka/link{1-7}.ply                  # Franka link 3DGS
│   ├── 3dgs/robotiq/*.ply                         # Robotiq gripper 3DGS
│   └── 3dgs/background_085.ply                     # Background 3DGS
└── models/tasks/table30/_04_hang_toothbrush_cup/
    ├── 3dgs/toothbrush_cup.ply                     # Object 3DGS
    └── 3dgs/rack.ply                               # Object 3DGS
```

Loaded via `mx.msd.from_file()`. Custom scenes can be composed with `world.attach()`.

## Dependencies

**Add:**
```
motrixsim_core>=0.7.1       # MotrixSim physics engine (from Motphys PyPI)
torch>=2.7.0+cu128          # PyTorch + CUDA 12.8
gaussian_renderer>=0.2.0     # Batch 3DGS rendering
gsplat>=1.5.3                # CUDA 3DGS rasterization kernels
scipy>=1.14
```

**Remove:**
```
mujoco                       # Replaced by MotrixSim
discoverse                   # Removed backend
```

**Keep:**
```
flask>=3.0, flask-cors>=6.0, rich>=14.0, numpy>=2.0, pyyaml>=6.0
```

## Risks and Mitigations

1. **Joint indexing mismatch:** MotrixSim link/dof layout differs from MuJoCo. Mitigation: build explicit name→index mapping from `model.link_names` at init.
2. **Missing MuJoCo-specific features:** `map_data`, `scan` (geom raycast) unavailable. Mitigation: mark as removed; reimplement via 3DGS depth if needed.
3. **3DGS asset availability:** Only Franka Panda assets available initially. Mitigation: GSConfig is abstract; XLeRobot assets can be plugged in later via GS-Real2Sim pipeline.
4. **CUDA toolkit dependency:** gsplat requires CUDA toolkit. Mitigation: documented in setup (user already has CUDA 12.4 installed).
