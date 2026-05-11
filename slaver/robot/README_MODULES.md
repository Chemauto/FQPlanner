# 模块使用与开发指南

## 目录结构

```
slaver/robot/
├── skill.py              # 统一入口
├── skill_reference.py    # 远程模式参考实现
├── module/               # 功能模块
│   ├── base.py           # 底盘控制（模拟导航）
│   └── example.py        # 示例模板
```

---

## 现有模块

### 1. base.py - 底盘控制模块

**功能:**
- `navigate_to_target(target)` - 导航到目标位置
- `move(direction, speed, duration)` - 参数化移动

**指令示例:**
```
"前往卧室" / "到客厅" / "导航到入口"
"向前移动1米" / "向右移动2秒"
```

### 2. example.py - 示例模板

用于参考开发新模块。

---

## 添加新模块

### 1. 创建模块文件

```bash
cd slaver/robot/module
cp example.py my_module.py
```

### 2. 编辑模块

```python
import sys

def register_tools(mcp):
    @mcp.tool()
    async def my_function(param: str) -> str:
        """函数功能说明"""
        return f"执行完成: {param}"
```

### 3. 注册到 skill.py

```python
from module.my_module import register_tools as register_my_module_tools

# 在 register_all_modules() 中添加:
register_my_module_tools(mcp)
```

### 4. 重启 Slaver

```bash
python slaver/run.py
```

---

## 模块快速参考

| 模块 | 功能 | 主要指令 |
|------|------|---------|
| base.py | 模拟底盘导航 | "前往卧室" |
