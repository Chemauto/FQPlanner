# robot_api Contract

`robot_api` 是 Master、Slaver、Deploy、Nav2 访问机器人的唯一入口。上层只调用 `robot_api.client`，不直接依赖 MuJoCo、Isaac Sim、Gazebo 或真实机器人代码。

## 配置

后端开关在 [`config.yaml`](config.yaml) 中配置。

- `enabled`: 是否启用该后端。
- `provide_state`: 是否接收状态查询。
- `accept_action`: 是否接收动作指令。
- `required`: 该后端失败时是否让整体调用失败。

默认后端是 MuJoCo，对应启动入口：

```text
serve/main.py
```

当前 MuJoCo 后端实现位置：

```text
serve/service/server.py
serve/backend/mujoco_backend.py
```

## 公开接口

上层只使用以下能力接口：

```python
get_scene()
get_objects()
get_fixtures()
get_base_status()
get_arm_status()
grasp_object(object_name)
place_object(object_name, target)
navigate_to(target, yaw=None)
move_forward(duration=1.0, speed=0.5)
rotate(direction="left", duration=1.0, speed=0.5)
capture_image(context="", camera_name=None)
```

## HTTP 后端要求

MuJoCo、Isaac Sim、Gazebo 等仿真后端建议实现同一组 HTTP endpoint：

```text
GET  /scene
GET  /objects
GET  /fixtures
GET  /base_status
GET  /status
GET  /map_data
POST /grasp
POST /place
POST /nav
POST /move_duration
POST /screenshot
```

导航内部桥接还可以实现：

```text
GET  /scan
POST /cmd_vel
```

这两个接口主要给 ROS2 SLAM/Nav2 bridge 使用，不建议作为 LLM 公开工具接口。

真实机器人后端可以只实现当前硬件支持的动作。未支持的动作应被跳过或返回清晰错误。

真实硬件连接参数不放在 `robot_api/config.yaml`，而放在：

```text
serve_real/config.yaml
```

当前真实后端目录：

```text
serve_real/bridge/
serve_real/service/
serve_real/backend/
```
