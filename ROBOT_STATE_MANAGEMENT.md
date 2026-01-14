# 机器人位置状态管理

## 概述

为了追踪机器人在场景中的实时位置，系统实现了位置状态管理功能。机器人的状态包括当前位置名称和具体坐标信息。

## 状态字段

机器人在Redis中的状态存储在key `robot` 下，包含以下字段：

```json
{
  "position": "bedroom",           // 当前位置名称（英文，对应场景定义的name字段）
  "coordinates": [4.0, 1.0, 0.0],  // 当前坐标 [x, y, z]
  "holding": null,                 // 当前持有的物体
  "status": "idle"                 // 机器人状态
}
```

## 工作流程

### 1. 初始化

**文件**: `slaver/run.py:216-224`

Slaver启动时，机器人状态初始化为：
- `position`: "entrance" (入口)
- `coordinates`: [0.0, 0.0, 0.0]

```python
self.collaborator.record_environment(
    "robot", json.dumps({
        "position": "entrance",
        "coordinates": [0.0, 0.0, 0.0],
        "holding": None,
        "status": "idle"
    })
)
```

### 2. 导航更新

**文件**: `slaver/demo_robot_local/base.py:28-77`

当执行`navigate_to_target`导航操作时：
1. 将中文位置名映射为英文名称
2. 从硬编码的坐标表中查找目标位置坐标
3. 返回状态更新：`{"position": "bedroom", "coordinates": [4.0, 1.0, 0.0]}`
4. Agent接收状态更新并写入Redis

**坐标定义** (base.py:61-70):
```python
location_coordinates = {
    "entrance": [0.0, 0.0, 0.0],
    "livingRoom": [2.0, 3.0, 0.0],
    "bedroom": [4.0, 1.0, 0.0],
    "kitchenTable": [1.0, 2.0, 0.0],
    "customTable": [2.0, 1.0, 0.0],
    "servingTable": [3.0, 2.0, 0.0],
    "basket": [1.5, 1.5, 0.5],
    "trashCan": [4.0, 3.0, 0.0]
}
```

### 3. 状态更新处理

**文件**: `slaver/agents/slaver_agent.py:158-250`

Agent的`_execute_tool_call`方法：
1. 解析MCP工具返回的结果
2. 如果返回格式为JSON数组 `["result_message", {"state": "updates"}]`，提取状态更新
3. 调用`_update_robot_state`方法将更新写入Redis

**注意**: 当前FastMCP返回的是序列化后的JSON字符串，Agent会尝试解析tuple格式。

### 4. 位置信息查询

**文件**: `slaver/agents/slaver_agent.py:252-310`

`_get_current_position_info`方法优先级：
1. **优先**从`robot.coordinates`读取坐标（由导航操作设置）
2. **回退**从场景数据`{position_name}`读取坐标
3. 格式化返回：`"Location: bedroom (卧室)\nCoordinates: (4.0, 1.0, 0.0)"`

## 使用示例

### 场景1: 导航到卧室

用户输入: "前往卧室"

1. Agent调用 `navigate_to_target(target="卧室")`
2. base.py映射为 `"bedroom"`，查找坐标 `[4.0, 1.0, 0.0]`
3. 返回状态更新：`{"position": "bedroom", "coordinates": [4.0, 1.0, 0.0]}`
4. Agent更新Redis中的robot状态
5. 下次查询时显示：
   ```
   Location: bedroom (卧室)
   Coordinates: (4.0, 1.0, 0.0)
   ```

### 场景2: 其他操作不影响坐标

用户输入: "机械臂复位"

1. Agent调用机械臂相关工具
2. 工具返回的状态更新不包含`position`或`coordinates`
3. `robot.coordinates`保持不变
4. 机器人仍记录在之前导航到的位置坐标

## 设计考虑

1. **分离关注点**:
   - `position`: 位置名称（用于场景语义）
   - `coordinates`: 精确坐标（用于位置追踪）

2. **非破坏性更新**:
   - 只有导航类操作会更新`coordinates`
   - 其他操作（如机械臂控制）不影响位置状态

3. **容错机制**:
   - 如果`robot.coordinates`不存在，回退到从场景数据读取
   - 确保系统始终能显示位置信息

## 未来改进

1. **动态读取坐标**: 从`profile.yaml`动态读取坐标，而不是硬编码
2. **move指令支持**: `move`指令也能根据移动距离/方向更新坐标
3. **多机器人支持**: 每个机器人有独立的状态key（如`robot:{robot_name}`）

## 相关文件

| 文件 | 作用 |
|------|------|
| `slaver/run.py` | 初始化机器人状态 |
| `slaver/demo_robot_local/base.py` | 导航工具，返回坐标更新 |
| `slaver/agents/slaver_agent.py` | 状态更新处理和位置查询 |
| `master/scene/profile.yaml` | 场景定义（坐标数据源） |
| `master/scene/LOCATION_MAP.py` | 中文名称→英文名称映射 |
