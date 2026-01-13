# TestSo101 - 独立机械臂测试脚本

独立的 SO101 机械臂测试脚本，不依赖原 DoRobot 代码库。

## 目录结构

```
TestSo101/
├── read_joint.py          # 读取关节数据并实时显示
├── keyboard_control.py    # 键盘控制（带限位保护）
├── record_limits.py       # 记录关节限位范围
├── requirements.txt       # 依赖包
├── limits.json.example    # 限位文件示例
├── motors/                # 机械臂驱动模块（独立）
│   ├── motors_bus.py
│   ├── feetech/
│   └── utils/
└── README.md
```

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 记录关节限位（首次使用必须）
python record_limits.py
# 按 B 开始记录，手动移动机械臂，按 S 保存

# 3. 键盘控制（自动加载限位保护）
python keyboard_control.py

# 4. 读取关节数据
python read_joint.py
```

## 文件说明

### 1. record_limits.py - 记录关节限位

**首次使用必须先运行此脚本记录安全限位！**

```bash
python record_limits.py
```

使用步骤：
1. 运行脚本
2. 按 **B** 开始记录
3. 手动移动机械臂到各个安全位置
4. 按 **S** 保存限位到 `limits.json`
5. 按 **ESC** 退出

生成的 `limits.json` 文件示例：
```json
{
  "shoulder_pan": {"min": -90.0, "max": 90.0},
  "shoulder_lift": {"min": -45.0, "max": 90.0},
  "elbow_flex": {"min": -90.0, "max": 90.0},
  "wrist_flex": {"min": -90.0, "max": 90.0},
  "wrist_roll": {"min": -180.0, "max": 180.0},
  "gripper": {"min": 0.0, "max": 100.0}
}
```

### 2. keyboard_control.py - 键盘控制（带限位保护）

自动加载 `limits.json` 进行限位保护。

```bash
python keyboard_control.py
```

**安全功能：**
- 自动加载限位文件
- 超出限位时停止运动并显示警告
- 退出时自动禁用扭矩，机械臂可自由移动

控制按键：
| 按键 | 关节 | 功能 |
|------|------|------|
| q / w | shoulder_pan | 左/右 旋转 +/- 5° |
| a / s | shoulder_lift | 上/下 抬起 +/- 5° |
| z / x | elbow_flex | 前/后 弯曲 +/- 5° |
| e / r | wrist_flex | 上/下 弯曲 +/- 5° |
| d / f | wrist_roll | 左/右 旋转 +/- 5° |
| c / v | gripper | 开/关 夹爪 +/- 10 |
| 空格 | 全部 | 复位到零位 |
| ESC | - | 退出程序 |

### 3. read_joint.py
读取并实时显示机械臂关节数据。

```bash
python read_joint.py
```

功能：
- 实时读取 6 个关节的当前位置
- 以 10Hz 频率刷新显示
- 按 Ctrl+C 退出

## 前置条件

1. **校准文件必须存在**
   - 脚本会在当前目录的 `.calibration/` 下查找 `SO101-arm.json`
   - 如果没有，需要从原项目复制：
   ```bash
   mkdir -p .calibration/
   cp ../operating_platform/robot/components/arm_normal_so101_v1/.calibration/SO101-*.json .calibration/
   ```

2. **限位文件**
   - 首次使用必须运行 `record_limits.py` 创建 `limits.json`
   - 或者手动复制 `limits.json.example` 并修改限位值

3. **串口端口**
   - 默认: `/dev/ttyACM0`
   - 如需修改，编辑脚本中的 `PORT` 变量

## 独立运行

此目录已复制所有必要的 motors 模块，可以单独打包使用：
- 不依赖 DORA
- 不依赖原 DoRobot 代码库
- 只需要 requirements.txt 中的依赖

## 注意事项

- 这些脚本不能同时运行（会抢占串口资源）
- 确保机械臂已连接并通电
- 脚本会自动处理 Ctrl+C 退出时的资源清理
- **安全第一：首次使用务必记录限位！**
