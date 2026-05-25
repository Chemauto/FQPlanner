# Plan2: 通过 objects.yaml 配置场景物体

## 一、目标

1. 在 `scene/config/objects.yaml` 中以 YAML 格式声明要添加的物体
2. `MyKitchen` 读取该文件，自动创建并放置物体
3. 不需要改 Python 代码就能增删物体，编辑 YAML 即可

## 二、背景：robocasa 的物体创建流程

```
_load_model()
  → _setup_model()           # 已实现：创建场景、家具
  → _setup_kitchen_references()  # 注册家具引用（self.counter, self.stove 等）
  → _create_objects()         # 调用 _get_obj_cfgs() 获取物体配置
      → _get_obj_cfgs()       # 返回 [dict, dict, ...]
      → 对每个 dict 调用 create_obj() 创建物体
      → 用 placement_samplers 放置到指定家具上
```

**关键顺序**：`_setup_kitchen_references()` 在 `_create_objects()` 之前调用（kitchen.py 797 vs 800 行），所以 `_get_obj_cfgs()` 里可以用 `self.counter` 等引用。

## 三、YAML 配置格式设计

### objects.yaml 示例

```yaml
# 家具引用注册（_setup_kitchen_references 中使用）
# id 使用 FixtureType 枚举名，ref 表示参照哪个已注册的家具
fixture_refs:
  - name: counter
    id: COUNTER

  - name: stove
    id: STOVE

  - name: island
    id: ISLAND

  - name: sink
    id: SINK

  - name: cab
    id: CABINET

# 物体配置列表（_get_obj_cfgs 中使用）
objects:
  # 在炉灶旁边的台面上放一个锅
  - name: pot
    obj_groups: pot
    graspable: true
    placement:
      fixture: counter          # 引用 fixture_refs 中的名称
      sample_region_kwargs:
        ref: stove              # 引用 fixture_refs 中的名称
      size: [0.50, 0.30]
      pos: ["ref", -1.0]

  # 在岛台上放一个杯子
  - name: cup
    obj_groups: glass_cup
    graspable: true
    placement:
      fixture: island
      size: [0.40, 0.30]
      pos: [null, 1.0]

  # 在台面上放一个碗
  - name: bowl
    obj_groups: bowl
    graspable: true
    placement:
      fixture: island
      size: [0.30, 0.30]
```

### FixtureType 可用值

| 枚举名 | 说明 |
|--------|------|
| COUNTER | 台面 |
| ISLAND | 岛台 |
| STOVE | 炉灶 |
| SINK | 水槽 |
| CABINET | 橱柜 |
| CABINET_WITH_DOOR | 带门橱柜 |
| DRAWER | 抽屉 |
| FRIDGE | 冰箱 |
| MICROWAVE | 微波炉 |
| OVEN | 烤箱 |
| DISHWASHER | 洗碗机 |
| DINING_COUNTER | 餐台 |
| SHELF | 架子 |

### 常用 obj_groups 类别

```
pot, pan, saucepan, kettle_non_electric, glass_cup, mug, bowl, plate,
fork, knife, spoon, spatula, cutting_board, dish_rack, sponge,
vegetable, fruit, can, bottle, jar, bread, cake, meat, egg, ...
```

## 四、具体实现

### 修改文件 1：scene/config/objects.yaml（新增）

上述 YAML 示例内容。先放 3 个物体（锅、杯子、碗）验证。

### 修改文件 2：scene/make_scene.py

在 MyKitchen 类中新增/修改：

```python
def _setup_kitchen_references(self):
    """注册家具引用，从 objects.yaml 的 fixture_refs 部分读取"""
    super()._setup_kitchen_references()

    config = self._load_yaml("config/objects.yaml")
    if config is None:
        return

    from robocasa.models.fixtures.fixture import FixtureType

    for ref in config.get("fixture_refs", []):
        ref_name = ref["name"]
        fixture_type = FixtureType[ref["id"]]
        fn_kwargs = {"id": fixture_type}

        # 如果有 ref（参照家具），先查找已注册的
        if "ref" in ref:
            parent_name = ref["ref"]
            parent_fxtr = self.fixture_refs.get(parent_name)
            if parent_fxtr:
                fn_kwargs["ref"] = parent_fxtr[0] if isinstance(parent_fxtr, tuple) else parent_fxtr

        self.register_fixture_ref(ref_name, fn_kwargs)

def _get_obj_cfgs(self):
    """从 objects.yaml 读取物体配置，解析 fixture 引用"""
    config = self._load_yaml("config/objects.yaml")
    if config is None:
        return []

    cfgs = []
    for obj_cfg in config.get("objects", []):
        cfg = dict(obj_cfg)

        # 解析 placement 中的 fixture 字符串引用
        placement = cfg.get("placement", {})
        if "fixture" in placement and isinstance(placement["fixture"], str):
            ref_name = placement["fixture"]
            fxtr = self.fixture_refs.get(ref_name)
            if fxtr:
                placement["fixture"] = fxtr[0] if isinstance(fxtr, tuple) else fxtr

        # 解析 sample_region_kwargs 中的 ref 字符串引用
        region_kwargs = placement.get("sample_region_kwargs", {})
        if "ref" in region_kwargs and isinstance(region_kwargs["ref"], str):
            ref_name = region_kwargs["ref"]
            fxtr = self.fixture_refs.get(ref_name)
            if fxtr:
                region_kwargs["ref"] = fxtr[0] if isinstance(fxtr, tuple) else fxtr

        cfgs.append(cfg)

    return cfgs
```

### 不需要修改的文件

- `main.py` — 不变
- `utils.py` — 不变
- `scene/config/layout.yaml` — 不变
- `scene/config/style.yaml` — 不变

## 五、验证方法

1. 创建 objects.yaml 后运行 `python main.py --info`，确认不报错
2. 运行 `python main.py`，确认场景中出现了锅、杯子、碗
3. 修改 objects.yaml（删除碗），再次运行，确认碗消失
4. 添加新物体（如 `obj_groups: fork`），确认新物体出现

## 六、注意事项

1. **fixture_refs 必须先注册才能在 objects 中引用** — YAML 中 fixture_refs 的顺序有依赖关系，被参照的要写在前面
2. **obj_groups 使用 robocasa 预定义的类别名** — 如果填错会报错，可在 `robocasa/models/objects/kitchen_objects.py` 中查看完整列表
3. **物体放置是随机的** — 每次重置位置可能不同，但会落在指定区域内。设置 seed 可以固定
4. **objects.yaml 可以不存在** — 如果不创建该文件，`_get_obj_cfgs()` 返回 `[]`，行为与之前一致
