# RoboOS 模块化开发指南

## 概述

RoboOS 机器人系统采用模块化设计，将不同功能分散到独立的模块文件中，便于管理和扩展。

## 目录结构

```
slaver/demo_robot_local/
├── skill.py          # 统一入口，注册所有模块
├── base.py           # 底盘控制模块
├── arm.py            # 机械臂控制模块
├── example.py        # 示例模块（添加新功能的模板）
└── README_MODULES.md # 本文档
```

## 现有模块说明

### 1. base.py - 底盘控制模块

**功能：**
- `navigate_to_target(target)`: 导航到目标位置
- `move(direction, speed, duration)`: 按指定方向、速度和时间移动

**使用场景：**
- 机器人在场景中的导航
- 底盘的基本移动控制

### 2. arm.py - 机械臂控制模块

**功能：**
- `move_joint_relative(joint_name, angle)`: 相对角度移动关节
- `move_joint_absolute(joint_name, angle)`: 绝对角度移动关节
- `get_joint_position(joint_name)`: 获取单个关节位置
- `get_all_joint_positions()`: 获取所有关节位置
- `reset_arm_to_zero()`: 复位到零点

**使用场景：**
- 机械臂的关节控制
- 读取机械臂状态
- 机械臂复位

### 3. example.py - 示例模块

这是一个模板文件，展示如何创建新的功能模块。

## 如何添加新功能模块

### 步骤 1: 创建新模块文件

复制 `example.py` 并重命名，例如创建 `camera.py`：

```bash
cp example.py camera.py
```

### 步骤 2: 编辑模块内容

打开 `camera.py`，修改模块文档和工具函数：

```python
"""
相机控制模块 (Camera Control Module)

负责机器人的相机功能。

Functions:
    - take_photo: 拍照
    - get_camera_info: 获取相机信息
"""

import sys
from typing import Tuple, Dict


def register_tools(mcp):
    """注册相机相关的所有工具函数到 MCP 服务器"""

    @mcp.tool()
    async def take_photo(camera_id: int = 0) -> Tuple[str, Dict]:
        """Take a photo with the specified camera.

        Args:
            camera_id: Camera ID (default: 0)

        Returns:
            A tuple containing the result message and photo info.

        Examples:
            take_photo(camera_id=0)  # Take photo with camera 0
        """
        print(f"[camera.take_photo] Taking photo with camera {camera_id}", file=sys.stderr)

        result = f"Photo taken with camera {camera_id}"
        state_update = {
            "camera_id": camera_id,
            "photo_saved": True,
            "timestamp": "2024-01-01_12-00-00"
        }

        return result, state_update

    print("[camera.py] 相机控制模块已注册", file=sys.stderr)
```

### 步骤 3: 在 skill.py 中注册模块

编辑 `skill.py`，添加导入和注册：

```python
# 在导入部分添加
from camera import register_tools as register_camera_tools

# 在 register_all_modules() 函数中添加
def register_all_modules():
    # ... 现有模块 ...

    # 注册相机控制模块
    register_camera_tools(mcp)
```

### 步骤 4: 测试新模块

重启 slaver 服务，系统会自动加载新模块：

```bash
# 在终端中
conda activate RoboOS
python slaver/run.py
```

查看日志确认模块已加载：
```
[skill.py] 开始注册机器人技能模块...
[base.py] 底盘控制模块已注册
[arm.py] 机械臂控制模块已注册
[camera.py] 相机控制模块已注册
[skill.py] ✓ 所有模块注册完成
```

## 模块开发规范

### 1. 函数签名

所有工具函数必须：
- 使用 `@mcp.tool()` 装饰器
- 是 `async` 异步函数
- 返回 `Tuple[str, Dict]` 类型
- 包含完整的文档字符串

