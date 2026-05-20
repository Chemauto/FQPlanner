# 模块使用与开发指南

## 目录结构

```
slaver/robot/
├── skill.py              # 统一入口（注册所有模块）
├── skill_remote.py       # 远程模式参考实现
└── module/
    ├── base.py           # 底盘控制（导航、移动）
    ├── grasp.py          # 抓取物体
    └── example.py        # 示例模板
```

---

## 现有模块

### 1. base.py - 底盘控制模块

**功能:**
- `navigate_to_target(target)` - 导航到目标位置，返回位置名和坐标
- `move(direction, speed, duration)` - 参数化移动（方向、速度、时长）

**指令示例:**
```
"前往卧室" / "到客厅" / "导航到厨房桌子"
"向前移动1米" / "向右移动2秒"
```

**场景状态:** 更新 robot.position 和 robot.coordinates

### 2. grasp.py - 抓取模块

**功能:**
- `grasp_object(object_name)` - 模拟抓取物体（80% 成功率）

**指令示例:**
```
"抓取苹果" / "拿起桌上的水果"
```

**场景状态:** 成功时从 contains 移除物体，更新 robot.holding


### 3. example.py - 示例模板

用于参考开发新模块。

---

## 工具返回格式

工具可返回两种格式：

**纯字符串：**
```python
return "执行成功"
```

**带状态更新的元组：**
```python
return "执行成功", {"position": "bedroom", "coordinates": [0.0, 0.8, 0.0]}
```

第二种格式会自动更新 Redis 中的 robot 状态。

---

## 添加新模块

### 1. 创建模块文件

```bash
cd slaver/robot/module
cp example.py my_module.py
```

### 2. 编辑模块

```python
import asyncio
import random

def register_tools(mcp):
    @mcp.tool()
    async def my_function(param: str = None) -> str:
        """函数功能说明"""
        await asyncio.sleep(1)  # 模拟执行耗时
        if random.random() < 0.8:
            return f"执行成功: {param}"
        else:
            return f"执行失败: {param}"
```

### 3. 注册到 skill.py

```python
from module.my_module import register_tools as register_my_module_tools

def register_all_modules(mcp):
    # ... existing modules ...
    register_my_module_tools(mcp)
```

### 4. 重启 Slaver

```bash
python slaver/run.py
```

---

## 模块快速参考

| 模块 | 功能 | 主要指令 | 场景影响 |
|------|------|---------|---------|
| base.py | 底盘导航 | "前往卧室" | 更新 robot position/coordinates |
| grasp.py | 抓取物体 | "抓取苹果" | 移除 contains，更新 holding |
