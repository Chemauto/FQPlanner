# service/ — HTTP API 服务

提供 HTTP API 接口，是 slaver 和仿真后端之间的桥梁。

```
service/
├── server.py    # Flask 服务端（定义所有 API 接口）
└── client.py    # HTTP 客户端（slaver 调用的封装层）
```

## server.py — API 服务端

Flask 应用，端口 5001。接收 HTTP 请求，调用 `tools/` 和 `mujoco_backend.py`，返回 JSON。

**状态查询：**

| 接口 | 方法 | 说明 |
|------|------|------|
| `/status` | GET | 机械臂末端和夹爪状态 |
| `/base_status` | GET | 底盘位置和朝向 |
| `/objects` | GET | 所有物体位置和抓取状态 |
| `/fixtures` | GET | 厨房固定家具（台面、水槽、炉灶等） |
| `/scene` | GET | 完整场景（聚合 objects + fixtures + robot） |
| `/scene_state` | GET | 场景状态记忆 |
| `/map_data` | GET | 占据栅格地图（用于 nav2 导航） |

**机器人控制：**

| 接口 | 方法 | 说明 |
|------|------|------|
| `/nav` | POST | 导航到目标位置 `{x, y, target_yaw}` |
| `/cmd_vel` | POST | 发送底盘速度 `{vx, vy, vw}` |
| `/nav_path` | POST | 路径跟随 `{path, w}` |
| `/move_to` | POST | 移动末端到目标 `{target}` |
| `/grasp` | POST | 抓取物体 `{obj_name}` |
| `/place` | POST | 放置物体 `{obj_name, target}` |
| `/open_gripper` | POST | 打开夹爪 |
| `/close_gripper` | POST | 关闭夹爪 |

**其他：**

| 接口 | 方法 | 说明 |
|------|------|------|
| `/screenshot` | POST | 相机截图（返回 base64） |
| `/record/start` | POST | 开始录制 |
| `/record/stop` | POST | 停止录制并保存视频 |

## client.py — HTTP 客户端

用 urllib 封装的 API 客户端，slaver 通过它调 server.py 的接口。

**主要函数：**

| 函数 | 对应接口 |
|------|---------|
| `navigate(x, y, yaw)` | POST `/nav` |
| `get_base_status()` | GET `/base_status` |
| `grasp_object(name)` | POST `/grasp` |
| `place_object(name, pos)` | POST `/place` |
| `capture_screenshot(cam)` | POST `/screenshot` |
| `get_scene()` | GET `/scene` |
| `get_objects()` | GET `/objects` |

**slaver 引用：**
- `slaver/robot/module/base.py` → `navigate`, `get_base_status`
- `slaver/robot/module/grasp.py` → `grasp_object`
- `slaver/robot/module/place.py` → `place_object`, `get_object_pos`
- `slaver/robot/module/camera.py` → `capture_screenshot`
- `slaver/agents/slaver_agent.py` → `get_scene`
