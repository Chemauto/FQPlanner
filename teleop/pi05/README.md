# teleop/pi05 — PI0.5 仿真推理

PI0.5 策略在 MotrixSim（3DGS）中的推理脚本，用于 BlueThink 双臂机器人。

## 架构

```
┌──────────────┐   SSH 隧道    ┌─────────────────────┐
│  本地机器人    │  localhost:5005 →  GPU 服务器          │
│  serve_3dgs   │◄─────────────►│  pi05_server.py     │
│  (3DGS 仿真)  │   HTTP JSON   │  (PI0.5 模型推理)    │
└──────────────┘               └─────────────────────┘
```

PI0.5 模型（3.6B 参数，PaliGemma + Gemma action expert）需要大显存（≥16GB），
因此在 GPU 服务器上以独立 HTTP 服务运行，本地通过 SSH 隧道访问。

## 前置条件

| 组件 | 要求 |
|------|------|
| 本地机器人 | Python 3.10+, MotrixSim, lerobot, requests |
| GPU 服务器 | Python 3.12+, lerobot ≥0.5.1, transformers ≥5.4, peft, flask, PyTorch+CUDA |
| 模型文件 | PI0.5 base (`pi05_base/`), LoRA adapter (`49000/pretrained_model/`), PaliGemma tokenizer (`paligemma-3b-pt-224/`) |

## 1. 服务器：启动 pi05_server.py

在 GPU 服务器上：

```bash
# 安装依赖（首次）
pip install lerobot "transformers>=5.4.0,<5.6.0" peft flask safetensors huggingface_hub

# 启动推理服务
python services/pi05_server.py \
  --policy-path  /path/to/49000/pretrained_model \
  --base-model-path /path/to/pi05_base \
  --tokenizer-path /path/to/paligemma-3b-pt-224 \
  --port 5005 \
  --device cuda \
  --dtype float32
```

> **注意**：如果 lerobot 版本的 GR00T dataclass 与 Python 3.12 不兼容（`backbone_cfg` 报错），
> 需要 patch `lerobot/policies/groot/groot_n1.py`：给所有 `init=False` 的 field 加 `default=None`。
> 如果缺少 processor step（如 `relative_actions_processor`），确保 `pi05_policy.py` 的
> `ensure_legacy_pi05_processor_registry_aliases` 已运行（它会自动注册缺失的 pass-through step）。

验证：
```bash
curl http://localhost:5005/health
# {"policy_loaded":true,"status":"ok"}
```

## 2. 本地：建立 SSH 隧道

```bash
# 将本地 5005 端口转发到服务器的 5005
ssh -N -L 5005:localhost:5005 -p <SSH端口> root@<服务器IP>

# 后台运行（推荐 autossh）
autossh -M 0 -f -N -L 5005:localhost:5005 -p <SSH端口> root@<服务器IP>
```

验证隧道：
```bash
curl http://127.0.0.1:5005/health
```

## 3. 配置 robot_api/config.yaml

```yaml
policy_services:
  pi05:
    enabled: 1
    url: "http://127.0.0.1:5005"
    task: "pick up the object and place it"
```

> **不要硬编码服务器 IP**——隧道把 `127.0.0.1:5005` 映射到服务器，换机器只需改隧道。

## 4. 运行

### 方式 A：serve_3dgs + 抓取指令（通过 Master/Slaver 或 curl）

```bash
# 起仿真后端
cd serve_3dgs && python main.py

# 发送抓取指令（task 用训练时的场景描述）
curl -X POST http://127.0.0.1:5002/grasp \
  -H 'Content-Type: application/json' \
  -d '{"obj_name":"apple","mode":"pi05","task":"pick up the apple"}'
```

日志输出示例：
```
[pi05_grasp] Async HTTP worker started -> http://127.0.0.1:5005 (non-blocking)
[pi05_grasp] step=10/1000 inferences=5 action[:3]=[...] grip=[...]
```

### 方式 B：sim_pi05_inference.py 直接跑（独立脚本）

**本地模型推理**（需要本机有 GPU + 模型文件）：
```bash
python teleop/pi05/sim_pi05_inference.py \
  --policy-path /data/FQIntern/49000/pretrained_model \
  --base-model-path /data/FQIntern/pi05_base \
  --tokenizer-path /data/FQIntern/paligemma-3b-pt-224 \
  --task "pick up the object" \
  --device cuda
```

**数据集回放推理**（不需要本地模型，通过远程服务器）：
```bash
python teleop/pi05/sim_pi05_inference.py \
  --data-path /data/FQIntern/dataset \
  --episode 0 \
  --pi05-url http://127.0.0.1:5005 \
  --scene robot_only
```

## 5. 端口/隧道速查

| 地址 | 说明 |
|------|------|
| 服务器 `localhost:5005` | pi05_server.py 监听 |
| 机器人 `127.0.0.1:5005` | SSH 隧道 → 服务器 5005 |
| 机器人 `127.0.0.1:5002` | serve_3dgs 仿真后端 |
| 机器人 `127.0.0.1:5001` | serve (MuJoCo) 仿真后端 |
| `robot_api/config.yaml` | `policy_services.pi05.url` 指向隧道地址 |

## 常见问题

| 问题 | 排查 |
|------|------|
| `Connection refused` on 5005 | 隧道没建好，或服务器 pi05_server 没跑 |
| `500 Internal Server Error` | 服务器日志看 traceback；常见：dtype 不匹配（用 `--dtype float32`）、processor step 缺失 |
| `missing policy image keys` | 客户端发的图片 key 要是 `top`/`left_wrist`/`right_wrist` |
| `backbone_cfg` dataclass 报错 | lerobot 0.5.x + Python 3.12 不兼容，patch groot_n1.py |
| 机器人不动 | 检查 `inferences` 计数是否在涨；`inferences=0` 说明服务器连不通 |
| 推理太慢 | 服务器显存不足时会 offload 到 CPU；换 fp16/bf16 减少显存 |
