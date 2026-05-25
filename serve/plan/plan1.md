# Plan1: 从本地 scene/ 目录加载场景 + 自定义物体

## 一、目标

1. 让代码从 `my_code/work/scene/` 目录读取 layout YAML 和 style YAML，而不是从 robocasa 标准路径
2. 支持自定义物体放置（后续在台面上放锅、杯子等）
3. 编辑 `scene/layout007.yaml` 后场景跟着变化

## 二、当前流程 vs 改造后流程

### 当前流程

```
main.py
  → utils.create_scene(layout_id=7, style_id=1)
    → robosuite.make("Kitchen", layout_and_style_ids=[[7, 1]])
      → Kitchen.__init__() 保存参数
      → env.reset()
        → _setup_model()
          → self.layout_id = 7  (从 layout_and_style_ids 随机选)
          → self.style_id = 1
          → KitchenArena(layout_id=7, style_id=1)
            → get_layout_path(7)  →  robocasa/models/assets/.../layout007.yaml  ← 读标准路径
            → get_style_path(1)   →  robocasa/models/assets/.../style001.yaml   ← 读标准路径
            → create_fixtures(layout_config, style_config)  → 创建所有家具
          → _create_objects()
            → _get_obj_cfgs() 返回 []  ← 空的，没有任何物体
```

### 改造后流程

```
main.py
  → utils.create_scene(scene_dir="scene")
    → 读取 scene/layout007.yaml → layout_config (dict)
    → 读取 scene/style001.yaml  → style_config (dict)
    → 自定义 MyKitchen 类
      → _setup_model() 中把 layout_config 和 style_config 作为 dict 传给 KitchenArena
        → KitchenArena(layout_id=layout_config, style_id=style_config)  ← KitchenArena 已支持 dict
          → 不再调用 get_layout_path / get_style_path
          → 直接使用传入的 dict 创建家具
      → _get_obj_cfgs() 返回物体配置列表（后续可添加物体）
```

## 三、关键发现：KitchenArena 已支持 dict 传入

`kitchen_arena.py` 第 109-136 行的代码：

```python
# layout_id 可以是 dict（直接用）或 int（从标准路径读 YAML）
if isinstance(layout_id, dict):
    layout_config = layout_id       # ← 直接用 dict，不走 get_layout_path
else:
    layout_path = get_layout_path(layout_id=layout_id)  # ← 从标准路径读
    with open(layout_path, "r") as f:
        layout_config = yaml.safe_load(f)

# style_id 同理
if isinstance(style_id, dict):
    style_config = style_id         # ← 直接用 dict
else:
    style_path = get_style_path(style_id=style_id)
    with open(style_path, "r") as f:
        style_config = yaml.safe_load(f)
```

所以只需要我们自己读 YAML，把 dict 传进去即可，不需要修改 KitchenArena 的代码。

## 四、具体实现方案

### 文件结构

```
my_code/work/
├── utils.py              # 工具函数（修改）
├── main.py               # 主程序（修改）
├── my_kitchen.py          # 新增：自定义 Kitchen 子类
├── scene/
│   ├── layout007.yaml     # 布局配置（可编辑）
│   └── style001.yaml      # 风格配置（可编辑）
└── plan/
    └── plan1.md
```

### 文件 1：my_kitchen.py（新增）

继承 Kitchen，做两件事：
1. 重写 `_setup_model()`，从本地 YAML 读取配置，以 dict 形式传给 KitchenArena
2. 重写 `_get_obj_cfgs()`，目前返回空列表，后续添加物体配置

```python
import yaml
from robocasa.environments.kitchen.kitchen import Kitchen, KitchenArena

class MyKitchen(Kitchen):
    def __init__(self, scene_dir=None, *args, **kwargs):
        self.scene_dir = scene_dir
        super().__init__(*args, **kwargs)

    def _setup_model(self):
        # 先调用父类的大部分逻辑（机器人初始化等）
        # 但跳过 KitchenArena 的创建，我们自己来

        # ... 保留父类的机器人初始化代码 ...

        # 从本地 scene/ 读取 YAML
        layout_config = self._load_yaml("layout007.yaml")
        style_config = self._load_yaml("style001.yaml")

        # 以 dict 形式传给 KitchenArena
        self.mujoco_arena = KitchenArena(
            layout_id=layout_config,    # dict，KitchenArena 会直接使用
            style_id=style_config,      # dict，KitchenArena 会直接使用
            rng=self.rng,
            enable_fixtures=self.enable_fixtures,
            clutter_mode=self.clutter_mode,
        )
        # ... 后续代码与父类一致 ...

    def _get_obj_cfgs(self):
        return []  # 暂时为空，后续添加物体

    def _check_success(self):
        return False

    def _load_yaml(self, filename):
        import os
        path = os.path.join(self.scene_dir, filename)
        with open(path, "r") as f:
            return yaml.safe_load(f)
```

