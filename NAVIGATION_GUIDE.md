# 麦轮底盘导航功能使用说明

## 新增功能：navigate_to_location

现在 `real_base.py` 支持基于场景配置文件的导航功能！

### 功能说明

通过读取 `/home/dora/RoboOs/RoboOS/master/scene/profile.yaml` 中的位置配置，机器人可以导航到场景中的任何位置。

### 坐标系统

- **x轴**: 左右方向（右为正）
- **y轴**: 前后方向（前为正）
- **z轴**: 垂直方向（通常为0）

### 导航参数

- **速度**: 固定为 0.2 m/s
- **移动方式**: 先沿 x 轴移动（左右），再沿 y 轴移动（前后）
- **当前位置**: 假设为入口 [0.0, 0.0, 0.0]

### 使用示例

#### 示例 1: 导航到卧室

卧室位置: [4.0, 1.0, 0.0]

```
用户说: "我想去卧室"
LLM调用: navigate_to_location(target="卧室")

执行过程:
1. 向右移动 4.0 米，用时 20 秒（4.0 / 0.2 = 20）
2. 向前移动 1.0 米，用时 5 秒（1.0 / 0.2 = 5）
总用时: 25 秒
```

#### 示例 2: 导航到客厅

客厅位置: [2.0, 3.0, 0.0]

```
用户说: "去客厅"
LLM调用: navigate_to_location(target="客厅")

执行过程:
1. 向右移动 2.0 米，用时 10 秒
2. 向前移动 3.0 米，用时 15 秒
总用时: 25 秒
```

### 支持的位置

| 中文名称 | 英文名称 | 坐标 [x, y, z] | 说明 |
|---------|---------|---------------|------|
| 卧室 | bedroom | [4.0, 1.0, 0.0] | 向右4米，向前1米 |
| 客厅 | livingRoom | [2.0, 3.0, 0.0] | 向右2米，向前3米 |
| 入口 | entrance | [0.0, 0.0, 0.0] | 原点 |
| 厨房桌子 | kitchenTable | [1.0, 2.0, 0.0] | 向右1米，向前2米 |
| 自定义桌子 | customTable | [2.0, 1.0, 0.0] | 向右2米，向前1米 |
| 服务桌 | servingTable | [3.0, 2.0, 0.0] | 向右3米，向前2米 |
| 篮子 | basket | [1.5, 1.5, 0.5] | 向右1.5米，向前1.5米 |
| 垃圾桶 | trashCan | [4.0, 3.0, 0.0] | 向右4米，向前3米 |

### LLM 调用示例

```python
# 中文
navigate_to_location(target="卧室")
navigate_to_location(target="客厅")
navigate_to_location(target="厨房桌子")

# 英文
navigate_to_location(target="bedroom")
navigate_to_location(target="livingRoom")
navigate_to_location(target="kitchenTable")
```

### 工作流程

1. **读取配置**: 从 `profile.yaml` 加载所有位置
2. **映射名称**: 将中文/英文名称统一映射
3. **计算距离**: 计算从当前位置到目标位置的 dx, dy
4. **规划路径**: 分解为 x 轴移动和 y 轴移动
5. **执行移动**: 通过 Socket 发送指令到开发板
6. **返回结果**: 返回成功状态和坐标信息

### 实现细节

#### 函数签名

```python
async def navigate_to_location(target: str) -> Tuple[str, Dict]:
    """导航到目标位置"""
```

#### 辅助函数

- `load_location_config()`: 加载位置配置
- `get_location_coordinates(target)`: 获取目标位置坐标

#### 配置文件格式

```yaml
scene:
  - name: bedroom
    type: location
    position: [4.0, 1.0, 0.0]
    description: "卧室"
```

### 测试

```python
# 测试位置加载
from real_base import load_location_config, get_location_coordinates

# 加载所有位置
locations = load_location_config()
print(f"已加载 {len(locations)} 个位置")

# 获取卧室坐标
success, info = get_location_coordinates("卧室")
if success:
    print(f"卧室坐标: {info['position']}")
    print(f"描述: {info['description']}")
```

### 注意事项

1. **假设起点**: 当前假设机器人从入口 [0.0, 0.0, 0.0] 开始
   - 未来可以追踪实际当前位置

2. **移动顺序**: 先 x 后 y
   - 这是简化实现，避免斜向运动

3. **固定速度**: 0.2 m/s
   - 确保运动的可预测性

4. **阻塞执行**: 导航过程中会等待移动完成
   - 总用时 = (|dx| + |dy|) / 0.2

### 日志输出

```
[real_base.navigate_to_location] 目标位置: 卧室
[real_base.navigate_to_location] 目标坐标: [4.0, 1.0, 0.0]
[real_base.navigate_to_location] 需要移动: dx=4.0m, dy=1.0m
[real_base.navigate_to_location] 开始导航，共 2 步
[real_base.navigate_to_location] 步骤 1/2: right 4.0m (20.0s)
[real_base.navigate_to_location] 步骤 2/2: forward 1.0m (5.0s)
[real_base.navigate_to_location] 已导航到 卧室 (bedroom)，用时 25.0秒
```

### 未来改进

- [ ] 追踪机器人当前位置
- [ ] 支持障碍物避让
- [ ] 支持斜向运动（同时 x 和 y）
- [ ] 支持速度调整
- [ ] 支持路径优化

### 相关文件

- 模块文件: `/home/dora/RoboOs/RoboOS/slaver/demo_robot_local/module/real_base.py`
- 配置文件: `/home/dora/RoboOs/RoboOS/master/scene/profile.yaml`
- 映射文件: `/home/dora/RoboOs/RoboOS/master/scene/LOCATION_MAP.py`
- 开发板服务器: `/home/dora/RoboOs/RoboOS/base_server.py`
