# ACT 模型仿真推理

将 LeRobot 训练的双臂 ACT 策略部署到 BlueThink MuJoCo 仿真环境中运行。

## 环境要求

`gs_playground` 环境，需包含 `lerobot`、`safetensors`、`motrixsim`。

## 运行

### 模式 1：仿真相机渲染

策略输入来自 MuJoCo 渲染的 3 个相机画面，物理由 MuJoCo 驱动。

```bash
cd FQPlanner_Mujoco3DGSNew

python teleop/act/sim_act_inference.py \
  --policy-path /path/to/checkpoint/pretrained_model \
  --device cuda
```

### 模式 2：真实数据集图像

策略输入来自 LeRobot 数据集中的真实视频帧（内存解码，无需写磁盘），物理仍由 MuJoCo 驱动。用于验证策略在真实图像下的表现，隔离图像域差异。

```bash
python teleop/act/sim_act_inference.py \
  --policy-path /path/to/checkpoint/pretrained_model \
  --data-path /path/to/lerobot_dataset \
  --episode 0 \
  --device cuda
```

日志中 `gt_err` 为策略输出与数据集 GT 动作的均方误差（deg），可直观判断策略质量。

## 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--policy-path` | (必填) | ACT 模型检查点路径 |
| `--device` | cuda | cuda / cpu |
| `--data-path` | "" | LeRobot 数据集根目录，设置后使用真实图像模式 |
| `--episode` | 0 | `--data-path` 模式下加载的 episode 索引 |
| `--no-viewer` | False | 无界面模式 |
| `--policy-fps` | 30 | 推理频率（应与训练数据 fps 一致） |
| `--camera-w` / `--camera-h` | 640 / 480 | 相机分辨率（需与训练一致） |
| `--physics-steps-per-step` | 10 | 每次推理后的物理步数 |
| `--init-hold-steps` | 500 | 初始姿态保持步数 |
| `--duration` | 0 | 最大运行秒数（<=0 为无限） |

## 相机映射

| 仿真相机 | 模型 key | 训练数据相机 |
|----------|----------|-------------|
| `base_cam` | `observation.images.top` | Orbbec Gemini 335L（顶视） |
| `left_ee_cam` | `observation.images.left_wrist` | RealSense D435i（左腕） |
| `right_ee_cam` | `observation.images.right_wrist` | RealSense D435i（右腕） |

## 关节顺序

前 7 个为左臂，后 7 个为右臂，与训练数据一致：

```
Left:  Shoulder_Pitch, Shoulder_Roll, Shoulder_Yaw, Elbow_Pitch, Wrist_Yaw, Wrist_Pitch, Wrist_Roll
Right: Shoulder_Pitch, Shoulder_Roll, Shoulder_Yaw, Elbow_Pitch, Wrist_Yaw, Wrist_Pitch, Wrist_Roll
```

## 已知问题与修复

### 反归一化 (unnormalize_outputs)

当前 LeRobot 版本的 `policy.unnormalize_outputs()` 为空操作，模型输出停留在归一化空间（值约 [-2, 2]）而非弧度。`sim_act_inference.py` 已自动从 checkpoint 的 safetensors 文件加载 `action.mean` / `action.std`，在 `step_policy()` 中手动做 `x = x * std + mean`。

### 离线验证脚本

`offline_validate_policy.py` 可离线评估策略在训练数据上的重建精度：

```bash
conda activate lerobot
python teleop/act/offline_validate_policy.py \
  --policy-path /path/to/checkpoint/pretrained_model \
  --data-path /path/to/lerobot_dataset \
  --episode 0 \
  --device cpu
```

输出包括逐关节误差统计、误差时序图，以及对比图片。模型在训练数据上的平均重建误差应 < 5 deg。

### 域差异 (Domain Gap)

仿真相机渲染（MuJoCo 默认）与真实相机画面存在光照、纹理、反光等差异，可能导致策略在仿真中表现下降。可通过 3DGS 渲染（本项目已支持）缩小视觉差距。
