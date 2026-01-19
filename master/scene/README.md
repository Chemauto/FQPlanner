# 场景配置说明

## 文件说明

### profile.yaml
场景定义文件，包含所有位置、物体和容器的坐标信息。

### LOCATION_MAP.py
中文名称到英文名称的映射表。

---

## 坐标系统

- **x轴**: 左右方向（右为正）
- **y轴**: 前后方向（前为正）
- **z轴**: 垂直方向（通常为0）

---

## 修改场景

### 步骤 1: 修改 profile.yaml

```yaml
scene:
  - name: balcony          # 英文名称
    type: location        # 类型: location/table/container
    position: [5.0, 2.0, 0.0]  # [x, y, z] 坐标
    description: "阳台"   # 中文名称
```

### 步骤 2: 更新 LOCATION_MAP.py

```python
LOCATION_MAP = {
    "阳台": "balcony",  # 中文名称 -> 英文名称
}
```

### 步骤 3: 重启服务

```bash
# 重启 Master
python master/run.py

# 重启 Slaver
python slaver/run.py
```

---

## 当前场景位置

| 中文名称 | 英文名称 | 坐标 [x,y,z] | 类型 |
|---------|---------|-------------|------|
| 入口 | entrance | [0.0, 0.0, 0.0] | location |
| 客厅 | livingRoom | [0.0, 0.4, 0.0] | location |
| 卧室 | bedroom | [0.0, 0.6, 0.0] | location |
| 厨房 | kitchenTable | [0.2, 0.0, 0.0] | location |
| 厕所 | bathroom | [0.6, 0.0, 0.0] | location |

---

## 导航示例

基于当前坐标（从入口 [0,0,0] 出发）：

- **去客厅**: 向前 0.4 米（2秒 @ 0.2 m/s）
- **去卧室**: 向前 0.6 米（3秒 @ 0.2 m/s）
- **去厨房**: 向右 0.2 米（1秒 @ 0.2 m/s）
- **去厕所**: 向右 0.6 米（3秒 @ 0.2 m/s）

---

## 常见问题

**Q: 为什么找不到位置？**
- 确认 `profile.yaml` 中的 `name` 与 `LOCATION_MAP.py` 中的值一致
- 确认 `profile.yaml` 中的 `description` 与 `LOCATION_MAP.py` 中的键一致
- 重启 Master 和 Slaver

**Q: 坐标不对？**
- 检查 profile.yaml 中的 position 值
- 重启 Master 服务