**难点**：`_setup_model()` 中有大量代码（机器人初始化、相机设置、家具引用等）。
不能完全重写，只能部分重写。具体做法是：
- 调用 `super()._setup_model()` 的前半部分（机器人初始化）
- 替换 KitchenArena 创建部分（从本地读 YAML）
- 保留后半部分（相机、家具引用等）

**实际上更好的做法**：
不重写 `_setup_model()`，而是在 `_setup_model()` 之前把 `self.layout_id` 和 `self.style_id` 设为 dict。
但 `_setup_model()` 中有 `self.rng.choice(self.layout_and_style_ids)` 的逻辑，layout_id 是在 `_setup_model()` 内部赋值的。

**最终做法**：
重写 `_setup_model()`，在其中：
1. 复制父类 `_setup_model()` 的机器人初始化代码
2. 自己读本地 YAML
3. 以 dict 传给 KitchenArena
4. 复制父类 `_setup_model()` 的后续代码（相机、家具引用）

需要复制的代码行：`kitchen.py` 第 560-641 行。

### 文件 2：utils.py（修改）

`create_scene()` 改为使用 `MyKitchen` 类：

```python
def create_scene(scene_dir="scene", seed=42):
    import os
    from my_kitchen import MyKitchen

    env = MyKitchen(
        scene_dir=os.path.abspath(scene_dir),
        robots="PandaOmron",
        controller_configs=load_composite_controller_config(robot="PandaOmron"),
        has_renderer=True,
        has_offscreen_renderer=False,
        render_camera=None,
        ignore_done=True,
        use_camera_obs=False,
        control_freq=20,
        renderer="mjviewer",
        translucent_robot=False,
        seed=seed,
    )

    env = EnclosingWallRenderWrapper(env, alpha=0.1, enabled=True)
    install_enclosing_wall_hotkeys(env)
    return env
```

注意：不再传 `layout_and_style_ids`，因为 MyKitchen 会从 scene/ 目录读取。

### 文件 3：main.py（微调）

```python
# 改前
env = create_scene(layout_id=7, style_id=1, seed=42)

# 改后
env = create_scene(scene_dir="scene", seed=42)
```

其余不变。

## 五、验证方法

1. 运行 `python main.py --info`，确认打印的家具列表和位置与之前完全一致
2. 运行 `python main.py`，确认场景视觉效果与之前一致
3. 修改 `scene/layout007.yaml` 中某个家具的位置，再次运行确认变化生效

## 六、后续扩展（本次不做）

在 `_get_obj_cfgs()` 中添加物体：

```python
def _get_obj_cfgs(self):
    cfgs = []

    # 在主台面上放一个锅
    cfgs.append(dict(
        name="pot",
        obj_groups="pot",
        graspable=True,
        placement=dict(
            fixture=self.counter,     # 放在台面上
            sample_region_kwargs=dict(ref=self.stove),
            size=(0.50, 0.30),
            pos=("ref", -1.0),
        ),
    ))

    # 在岛台上放一个杯子
    cfgs.append(dict(
        name="cup",
        obj_groups="glass_cup",
        graspable=True,
        placement=dict(
            fixture=self.island,
            size=(0.40, 0.30),
            pos=(None, 1.0),
        ),
    ))

    return cfgs
```

## 七、注意事项

1. `KitchenArena` 接收 dict 后，不再经过 `get_layout_path()`，所以 `scene/` 下的文件名可以随意命名
2. 3D 模型文件（Stove028 等）仍然从 robocasa 标准路径加载，YAML 中引用的模型名必须与标准路径中的一致
3. 相机配置 `CamUtils.LAYOUT_CAMS` 使用 `layout_id` 作为 key，传 dict 后需要用固定值或直接指定相机配置
