# AGENTS.md — 场景物体管理指南

## 添加可抓取物体

### 需要修改的文件（2 个）

**1. `scene/config/objects.yaml`** — 添加物体定义

```yaml
objects:
  - name: my_obj           # 唯一名称（API 调用时用这个名字）
    obj_groups: apple       # 物体类别（见下方查询方法）
    graspable: true
    placement:
      fixture: counter      # 放在哪个家具上（引用 fixture_refs 中的 name）
      size: [0.30, 0.30]   # 放置区域大小 [宽, 深]
```

**2. `scene/config/target.yaml`** — 添加放置目标点

```yaml
my_obj:
  target: [0.0, 0.0, 0.5]  # 世界坐标（运行后根据实际家具位置调整）
  snap_threshold: 0.3       # 瞬移触发距离
```

### 不需要修改的文件

- `arm.py` — 通用函数，不硬编码物体名
- `server.py` — API 端点通用，`obj_name` 由请求传入
- `web.py` — 物体名由输入框填写，不硬编码

### 查询可用物体类别

```bash
python scene/utils/get_available_object.py --search apple
```

### 获取家具坐标（用于 target.yaml）

运行场景后通过 API 或 Python 查询：
- API: `GET /objects` 返回所有物体当前坐标
- Python: `env.sim.data.body_xpos[env.fixture_body_ids["counter"]]`

## 抓取与放置机制

### grasp（抓取）
1. `move_to` 到物体位置，误差 < 0.15m 停止
2. 吸附：修改物体 qpos 瞬移到夹爪位置
3. 关夹爪 10 步
4. 提起 0.2m

### place（放置）
1. `move_to` 到目标位置，误差 < 0.15m 停止
2. 开夹爪 10 步（先松开物体）
3. 瞬移：修改物体 qpos 到目标点
4. 提起 0.2m

## 控制器参数

位置: `robosuite/controllers/config/robots/default_pandaomron.json`

| 参数 | 值 | 说明 |
|------|-----|------|
| `output_max` | 0.10 | 每步最大位移 10cm |
| `ramp_ratio` | 1.0 | 无加速延迟 |

`arm.py` 中 `move_to` 的 `max_step` 必须与 `output_max` 一致。
