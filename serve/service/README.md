# service/ — MuJoCo HTTP 服务层

`service/` 只保留 MuJoCo 后端的 HTTP 服务端。上层客户端入口在 `robot_api.client`，不要再从这里提供或引用 client 封装。

```
service/
└── server.py    # Flask 服务端（定义 MuJoCo 后端 API）
```

## server.py — API 服务端

Flask 应用，端口 5001。接收 HTTP 请求，调用 `serve/tools/` 和 `serve/backend/mujoco_backend.py`，返回 JSON。

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

## 边界

- `service/server.py` 负责 HTTP endpoint 和命令队列。
- `serve/tools/` 负责 MuJoCo 中的动作实现。
- `serve/backend/` 负责 MuJoCo 模型、数据和仿真步进。
- `robot_api/` 负责上层统一接口、后端选择和 sim/real 编排。
