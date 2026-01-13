# SO101机械臂LLM控制集成指南

## 概述

本文档说明如何使用大语言模型(LLM)通过RoboOS系统控制SO101机械臂。

## 系统架构

```
RoboOS
├── TestSo101/              # 机械臂控制模块
│   ├── arm_controller.py   # 机械臂控制封装(新建)
│   ├── keyboard_control.py # 键盘控制示例
│   ├── motors/             # 驱动模块
│   └── limits.json         # 限位配置
└── slaver/
    ├── run.py              # Slave启动程序
    ├── config.yaml         # 配置文件
    └── demo_robot_local/
        └── skill.py        # MCP技能注册(已更新)
```

## 新增功能

### 1. 机械臂控制封装 (`arm_controller.py`)

提供了 `SO101ArmController` 类,包含以下功能:

- **单关节相对角度控制**: `move_joint(joint_name, angle)`
- **单关节绝对角度控制**: `move_joint_absolute(joint_name, angle)`
- **关节位置查询**: `get_joint_position(joint_name)`
- **所有关节位置查询**: `get_all_positions()`
- **复位到零位**: `reset_to_zero()`
- **限位保护**: 自动加载并检查限位配置

### 2. MCP工具注册 (已更新 `skill.py`)

新增以下MCP工具,LLM可以直接调用:

1. **`move_joint_relative`**: 相对角度控制关节
   - 参数: `joint_name` (关节名称), `angle` (相对角度)
   - 示例: `wrist_flex` +10度

2. **`move_joint_absolute`**: 绝对角度控制关节
   - 参数: `joint_name` (关节名称), `angle` (绝对角度)
   - 示例: 移动到45度

3. **`get_joint_position`**: 查询单个关节位置
   - 参数: `joint_name` (关节名称)
   - 返回: 当前角度

4. **`get_all_joint_positions`**: 查询所有关节位置
   - 返回: 所有关节当前角度

5. **`reset_arm_to_zero`**: 复位所有关节到零位
   - 无参数

## 支持的关节

| 关节名称 | 描述 | 角度范围 |
|---------|------|---------|
| `shoulder_pan` | 肩部旋转 | -90° ~ 90° |
| `shoulder_lift` | 肩部抬起 | -45° ~ 90° |
| `elbow_flex` | 肘部弯曲 | -90° ~ 90° |
| `wrist_flex` | 手腕弯曲 | -90° ~ 90° |
| `wrist_roll` | 手腕旋转 | -180° ~ 180° |
| `gripper` | 夹爪 | 0 ~ 100 (0=开, 100=闭) |

*注: 实际限位由 `limits.json` 文件配置决定*

## 启动流程

### 前置条件

1. **确保限位文件存在**
   ```bash
   cd TestSo101
   python record_limits.py  # 首次使用必须运行
   ```

2. **确保校准文件存在**
   ```bash
   # 校准文件应在 .calibration/SO101-arm.json
   # 如果不存在,需要从原项目复制
   mkdir -p .calibration/
   cp ../path/to/original/.calibration/SO101-*.json .calibration/
   ```

### 启动步骤

按照以下顺序在4个独立终端中启动系统:

#### 终端 1: 启动模型服务
```bash
conda activate RoboOS
bash Modeldeploy/start_server.sh
```

#### 终端 2: 启动 Master
```bash
conda activate RoboOS
python master/run.py
```

#### 终端 3: 启动 Slaver (机械臂控制)
```bash
conda activate RoboOS
python slaver/run.py
```
*此时会看到: "✓ SO101机械臂连接成功"*

#### 终端 4: 启动 Web UI
```bash
conda activate RoboOS
python deploy/run.py
```

访问: http://127.0.0.1:8888

## LLM控制示例

### 示例 1: 相对角度控制

**用户输入:**
```
wrist_flex角度+10度
```

**LLM调用:**
```python
move_joint_relative(joint_name="wrist_flex", angle=10.0)
```

**系统执行:**
- 读取当前手腕角度: 假设为 0°
- 计算目标角度: 0° + 10° = 10°
- 检查限位: 10° 在 [-90°, 90°] 范围内 ✓
- 发送控制命令
- 返回: "手腕弯曲(wrist_flex) 已调整 +10.0°, 当前角度: 10.00°"

### 示例 2: 绝对角度控制

**用户输入:**
```
把肩部旋转移动到45度
```

**LLM调用:**
```python
move_joint_absolute(joint_name="shoulder_pan", angle=45.0)
```

**系统执行:**
- 检查限位: 45° 在 [-90°, 90°] 范围内 ✓
- 直接移动到45°
- 返回: "肩部旋转(shoulder_pan) 已移动到 45.00°"

### 示例 3: 查询关节位置

**用户输入:**
```
查询当前所有关节的位置
```

**LLM调用:**
```python
get_all_joint_positions()
```

**返回:**
```json
{
  "shoulder_pan": {"angle": 0.0, "description": "肩部旋转"},
  "shoulder_lift": {"angle": 0.0, "description": "肩部抬起"},
  "elbow_flex": {"angle": 0.0, "description": "肘部弯曲"},
  "wrist_flex": {"angle": 10.0, "description": "手腕弯曲"},
  "wrist_roll": {"angle": 0.0, "description": "手腕旋转"},
  "gripper": {"angle": 0.0, "description": "夹爪"}
}
```

