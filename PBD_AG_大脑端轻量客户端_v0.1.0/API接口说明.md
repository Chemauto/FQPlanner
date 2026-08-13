# PBD-AG—大脑 HTTP API v1

## 1. 约定

- PBD 服务地址：`http://10.11.32.63:8088`（当前 DHCP 地址，开机后以 `hostname -I` 复核）。
- 大脑主机：`10.11.32.178`。
- 坐标系：所有坐标均为 `map` 系，位置单位为米，偏航角单位为弧度，绕 `+Z` 轴逆时针为正。
- `map_session_id`：一次建图会话的唯一标识。大脑缓存的地图或目标如果与当前会话不一致，应重新拉取，不能跨会话直接复用坐标。
- `world_revision`：世界模型版本号。它变化时才需要重新解析完整快照；轻量变化可通过事件接口增量拉取。
- 物体的 `node_id`/`object_id` 是面向大脑的稳定 ID；不要使用内部 `source_node_id` 作为长期身份。

## 2. 读取接口

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/health` | 连通性、世界模型是否就绪、会话/版本、导航模式 |
| GET | `/v1/world/snapshot` | 一次获取地图元数据、机器人位姿、关系图、媒体 URL 和任务上下文 |
| GET | `/v1/world/events?after=17` | 从事件 17 后增量获取 add/update/move/reparent/remove |
| GET | `/v1/objects` | 获取所有语义物体 |
| GET | `/v1/objects?class=table,chair,bottle` | 按类别筛选物体 |
| GET | `/v1/robot/pose` | 获取 `map` 系机器人位姿及有效性信息 |
| GET | `/v1/map/metadata` | 获取 resolution、origin 和地图下载地址 |
| GET | `/v1/map/yaml` | 下载 ROS 兼容地图 YAML |
| GET | `/v1/map/pgm` | 下载占据栅格 PGM |
| GET | `/v1/rgb/latest` | 按需获取最近一张 RGB 图 |
| GET | `/v1/depth/latest` | 按需获取最近一张深度图；可能返回 503，深度为可选项 |
| GET | `/v1/task/context` | 获取当前大脑任务上下文 |
| GET | `/v1/navigation/status` | 查询当前和历史导航命令状态 |

占据地图遵循 ROS map_server 约定。像素到地图坐标必须同时使用 YAML 中的 `origin`、`resolution` 和图像纵轴翻转规则，不应假定图像左上角就是地图原点。

## 3. 大脑写入接口

### 3.1 设置任务上下文

`POST /v1/task/context`

```json
{
  "task_id": "fetch_cola_001",
  "instruction": "去茶水间取一瓶可乐",
  "semantic_target": "cola bottle",
  "target_classes": ["cola", "bottle", "table"],
  "priority": 80
}
```

该接口只改变感知/查询关注上下文，不直接产生运动。

### 3.2 下发导航目标

`POST /nav`

```json
{
  "task_id": "fetch_cola_001",
  "map_session_id": "g1_manual_20260803_120000",
  "frame_id": "map",
  "x": 2.35,
  "y": -1.20,
  "target_yaw": 1.57
}
```

服务端检查数值有限性、`frame_id` 和 `map_session_id`。到达判定由 PBD/导航侧完成。返回中的 `command_id` 用于状态查询。当前未配置导航组 HTTP 地址时，返回 `PENDING_NAV_ADAPTER`，命令只写入审计日志，**不会让机器人运动**。

### 3.3 导航结果

大脑通过 `GET /v1/navigation/status` 查询。导航适配器也可向 `POST /v1/navigation/result` 回写：

```json
{
  "command_id": "brain_nav_123456789abc",
  "status": "SUCCEEDED",
  "success": true,
  "pose": {"x": 2.31, "y": -1.18, "yaw": 1.55},
  "message": "goal reached"
}
```

建议状态枚举为 `ACCEPTED`、`RUNNING`、`SUCCEEDED`、`FAILED`、`CANCELED`。

## 4. 错误和安全规则

- `200`：读取成功或同步操作完成。
- `202`：导航请求被记录/接受，但不代表已到达。
- `400`：字段、坐标或地图会话错误。
- `503`：世界模型/图片尚未就绪。
- `502`：已配置的下游导航服务不可达或拒绝请求。
- 大脑仅在 `/health` 中 `world_ready=true`、机器人位姿有效、地图会话一致时计算和发送导航目标。
- `source_stale=true` 表示上游数据近期没有更新。复盘旧实验时这是正常的；真机在线导航时应停止发新目标并等待恢复。
- 局域网联调暂不启用 Token/TLS；服务不得暴露至公网。进入跨网段或生产真机阶段必须增加认证、TLS 和来源限制。