```python
@mcp.tool()
async def my_function(param1: str, param2: float = 10.0) -> Tuple[str, Dict]:
    """函数功能的简要描述.

    详细说明函数的功能、使用场景等。

    Args:
        param1: 参数1的说明
        param2: 参数2的说明（可选参数）

    Returns:
        A tuple containing the result message and updated robot state.

    Examples:
        my_function(param1="test", param2=5.0)
    """
    result = "操作结果"
    state_update = {"key": "value"}
    return result, state_update
```

### 2. 日志输出

使用 `sys.stderr` 输出日志，确保日志可见：

```python
print(f"[module_name.function_name] 日志信息", file=sys.stderr)
```

### 3. 错误处理

妥善处理错误，返回有用的错误信息：

```python
try:
    # 执行操作
    result = perform_operation()
    return result, {"success": True}
except Exception as e:
    error_msg = f"操作失败: {e}"
    print(f"[module_name] {error_msg}", file=sys.stderr)
    return error_msg, {"error": str(e), "success": False}
```

### 4. 状态更新

返回的状态字典应包含：
- `success`: 操作是否成功（布尔值）
- 相关的参数和结果数据
- 错误信息（如果失败）

## 常见使用场景

### 场景 1: 添加传感器模块

创建 `sensor.py`：

```python
"""传感器模块"""
from typing import Tuple, Dict
import sys

def register_tools(mcp):
    @mcp.tool()
    async def read_sensor(sensor_id: int) -> Tuple[str, Dict]:
        """Read sensor data."""
        # 实现传感器读取逻辑
        return f"Sensor {sensor_id} data: 25.5°C", {"temperature": 25.5}
```

### 场景 2: 添加语音模块

创建 `voice.py`：

```python
"""语音控制模块"""
from typing import Tuple, Dict
import sys

def register_tools(mcp):
    @mcp.tool()
    async def speak(text: str) -> Tuple[str, Dict]:
        """Text to speech."""
        # 实现语音播放逻辑
        return f"Speaking: {text}", {"text": text, "spoken": True}
```

### 场景 3: 添加抓取模块

创建 `gripper.py`：

```python
"""抓取控制模块"""
from typing import Tuple, Dict
import sys

def register_tools(mcp):
    @mcp.tool()
    async def grip_object(object_name: str) -> Tuple[str, Dict]:
        """Grip an object."""
        # 实现抓取逻辑
        return f"Gripped {object_name}", {"holding": object_name}
```

## 调试技巧

### 1. 查看注册的工具

启动服务后，可以在日志中看到所有注册的工具：

```
[skill.py] 开始注册机器人技能模块...
[base.py] 底盘控制模块已注册
[arm.py] 机械臂控制模块已注册
```

### 2. 测试单个工具

通过 Web UI 发送任务测试新工具是否正常工作。

### 3. 查看详细日志

检查 `slaver/.log/agent.log` 获取详细执行日志。

## 注意事项

1. **模块独立性**: 每个模块应该独立工作，避免强耦合
2. **全局变量**: 谨慎使用全局变量，如需要使用请在模块内部管理
3. **资源清理**: 如需初始化/清理资源，提供相应的函数并在 skill.py 中调用
4. **命名规范**: 函数名使用动词开头，描述清晰的英文命名
5. **文档完整**: 为每个函数提供完整的文档字符串

## 示例：完整的模块开发流程

假设要添加一个灯光控制模块：

1. **创建模块文件** `lighting.py`
2. **实现工具函数** (toggle_light, set_brightness, etc.)
3. **在 skill.py 注册**
4. **重启服务测试**
5. **通过 Web UI 验证功能**

## 进阶主题

### 1. 模块间通信

如果模块间需要通信，可以使用共享的状态管理器。

### 2. 异步操作

使用 `asyncio` 处理耗时的 I/O 操作。

### 3. 配置管理

为模块添加配置文件支持。

## 总结

模块化设计使得：
- ✅ 代码结构清晰
- ✅ 功能易于扩展
- ✅ 维护更加简单
- ✅ 团队协作方便

遵循本指南，你可以轻松添加新功能到 RoboOS 系统！
