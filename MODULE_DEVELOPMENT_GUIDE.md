# RoboOS 模块开发与使用指南

## 目录

- [系统概述](#系统概述)
- [快速开始](#快速开始)
- [现有模块介绍](#现有模块介绍)
- [添加新模块](#添加新模块)
- [模块开发规范](#模块开发规范)
- [测试工具](#测试工具)
- [常见问题](#常见问题)

---

## 系统概述

RoboOS 采用模块化设计，将机器人功能分散到独立模块中：

```
slaver/demo_robot_local/
├── skill.py          # 统一入口，注册所有模块
├── base.py           # 底盘控制（导航、移动）
├── arm.py            # 机械臂控制（关节运动）
├── example.py        # 示例模板（开发参考）
└── README_MODULES.md # 详细开发文档
```

---

## 快速开始

### 1. 启动系统

```bash
# 终端 1: 启动模型服务
conda activate RoboOS
bash Modeldeploy/start_server.sh

# 终端 2: 启动 Master
conda activate RoboOS
python master/run.py

# 终端 3: 启动 Slaver
conda activate RoboOS
python slaver/run.py

# 终端 4: 启动 Web UI
conda activate RoboOS
python deploy/run.py
```

### 2. 发送任务

通过 Web UI 发送自然语言任务，例如：
- "前往卧室"
- "导航到客厅"
- "机械臂复位"

### 3. 查看日志

```bash
# Master 日志
tail -f master/.logs/master_agent.log

# Slaver 日志
tail -f slaver/.log/agent.log
```

---

## 现有模块介绍

### 1. base.py - 底盘控制模块

**功能：**
- `navigate_to_target(target)` - 导航到指定位置
- `move(direction, speed, duration)` - 按参数移动底盘

**使用示例：**
```
"前往卧室"           # 导航到卧室
"到客厅"             # 导航到客厅
"向前移动1米"        # 控制底盘移动
```

**场景位置：**
- entrance (入口): (0.0, 0.0, 0.0)
- livingRoom (客厅): (2.0, 3.0, 0.0)
- bedroom (卧室): (4.0, 1.0, 0.0)
- kitchenTable (厨房桌子): (1.0, 2.0, 0.0)
- customTable (自定义桌子): (2.0, 1.0, 0.0)
- servingTable (服务桌): (3.0, 2.0, 0.0)
- trashCan (垃圾桶): (4.0, 3.0, 0.0)

### 2. arm.py - 机械臂控制模块

**功能：**
- `move_joint_relative(joint_name, angle)` - 相对角度移动关节
- `move_joint_absolute(joint_name, angle)` - 绝对角度移动关节
- `get_joint_position(joint_name)` - 获取单个关节位置
- `get_all_joint_positions()` - 获取所有关节位置
- `reset_arm_to_zero()` - 复位到零点

**关节列表：**
- `shoulder_pan`: 肩部旋转
- `shoulder_lift`: 肩部升降
- `elbow_flex`: 肘部弯曲
- `wrist_flex`: 腕部弯曲
- `wrist_roll`: 腕部旋转
- `gripper`: 夹爪 (0-100, 0=张开, 100=闭合)

**使用示例：**
```
"机械臂复位"                    # 复位所有关节
"腕部向上转动10度"              # 相对移动
"夹爪闭合到50"                  # 绝对位置
```

### 3. example.py - 示例模板

这是一个完整的示例模块，展示如何创建新功能。包含两个示例函数：
- `example_tool(param1, param2)` - 基本工具函数示例
- `another_example(device_id)` - 设备操作示例

---

## 添加新模块

### 方法一：复制模板（推荐）

```bash
# 1. 复制示例文件
cd slaver/demo_robot_local
cp example.py camera.py

# 2. 编辑 camera.py，修改函数实现
# 3. 在 skill.py 中导入并注册
```

### 方法二：从头创建

#### 步骤 1: 创建模块文件

创建 `slaver/demo_robot_local/my_module.py`:

```python
"""我的自定义模块"""

import sys
from typing import Tuple, Dict


def register_tools(mcp):
    """注册工具函数到 MCP 服务器"""

    @mcp.tool()
    async def my_tool(param: str) -> Tuple[str, Dict]:
        """我的工具函数描述.

        Args:
            param: 参数说明

        Returns:
            结果和状态更新
        """
        # 实现功能逻辑
        result = f"执行结果: {param}"
        state = {"success": True, "param": param}

        print(f"[my_tool] {result}", file=sys.stderr)
        return result, state

    print("[my_module.py] 模块已注册", file=sys.stderr)
```

#### 步骤 2: 在 skill.py 中注册

编辑 `skill.py`:

```python
# 在导入部分添加
from my_module import register_tools as register_my_module_tools

# 在 register_all_modules() 函数中添加
def register_all_modules():
    # ... 现有模块 ...
    register_my_module_tools(mcp)
```

#### 步骤 3: 测试

重启 Slaver 服务：

```bash
# 按 Ctrl+C 停止当前的 slaver
# 然后重新启动
python slaver/run.py
```

查看日志确认模块已加载：
```
[skill.py] 开始注册机器人技能模块...
[base.py] 底盘控制模块已注册
[arm.py] 机械臂控制模块已注册
[my_module.py] 模块已注册  ← 新模块
[skill.py] ✓ 所有模块注册完成
```

---

## 模块开发规范

### 1. 函数签名

所有工具函数必须：

```python
@mcp.tool()
async def function_name(param1: type, param2: type = default) -> Tuple[str, Dict]:
    """函数文档字符串.

    详细说明...
    """
    result = "操作结果"
    state_update = {"key": "value"}
    return result, state_update
```

**要求：**
- ✅ 使用 `@mcp.tool()` 装饰器
- ✅ 是 `async` 异步函数
- ✅ 返回 `Tuple[str, Dict]`
- ✅ 包含完整文档字符串

### 2. 日志输出

使用 `sys.stderr` 输出日志：

```python
print(f"[module_name.function_name] 日志信息", file=sys.stderr)
```

### 3. 错误处理

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
- `success`: 布尔值，表示操作是否成功
- 相关参数和结果数据
- 错误信息（如果失败）

---

## 测试工具

### 使用统一测试脚本

我们提供了一个统一的测试脚本 `test_robot.py`，可以测试所有模块：

```bash
python test_robot.py
```

**功能：**
1. 选择测试模块（底盘/机械臂/全部）
2. 选择测试模式（所有案例/特定案例/自定义）
3. 自动发送任务并显示结果
4. 实时查看机器人状态

**示例输出：**
```
============================================================
🤖 RoboOS 机器人功能测试
============================================================

🔍 检查Master服务...
✅ Master服务正在运行

请选择测试模块:
  1. 底盘控制模块 (base)
  2. 机械臂控制模块 (arm)
  3. 测试所有模块
请输入选择 (1/2/3):

选择测试模式:
  1. 运行所有测试
  2. 选择特定测试
  3. 自定义任务
请输入选择 (1/2/3):
```

### 通过 Web UI 测试

访问 `http://localhost:7860`，在 Web UI 中输入自然语言任务。

### 手动 API 测试

```python
import requests

response = requests.post(
    "http://localhost:5000/publish_task",
    json={"task": "前往卧室", "refresh": False}
)
print(response.json())
```

---

## 常见问题

### Q1: 添加新模块后没有生效？

**解决方法：**
1. 确认在 `skill.py` 中导入了模块
2. 确认调用了 `register_tools(mcp)`
3. 重启 Slaver 服务
4. 查看启动日志确认模块已注册

### Q2: 工具函数没有被调用？

**检查方法：**
1. 查看日志确认函数已注册
2. 在 Web UI 中使用更明确的任务描述
3. 检查函数的文档字符串是否清晰

### Q3: 如何调试模块？

**调试步骤：**
1. 在函数中添加 `print()` 输出到 `sys.stderr`
2. 查看 Slaver 日志：`tail -f slaver/.log/agent.log`
3. 使用测试脚本单独测试功能

### Q4: 模块之间如何通信？

**推荐方法：**
1. 使用 Redis (collaborator) 共享状态
2. 通过 master/slaver 的状态管理机制
3. 避免直接模块间调用，保持独立性

### Q5: 如何添加配置参数？

**方法：**
```python
# 在模块文件顶部
import yaml

def load_config():
    with open('config.yaml', 'r') as f:
        return yaml.safe_load(f)

config = load_config()
```

---

## 示例：完整模块开发流程

假设要添加一个相机控制模块：

### 1. 创建模块

```python
# camera.py
"""相机控制模块"""

import sys
from typing import Tuple, Dict


def register_tools(mcp):
    @mcp.tool()
    async def take_photo(camera_id: int = 0) -> Tuple[str, Dict]:
        """拍照.

        Args:
            camera_id: 相机ID (默认0)

        Returns:
            拍照结果和文件信息
        """
        print(f"[camera.take_photo] Camera {camera_id}", file=sys.stderr)

        # 实际的拍照逻辑
        result = f"已使用相机{camera_id}拍照"
        state = {
            "camera_id": camera_id,
            "photo_saved": True,
            "success": True
        }

        return result, state

    print("[camera.py] 相机模块已注册", file=sys.stderr)
```

### 2. 注册到 skill.py

```python
from camera import register_tools as register_camera_tools

def register_all_modules():
    register_base_tools(mcp)
    register_arm_tools(mcp)
    register_camera_tools(mcp)  # 新增
```

### 3. 测试

通过 Web UI 或测试脚本发送：
```
"使用相机0拍照"
```

### 4. 查看日志

```bash
tail -f slaver/.log/agent.log
```

应该看到：
```
[camera.take_photo] Camera 0
```

---

## 进阶主题

### 1. 异步操作

使用 `asyncio` 处理耗时操作：

```python
import asyncio

@mcp.tool()
async def long_operation(duration: int) -> Tuple[str, Dict]:
    """长时间操作示例"""
    await asyncio.sleep(duration)
    return f"完成，耗时{duration}秒", {"success": True}
```

### 2. 文件操作

```python
import os
from datetime import datetime

@mcp.tool()
async def save_data(data: str) -> Tuple[str, Dict]:
    """保存数据到文件"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"data_{timestamp}.txt"

    with open(filename, 'w') as f:
        f.write(data)

    return f"数据已保存到 {filename}", {"filename": filename}
```

### 3. 设备通信

```python
import serial

@mcp.tool()
async def send_command(command: str) -> Tuple[str, Dict]:
    """向设备发送命令"""
    with serial.Serial('/dev/ttyUSB0', 9600) as ser:
        ser.write(command.encode())
        response = ser.read(100)

    return response.decode(), {"command": command}
```

---

## 总结

RoboOS 模块化系统的优势：

- ✅ **结构清晰** - 功能分离，易于理解
- ✅ **易于扩展** - 添加新功能只需创建新模块
- ✅ **维护简单** - 每个模块独立管理
- ✅ **团队友好** - 多人并行开发
- ✅ **测试方便** - 模块独立测试

遵循本指南，你可以轻松开发和集成新功能到 RoboOS 系统！

---

## 参考资料

- 详细开发文档: `slaver/demo_robot_local/README_MODULES.md`
- 测试脚本: `test_robot.py`
- 示例模块: `slaver/demo_robot_local/example.py`
- 系统配置: `master/config.yaml`, `slaver/config.yaml`
