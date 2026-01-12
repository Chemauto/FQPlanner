# Robot Skills Guide

## 可用技能

### 1. navigate_to_target - 导航到目标位置

**参数：** `target` (str) - 目标位置名称（如 "kitchenTable", "bedroom"）

**示例：**
```python
"Navigate to bedroom"  # 导航到卧室
"去厨房"                # 导航到厨房
```

---

### 2. move - 控制机器人移动

**参数：**
- `direction` (float): 移动方向，0-360度
  - 0° = 前方, 90° = 左侧, 180° = 后方, 270° = 右侧
- `speed` (float): 速度，单位：米/秒 (m/s)
- `duration` (float): 持续时间，单位：秒 (s)

**坐标系：**
```
      0° (前)
        ↑
270° ← ● → 90°
(右)     (左)
        ↓
     180° (后)
```

**示例：**
```python
"Move forward at 1 m/s for 2 seconds"     # 向前移动2米
"Move left at 0.5 m/s for 3 seconds"      # 向左移动1.5米
"Move backward at 0.8 m/s for 1.5 seconds" # 向后移动1.2米
"Move at 45 degrees at 0.5 m/s for 2 s"   # 45度方向移动1米
```

---

## 组合任务

```python
# 导航后移动
tasks = [
    "Navigate to bedroom",
    "Move forward at 1 m/s for 2 seconds"
]

# 多段移动
tasks = [
    "Move forward at 1 m/s for 2 seconds",
    "Move left at 0.5 m/s for 3 seconds",
    "Move backward at 0.8 m/s for 1.5 seconds"
]
```

---

## 测试

```bash
# 测试移动功能
python test_move.py

# 测试导航功能
python test_navigation.py
```

---

## 查看日志

```bash
# Slaver 日志
tail -f slaver/.log/agent.log

# Master 日志
tail -f master/.logs/master_agent.log
```

在运行 `slaver/run.py` 的终端可以看到调试输出。
