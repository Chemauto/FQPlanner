# 场景配置目录 (Scene Configuration)

本目录包含RoboOS的场景定义和位置映射配置。

## 文件说明

### 1. profile.yaml
场景定义文件，包含所有场景位置、物体和容器的信息。

**结构示例：**
```yaml
scene:
  - name: bedroom          # 英文名称（作为数据库key）
    type: location         # 类型：location/table/container
    position: [4.0, 1.0, 0.0]  # [x, y, z] 坐标
    description: "卧室"     # 中文描述（用户输入的名称）
    contains:              # 可选：包含的物体列表
      - bed
      - table
```

### 2. LOCATION_MAP.py
中文名称到英文名称的映射表，用于导航时的名称转换。

**结构示例：**
```python
LOCATION_MAP = {
    "卧室": "bedroom",
    "客厅": "livingRoom",
}
```

## 工作原理

1. **Master 启动时**：
   - 读取 `profile.yaml`
   - 使用 `name` 字段（英文）作为 key，将场景数据存入 Redis
   - 例如：`bedroom` -> `{type: location, position: [4.0, 1.0, 0.0], description: "卧室"}`

2. **用户执行导航时**：
   - 输入："前往卧室"
   - Slaver 接收任务，调用 `navigate_to_target(target="卧室")`

3. **位置映射转换**：
   - `base.py` 从 `LOCATION_MAP.py` 导入映射表
   - 将 "卧室" 转换为 "bedroom"
   - 更新机器人状态：`position: "bedroom"`

4. **查询坐标时**：
   - 使用 "bedroom" 从 Redis 查找场景数据
   - 成功找到坐标：`(4.0, 1.0, 0.0)`

## 修改场景的步骤

**重要**：当添加、修改或删除场景时，必须同时修改这两个文件！

### 步骤 1：修改场景配置文件

编辑 `master/scene/profile.yaml`，添加新的场景定义：

```yaml
scene:
  - name: balcony          # 英文名称（作为Redis的key）
    type: location
    position: [5.0, 2.0, 0.0]
    description: "阳台"    # 中文描述
```

### 步骤 2：更新位置映射表

编辑 `master/scene/LOCATION_MAP.py`，在 `LOCATION_MAP` 字典中添加映射：

```python
LOCATION_MAP = {
    # ... 现有映射 ...
    "阳台": "balcony",     # 新增：中文描述 -> 英文名称
}
```

**关键点**：
- 键（中文）必须与 `profile.yaml` 中的 `description` 字段完全一致
- 值（英文）必须与 `profile.yaml` 中的 `name` 字段完全一致

### 步骤 3：重启服务

修改完成后，需要重启 Master 和 Slaver 使配置生效：

```bash
# 终端 2 - 重启 Master
# 按 Ctrl+C 停止，然后：
python master/run.py

# 终端 3 - 重启 Slaver
# 按 Ctrl+C 停止，然后：
python slaver/run.py
```

## 常见问题

### Q: 为什么显示 "Coordinates: Not found in scene"？

A: 通常是因为 `LOCATION_MAP` 中的映射与 `profile.yaml` 不一致：
- 检查中文名称是否与 `description` 完全一致（包括标点符号）
- 检查英文名称是否与 `name` 完全一致（区分大小写）
- 确认修改后已重启 Master 和 Slaver

### Q: 如何验证配置是否正确？

A: 查看日志文件：
```bash
tail -f master/.logs/master_agent.log  # 查看 Master 加载的场景
tail -f slaver/.log/agent.log          # 查看 Slaver 执行的导航
```

## 修改示例

### 示例1：添加新位置

在 `profile.yaml` 添加：
```yaml
- name: studyRoom
  type: location
  position: [3.0, 4.0, 0.0]
  description: "书房"
```

在 `LOCATION_MAP.py` 添加：
```python
"书房": "studyRoom",
```

### 示例2：修改现有位置

修改 `profile.yaml` 中的坐标：
```yaml
- name: bedroom
  type: location
  position: [5.0, 2.0, 0.0]  # 修改坐标
  description: "卧室"
```

`LOCATION_MAP.py` 无需修改（name 和 description 未变）。

### 示例3：删除位置

从 `profile.yaml` 删除：
```yaml
# - name: oldRoom  # 删除这一段
#   type: location
#   position: [0.0, 0.0, 0.0]
#   description: "旧房间"
```

从 `LOCATION_MAP.py` 删除：
```python
# "旧房间": "oldRoom",  # 删除这一行
```

## 快速检查清单

修改场景后，使用此清单确保所有步骤已完成：

- [ ] 已修改 `master/scene/profile.yaml` 中的场景定义
- [ ] 已更新 `master/scene/LOCATION_MAP.py` 中的映射
- [ ] 确认 name 字段（英文）与 LOCATION_MAP 的值一致
- [ ] 确认 description 字段（中文）与 LOCATION_MAP 的键一致
- [ ] 已重启 Master 服务
- [ ] 已重启 Slaver 服务
- [ ] 已测试导航功能并验证坐标显示正确

## 当前场景位置

| 中文名称 | 英文名称 | 坐标 | 类型 |
|---------|---------|------|------|
| 卧室 | bedroom | (4.0, 1.0, 0.0) | location |
| 客厅 | livingRoom | (2.0, 3.0, 0.0) | location |
| 入口 | entrance | (0.0, 0.0, 0.0) | location |
| 厨房桌子 | kitchenTable | (1.0, 2.0, 0.0) | table |
| 自定义桌子 | customTable | (2.0, 1.0, 0.0) | table |
| 服务桌 | servingTable | (3.0, 2.0, 0.0) | table |
| 篮子 | basket | (1.5, 1.5, 0.5) | container |
| 垃圾桶 | trashCan | (4.0, 3.0, 0.0) | container |

## 参考文档

- [完整开发指南](../../MODULE_DEVELOPMENT_GUIDE.md)
- [模块详细文档](../../slaver/demo_robot_local/README_MODULES.md)
