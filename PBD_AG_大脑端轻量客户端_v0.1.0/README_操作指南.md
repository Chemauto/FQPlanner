# PBD-AG 与大脑双主机接入操作指南

## 1. 已交付结果

本目录提供“PBD 主机运行重服务、大脑 Mac 仅安装轻量客户端”的双主机方案。大模型、检测/分割模型、CUDA、ROS2、Rerun 和 PBD-AG 环境全部留在 PBD 主机；Mac 端只通过 HTTP 拉取结构化世界模型并回传任务/导航目标，因此不需要复制模型、不需要 Docker，也不会与大脑现有 Python/Redis 环境冲突。

已完成本机端到端验证的能力包括：

- 占据地图 YAML/PGM、地图元数据与地图会话版本；
- `map` 系机器人位姿；
- 粗粒度和细粒度语义物体、中心、包围盒、父子关系和跨帧稳定 ID；
- RGB 按需下载、深度可选下载；
- 世界模型增量事件轮询；
- 大脑任务上下文写入；
- 导航命令校验、状态记录及可选下游 HTTP 转发。

当前地址：

- PBD 主机：`10.11.32.63/24`；
- 大脑 Mac：`10.11.32.178`；
- PBD API：`http://10.11.32.63:8088`。

两端地址在同一 `/24` 网段，但最终连通性必须以 Mac 侧 `curl` 验收为准。PBD 主机重连 Wi-Fi 后可能由 DHCP 获得新地址，正式联调建议在路由器上为 PBD 主机设置 DHCP 静态租约。

## 2. PBD 主机操作

### 2.1 先启动正常的 PBD/G1 感知建图

按原有方式启动 G1 实机建图，使 `/tmp/g1_dream_control/current_run.json` 指向当前运行目录。本接口会自动跟随当前运行，无需大脑知道实验目录。

### 2.2 启动 HTTP 服务

在 PBD Ubuntu 主机终端执行：

```bash
cd /home/fq/BJHYZJ_FQ/与大脑交接
./server/start_pbd_brain_server.sh start
./server/start_pbd_brain_server.sh status
```

正常输出应包含 `world_ready: true` 和：

```text
navigation.mode: record_only_no_motion
```

查看日志或停止服务：

```bash
tail -f /home/fq/BJHYZJ_FQ/与大脑交接/runtime/pbd_brain_server.log
cd /home/fq/BJHYZJ_FQ/与大脑交接
./server/start_pbd_brain_server.sh stop
```

如果当前 IP 变化，执行：

```bash
hostname -I
```

并把新的 Wi-Fi IPv4 地址告知大脑端。

### 2.3 接入真实导航服务

现在默认是安全的“只记录、不驱动”模式。导航组提供可接受同一 JSON 的 HTTP 服务地址后，在 PBD 主机执行：

```bash
cd /home/fq/BJHYZJ_FQ/与大脑交接
./server/start_pbd_brain_server.sh stop
export PBD_NAVIGATION_URL='http://导航服务IP:端口'
export PBD_NAVIGATION_PATH='/nav'
./server/start_pbd_brain_server.sh start
./server/start_pbd_brain_server.sh status
```

只有 `navigation.mode` 变成 `forward` 后，大脑的 `/nav` 才会被转发给真实导航模块。若导航组只有 ROS2 action/topic、没有 HTTP 接口，需要再增加一个位于 PBD 主机的 ROS2-to-HTTP 小适配器；大脑 Mac 仍无需安装 ROS2。

## 3. 大脑 Mac 操作

### 3.1 首次网络验收

在大脑 Mac 终端执行：

```bash
ping -c 4 10.11.32.63
nc -vz 10.11.32.63 8088
curl --fail --show-error http://10.11.32.63:8088/health
```

`ping` 可能被防火墙屏蔽，但 `nc` 和 `curl` 必须成功。若失败：

