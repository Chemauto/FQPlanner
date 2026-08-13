# Windows 作为临时大脑端的测试指南

本方案不改变 PBD 主机架构。Ubuntu 继续运行感知、建图、关系图和 HTTP 服务；Windows 只安装约 5 KB 的纯 Python 客户端。Windows 不需要 ROS2、CUDA、Docker、Rerun或大模型环境。

## 一、Ubuntu/PBD 主机

PBD 当前地址为 `10.11.32.63`，服务当前已监听 `0.0.0.0:8088`。每次联调前在 Ubuntu 终端确认：

```bash
hostname -I
cd /home/fq/BJHYZJ_FQ/与大脑交接
./server/start_pbd_brain_server.sh start
./server/start_pbd_brain_server.sh status
```

若只测试历史世界模型，`source_stale=true` 可以接受；若要测试真机实时更新，应先启动新的 PBD/G1 建图运行，并确认该字段恢复为 `false`。

## 二、把客户端复制到 Windows

需要复制的文件是：

```text
/home/fq/BJHYZJ_FQ/与大脑交接/dist/PBD_AG_大脑端轻量客户端_v0.1.0.zip
```

可以使用共享文件、U 盘、WinSCP，或在 Windows PowerShell 中使用系统自带的 `scp`：

```powershell
scp "fq@10.11.32.63:/home/fq/BJHYZJ_FQ/与大脑交接/dist/PBD_AG_大脑端轻量客户端_v0.1.0.zip" "$HOME\Downloads\"
```

SSH 会要求输入 Ubuntu 用户 `fq` 的密码；不要把密码写进脚本。

## 三、Windows 网络验收

Windows 必须连接与 PBD 主机相同的局域网。打开 PowerShell：

```powershell
ipconfig
Test-NetConnection 10.11.32.63 -Port 8088
Invoke-RestMethod http://10.11.32.63:8088/health | ConvertTo-Json -Depth 10
```

必须看到：

```text
TcpTestSucceeded : True
world_ready      : true
api_version      : v1
```

若端口失败，依次检查：Windows/PBD 是否同一 Wi-Fi、VPN 是否关闭、路由器是否启用了客户端隔离、Ubuntu 服务状态及 Ubuntu 防火墙。`ping` 被禁并不一定代表 TCP 不通，以 `Test-NetConnection` 为准。

## 四、一条命令完成安装和只读验收

在 Windows 上解压：

```powershell
cd "$HOME\Downloads"
Expand-Archive .\PBD_AG_大脑端轻量客户端_v0.1.0.zip .\PBD_AG_Client -Force
cd .\PBD_AG_Client
```

若 PowerShell 禁止执行本地脚本，只对当前窗口临时放行，然后运行验收：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\client\windows\acceptance.ps1 -Server http://10.11.32.63:8088
```

脚本会创建隔离的 `.venv_windows`、安装客户端、获取世界模型、地图和 RGB，并且**不会发送导航命令**。末尾出现 `PBD-AG Windows read-only acceptance: PASS` 即表示接入成功。

## 五、手动调用示例

无需激活环境，直接使用解压目录内的可执行文件：

```powershell
$PBD = "http://10.11.32.63:8088"
$Client = ".\.venv_windows\Scripts\pbd-ag-client.exe"

& $Client --server $PBD doctor
& $Client --server $PBD objects --class-name "table,chair,bottle,cola"
& $Client --server $PBD pose
& $Client --server $PBD map .\output\map
& $Client --server $PBD rgb .\output\rgb_latest.png
& $Client --server $PBD task --task-id fetch_cola_001 --semantic-target "cola bottle" --instruction "go to the pantry and fetch a cola"
```

也可以不安装客户端，直接调用 HTTP：

```powershell
Invoke-RestMethod "$PBD/v1/objects?class=table,chair,bottle"
Invoke-RestMethod "$PBD/v1/robot/pose"
Invoke-WebRequest "$PBD/v1/rgb/latest" -OutFile .\rgb_latest.png
```

## 六、导航接口测试

当前 `/health` 中的导航模式是 `record_only_no_motion`，因此即使 Windows POST `/nav`，也只记录命令而不会驱动机器人。建议先完成读取和任务上下文测试。

导航组接口接通、`navigation.mode` 显示为 `forward` 后，才进行实机目标测试：

```powershell
$Body = @{
    task_id = "fetch_cola_001"
    map_session_id = "从health或snapshot读取的当前值"
    frame_id = "map"
    x = 2.35
    y = -1.20
    target_yaw = 1.57
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "$PBD/nav" -ContentType "application/json" -Body $Body
Invoke-RestMethod "$PBD/v1/navigation/status" | ConvertTo-Json -Depth 10
```

首次实机测试必须在机器人旁保留急停人员，并先发送近距离、空旷区域内的单目标。
