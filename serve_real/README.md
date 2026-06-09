# serve_real/ — 真实机器人后端

`serve_real/` 只放真实机器人相关代码。上层仍然通过 `robot_api.client` 调用能力接口，`robot_api.runtime` 按配置决定是否把动作传递到这里。

## 目录结构

```text
serve_real/
├── config.yaml          # 真实硬件连接参数
├── bridge/              # robot_api.runtime 调用的真实硬件桥接
│   ├── arm.py
│   └── base.py
├── service/             # 开发板侧常驻服务
│   └── grasp_server.py
└── backend/
    └── base/            # 真实底盘驱动和测试脚本
```

## 配置

`robot_api/config.yaml` 只控制是否传递真实动作：

```yaml
backends:
  real:
    enabled: 1
    accept_action: 1
    required: 1
```

真实硬件连接参数放在 `serve_real/config.yaml`：

```yaml
real_arm:
  enabled: 1
  host: 10.11.32.17
  port: 9999
  timeout: 60
  command_byte: 0xAA
  fail_on_error: 1
```

`host` 只写开发板 IP，不要写成 `user@ip`。服务端需要接受 `0xAA` 并返回 `SUCCESS...` 或 `FAILED...`。

## 开发板侧抓取服务

启动：

```bash
python3 serve_real/service/grasp_server.py
```

默认执行的抓取脚本：

```bash
../../camera_10s.sh
```

该路径相对项目根目录解析。脚本成功应返回 `0`，失败应返回非零。

## 环境变量覆盖

- `REAL_ARM_ENABLED`
- `REAL_ARM_HOST`
- `REAL_ARM_PORT`
- `REAL_ARM_TIMEOUT`
- `REAL_ARM_COMMAND_BYTE`
- `REAL_ARM_FAIL_ON_ERROR`
- `REAL_BASE_ENABLED`
- `REAL_BASE_PORT`
- `REAL_BASE_SPEED_SCALE`
- `REAL_BASE_MAX_SPEED`
- `GRASP_SCRIPT_PATH`