1. 确认两台主机连的是同一个 Wi-Fi/SSID，而不只是地址看起来相似；
2. 关闭 VPN 后复测；
3. 检查 Wi-Fi 是否启用了 AP/client isolation；
4. 在 Ubuntu 上确认 `ss -lnt | grep ':8088'` 显示 `0.0.0.0:8088`；
5. 若 Ubuntu 启用了 UFW，由管理员仅对局域网开放：`sudo ufw allow from 10.11.32.0/24 to any port 8088 proto tcp`。

### 3.2 安装轻量客户端

把 `dist/pbd_ag_client-0.1.0-py3-none-any.whl` 复制到 Mac，然后执行：

```bash
python3.10 -m venv ~/pbd_ag_env
source ~/pbd_ag_env/bin/activate
python -m pip install ./pbd_ag_client-0.1.0-py3-none-any.whl
export PBD_AG_SERVER='http://10.11.32.63:8088'
pbd-ag-client --server "$PBD_AG_SERVER" doctor
```

该 wheel 是纯 Python、与 arm64/x86 无关，无第三方运行依赖，不修改大脑原有 conda/Redis 环境。如果大脑希望使用已有 conda，也可以直接在独立 conda 环境中安装。

### 3.3 常用命令

```bash
# 查询桌子、椅子和瓶子
pbd-ag-client --server "$PBD_AG_SERVER" objects --class-name table,chair,bottle

# 查询机器人位姿
pbd-ag-client --server "$PBD_AG_SERVER" pose

# 下载最新地图和 RGB
pbd-ag-client --server "$PBD_AG_SERVER" map ./pbd_map
pbd-ag-client --server "$PBD_AG_SERVER" rgb ./rgb_latest.png

# 传入语义任务上下文
pbd-ag-client --server "$PBD_AG_SERVER" task \
  --task-id fetch_cola_001 \
  --semantic-target 'cola bottle' \
  --instruction '去茶水间取一瓶可乐'

# 导航接口启用后，在 map 系发送目标
pbd-ag-client --server "$PBD_AG_SERVER" nav 2.35 -1.20 1.57 \
  --task-id fetch_cola_001

pbd-ag-client --server "$PBD_AG_SERVER" nav-status
```

Python 调用见 `client/examples/brain_integration_example.py`，增量轮询见 `client/examples/brain_polling_loop.py`。

### 3.4 只读自动验收

验收脚本不会发送导航命令：

```bash
source ~/pbd_ag_env/bin/activate
python /path/to/smoke_test.py --server http://10.11.32.63:8088
```

## 4. 推荐的大脑工作流

1. 每秒调用 `/health`；检测到新的 `map_session_id` 时清空旧地图坐标缓存。
2. 以 1–2 Hz 读取 `/v1/robot/pose`，以 0.5–1 Hz 或按 `world_revision` 读取世界模型。
3. 首次或版本切换时拉 `/v1/world/snapshot`；之后用 `/v1/world/events?after=...` 获取增量变化。
4. 需要视觉核验时才拉 `/v1/rgb/latest`，不要持续推流。
5. 任务开始时 POST `/v1/task/context`，使 PBD 感知层知道语义目标。
6. 大脑在占据地图中计算工作点，确认 `map_session_id`、位姿有效性及安全性后 POST `/nav`。
7. 轮询 `/v1/navigation/status`，等待 PBD/导航侧给出最终到达状态；大脑不直接拥有底盘速度控制权。

## 5. 尚需导航组确认的唯一接口信息

世界模型和大脑端接口已经可以独立联调。要实际驱动机器人，还需导航组给出：

- 导航 HTTP 根地址和端口；若没有 HTTP，则给出 ROS2 action/topic 名称和消息类型；
- 接受目标后的返回格式，以及运行中/成功/失败/取消状态来源；
- 是否支持取消当前目标；
- 最终位置和航向到达阈值；
- 目标不可达、碰撞风险或地图过期时的错误码。

在这些信息确认前保持 `record_only_no_motion` 是正确且安全的，不影响地图、关系图、位姿、RGB 与任务上下文的联调。

更完整的字段和示例见 [API接口说明.md](./API接口说明.md)。
