# ACT 模型模拟推理

将 LeRobot 训练的双臂 ACT 策略部署到 BlueThink MuJoCo 仿真环境中运行。

## 环境要求

`gs_playground` 环境 + `lerobot`：

```bash
# 在 gs_playground/pyproject.toml 中已添加 lerobot 依赖
cd gs_playground && uv sync
```

## 运行

```bash
cd FQPlanner_Mujoco3DGSNew

python teleop/act/sim_act_inference.py \
  --policy-path /path/to/checkpoint/pretrained_model \
  --device cuda
```

## 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--policy-path` | (必填) | ACT 模型检查点路径 |
| `--device` | cuda | cuda / cpu |
| `--no-viewer` | False | 无界面模式 |
| `--policy-fps` | 30 | 推理频率 |
| `--camera-w` / `--camera-h` | 640 / 480 | 相机分辨率 |

## 相机映射

| 仿真相机 | 模型 key |
|----------|----------|
| `base_cam` | `observation.images.top` |
| `left_ee_cam` | `observation.images.left_wrist` |
| `right_ee_cam` | `observation.images.right_wrist` |

## 关节顺序

前 7 个为左臂，后 7 个为右臂，与训练数据一致：
- Shoulder_Pitch / Shoulder_Roll / Shoulder_Yaw / Elbow_Pitch / Wrist_Yaw / Wrist_Pitch / Wrist_Roll
