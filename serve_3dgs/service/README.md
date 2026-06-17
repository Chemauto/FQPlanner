# service/ — HTTP API Layer

`service/` exposes the Flask API used by `robot_api` and the upper planning
layers. It does not own scene construction; scene loading and MotrixSim state
live in `serve_3dgs/backend/`.

```text
service/
└── server.py
```

## Responsibilities

- Define the HTTP endpoints used by `robot_api`.
- Queue commands so request threads do not step the simulator directly.
- Call `tools.move` and `tools.arm` for high-level base and arm actions.
- Render screenshots through the active `SimEnv`.

## Main Endpoints

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/status` | GET | Arm and gripper status |
| `/base_status` | GET | Base pose and velocity |
| `/objects` | GET | Scene object positions |
| `/scene` | GET | Aggregated scene state |
| `/nav` | POST | Navigate to `{x, y, target_yaw}` |
| `/cmd_vel` | POST | Apply base velocity `{vx, vy, vw}` |
| `/move_to` | POST | Move the virtual end effector |
| `/grasp` | POST | Grasp an object |
| `/place` | POST | Place an object |
| `/open_gripper` | POST | Open gripper |
| `/close_gripper` | POST | Close gripper |
| `/screenshot` | POST | Return a camera image as base64 |

Upper layers should continue to call through `robot_api`, not import this
package directly.