### 示例 4: 复位机械臂

**用户输入:**
```
复位机械臂
```

**LLM调用:**
```python
reset_arm_to_zero()
```

**系统执行:**
- 所有关节移动到零位
- 返回: "机械臂已复位到零位"

### 示例 5: 组合控制

**用户输入:**
```
先抬起肩膀30度,然后弯曲手腕15度,最后关闭夹爪
```

**LLM依次调用:**
```python
# 1. 抬起肩膀
move_joint_relative(joint_name="shoulder_lift", angle=30.0)
# → "肩部抬起(shoulder_lift) 已调整 +30.0°, 当前角度: 30.00°"

# 2. 弯曲手腕
move_joint_relative(joint_name="wrist_flex", angle=15.0)
# → "手腕弯曲(wrist_flex) 已调整 +15.0°, 当前角度: 15.00°"

# 3. 关闭夹爪
move_joint_absolute(joint_name="gripper", angle=80.0)
# → "夹爪(gripper) 已移动到 80.00°"
```

## LLM提示词建议

为了获得最佳效果,LLM应理解以下语义:

### 关节控制
- "把[关节]转动/移动/调整 X度" → `move_joint_relative`
- "把[关节]移动到X度" → `move_joint_absolute`
- "向上/向下/向左/向右移动[关节]" → `move_joint_relative` (带正负角度)

### 常用词汇映射
| 中文描述 | 关节名称 |
|---------|---------|
| 肩部旋转 / 底盘旋转 | shoulder_pan |
| 肩部抬起 / 大臂 | shoulder_lift |
| 肘部弯曲 / 小臂 | elbow_flex |
| 手腕弯曲 | wrist_flex |
| 手腕旋转 | wrist_roll |
| 夹爪 / 手爪 | gripper |

### 方向映射
- "向上/抬起/提起" → 正角度
- "向下/放下/降低" → 负角度
- "向左/左转" → 负角度 (shoulder_pan)
- "向右/右转" → 正角度 (shoulder_pan)
- "打开夹爪" → angle=0
- "关闭夹爪" → angle=100

## 故障排查

### 1. 机械臂连接失败

**症状:**
```
[skill.py] ✗ SO101机械臂连接失败
```

**解决方案:**
1. 检查串口: `ls /dev/ttyACM*`
2. 确认机械臂已通电
3. 检查串口权限: `sudo chmod 666 /dev/ttyACM0`

### 2. 限位文件未找到

**症状:**
```
⚠ 警告: 限位文件 limits.json 不存在
```

**解决方案:**
```bash
cd TestSo101
python record_limits.py
# 按 B 开始记录,手动移动机械臂,按 S 保存
```

### 3. 校准文件未找到

**症状:**
```
✗ 校准文件不存在: .calibration/SO101-arm.json
```

**解决方案:**
```bash
mkdir -p .calibration/
# 从原项目复制校准文件
cp ../original_project/.calibration/SO101-*.json .calibration/
```

### 4. MCP工具未注册

**症状:** Web界面中看不到机械臂控制工具

**解决方案:**
1. 检查 `slaver/run.py` 是否正在运行
2. 查看日志中的工具列表
3. 确认 `skill.py` 中的 `@mcp.tool()` 装饰器正确

## 安全注意事项

1. **首次使用必须设置限位**: 运行 `record_limits.py` 记录安全范围
2. **确保限位文件存在**: 系统会自动检查并警告
3. **监控日志输出**: 所有操作都会输出到 stderr
4. **自动断电保护**:
   - 正常退出程序时，机械臂会自动禁用扭矩，进入松弛状态
   - 按下 Ctrl+C 会触发清理函数，机械臂会立即断电
   - 收到 SIGTERM 信号时也会自动断电
5. **紧急停止**: Ctrl+C 会自动禁用扭矩,使机械臂松弛
6. **测试时使用小角度**: 首次测试建议使用 ±5° 以内的小角度

## 退出与断电

程序退出时会**自动执行以下清理操作**:

1. 调用 `arm_controller.disconnect()`
2. 禁用所有关节扭矩 (disable_torque)
3. 断开串口连接
4. 机械臂进入松弛状态，可以手动移动

**示例输出:**
```
[skill.py] 正在断开机械臂连接并禁用扭矩...
[skill.py] ✓ 机械臂已断电，可以自由移动
```

**无需手动操作**，程序会自动处理。就像 `keyboard_control.py` 一样安全。

## 配置文件

### `slaver/config.yaml`

```yaml
robot:
  call_type: local
  path: "demo_robot_local"  # 指向包含skill.py的目录
  name: demo_robot          # 机器人名称
```

### `TestSo101/limits.json`

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

## 扩展开发

### 添加新的关节控制功能

编辑 `TestSo101/arm_controller.py`,添加新方法:

```python
def your_custom_control(self, params):
    # 实现自定义控制逻辑
    pass
```

然后在 `slaver/demo_robot_local/skill.py` 中注册MCP工具:

```python
@mcp.tool()
async def your_tool_name(param: type) -> tuple[str, dict]:
    """工具描述"""
    result = arm_controller.your_custom_control(param)
    return result["message"], result
```

## 参考文档

- `TestSo101/README.md`: TestSo101模块说明
- `slaver/demo_robot_local/skill.py`: MCP工具实现
- `keyboard_control.py`: 键盘控制参考示例
