# RoboCasa 开发文档

本文档记录了对 RoboCasa 代码库的深入分析，涵盖环境创建流程、场景系统、物体系统、控制接口等所有关键知识点。

---

## 目录

1. [项目概述](#1-项目概述)
2. [代码结构](#2-代码结构)
3. [环境注册机制](#3-环境注册机制)
4. [环境创建全流程](#4-环境创建全流程)
5. [场景系统（Layout + Style）](#5-场景系统layout--style)
6. [家具系统（Fixtures）](#6-家具系统fixtures)
7. [物体系统（Objects）](#7-物体系统objects)
8. [机器人控制](#8-机器人控制)
9. [渲染系统](#9-渲染系统)
10. [Demo 脚本分析](#10-demo-脚本分析)
11. [已知陷阱与踩坑记录](#11-已知陷阱与踩坑记录)
12. [项目自定义改造（MyKitchen）](#12-项目自定义改造mykitchen)
13. [物体配置系统（objects.yaml）](#13-物体配置系统objectsyaml)

---

## 1. 项目概述

RoboCasa 是基于 MuJoCo + RoboSuite 的大规模厨房机器人仿真框架。

- **365+ 任务环境**
- **60 种布局 × 60 种风格 = 3,600 种厨房场景**
- **3,200+ 3D 物体**
- **PandaOmron 机器人**（Franka Panda 机械臂 + Omron 移动底座）

### 核心依赖

| 依赖 | 版本 | 作用 |
|------|------|------|
| MuJoCo | 3.3.1 | 物理仿真引擎 |
| RoboSuite | 1.5.2+ | 机器人仿真框架 |
| Gymnasium | - | 标准 RL 环境接口 |
| NumPy | 2.2.5 | 数值计算 |

### 安装后必须做的事

```bash
# 1. 必须导入 robocasa 才能注册 Kitchen 环境到 robosuite
import robocasa

# 2. 下载资产文件（约 10GB）
python -m robocasa.scripts.download_kitchen_assets
```

---

## 2. 代码结构

```
robocasa/
├── environments/           # 任务环境
│   └── kitchen/
│       ├── kitchen.py      # Kitchen 基类（核心文件，1800+ 行）
│       ├── atomic/         # 15 个原子任务（抓放、开关门等）
│       └── composite/      # 362 个复合任务（62+ 类别）
├── models/
│   ├── assets/             # 原始资产文件（需下载）
│   │   ├── arenas/         # 空白厨房场地 XML
│   │   ├── fixtures/       # 固定设施 3D 模型（炉灶、水槽等）
│   │   ├── objects/        # 可操作物体 3D 模型（锅、杯子等）
│   │   │   ├── objaverse/  # 开源模型
│   │   │   ├── lightwheel/ # 自带模型
│   │   │   └── aigen/      # AI 生成模型
│   │   ├── scenes/         # 场景配置 YAML
│   │   │   ├── kitchen_layouts/{test|train}/layout001-060.yaml
│   │   │   └── kitchen_styles/{test|train}/style001-060.yaml
│   │   └── textures/       # 纹理文件
│   ├── fixtures/           # 设施类 Python 实现
│   ├── objects/            # 物体类 Python 实现
│   │   └── kitchen_objects.py  # 物体注册表（7万+ 行）
│   └── scenes/             # 场景构建
│       ├── scene_registry.py   # LayoutType/StyleType 枚举 + 路径解析
│       ├── scene_builder.py    # 从 YAML 创建家具对象
│       └── kitchen_arena.py    # KitchenArena 类
├── utils/
│   ├── env_utils.py        # 环境工具（create_env, create_obj, convert_action 等）
│   ├── object_utils.py     # 物体工具（位置查询、抓取检测等）
│   ├── camera_utils.py     # 相机配置
│   ├── placement_samplers.py  # 物体放置算法
│   └── dataset_registry.py # 数据集注册
├── scripts/                # 实用脚本
├── demos/                  # 交互式演示
└── wrappers/               # 环境封装
```

---

## 3. 环境注册机制

RoboSuite 使用 Python **元类（metaclass）** 自动注册环境。

### 注册流程

```python
# robosuite/environments/base.py

REGISTERED_ENVS = {}  # 全局字典：{类名: 类对象}

class EnvMeta(type):
    def __new__(meta, name, bases, class_dict):
        cls = super().__new__(meta, name, bases, class_dict)
        _unregistered_envs = ["MujocoEnv", "RobotEnv", "ManipulationEnv", "TwoArmEnv"]
        if cls.__name__ not in _unregistered_envs:
            register_env(cls)  # 自动注册到 REGISTERED_ENVS
        return cls

def make(env_name, *args, **kwargs):
    if env_name not in REGISTERED_ENVS:
        raise Exception(f"Environment {env_name} not found...")
    return REGISTERED_ENVS[env_name](*args, **kwargs)
```

### RoboCasa 的 Kitchen 注册

```python
# robocasa/environments/kitchen/kitchen.py

REGISTERED_KITCHEN_ENVS = {}

class KitchenEnvMeta(EnvMeta):
    def __new__(meta, name, bases, class_dict):
        cls = super().__new__(meta, name, bases, class_dict)
        if cls.__name__ not in ["MG_Robocasa_Env", "PickPlace", ...]:
            register_kitchen_env(cls)  # 注册到 Kitchen 专属字典
        return cls

class Kitchen(ManipulationEnv, metaclass=KitchenEnvMeta):
    ...
```

### 关键点

- **必须 `import robocasa`**：`robocasa/__init__.py` 导入了 Kitchen 类，触发元类注册。不导入则 `robosuite.make("Kitchen")` 找不到环境。
- Kitchen 类在**定义时**就被注册，不是在实例化时。
- 所有 Kitchen 子类（PickPlaceCounterToCabinet 等）定义时也自动注册。
- 用 `robosuite.make("Kitchen")` 或 `robosuite.make("PickPlaceCounterToCabinet")` 都可以。

---

## 4. 环境创建全流程

以 `robosuite.make("Kitchen", layout_and_style_ids=[[7, 1]])` 为例：

### 阶段 1：`__init__`（只保存参数）

```
Kitchen.__init__()
  → ManipulationEnv.__init__()
    → RobotEnv.__init__()
      → MujocoEnv.__init__()
        → 保存所有参数到 self（layout_ids, style_ids, robots, renderer 等）
        → 不创建任何仿真对象
```

Kitchen.__init__ 的关键参数：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `robots` | 必需 | 机器人型号，如 "PandaOmron" |
| `layout_ids` | None | 布局 ID 或 ID 列表 |
| `style_ids` | None | 风格 ID 或 ID 列表 |
| `layout_and_style_ids` | None | [[layout, style], ...] 配对列表 |
| `controller_configs` | None | 控制器配置 |
| `has_renderer` | False | 是否开启屏幕渲染 |
| `has_offscreen_renderer` | True | 是否开启离屏渲染 |
| `use_camera_obs` | True | 是否使用相机观测 |
| `seed` | None | 随机种子 |
| `translucent_robot` | False | 机器人是否半透明 |
| `clutter_mode` | 0 | 杂物模式（0=无，1=有） |
| `enable_fixtures` | None | 启用的家具列表 |
| `obj_instance_split` | None | 物体实例分割 |

### 阶段 2：`reset()`（真正构建场景）

```
env.reset()
  → _load_model(attempt_num=1)
    → _setup_model()

      ① 机器人初始化（设置 PandaOmron 的关节初始角度）
         kitchen.py 第 564-588 行

      ② 选择 layout 和 style
         kitchen.py 第 590-597 行
         - 如果 _ep_meta 中有 layout_id/style_id，直接用
         - 否则从 self.layout_and_style_ids 中随机选一组
         - 赋值给 self.layout_id, self.style_id

      ③ 创建 KitchenArena
         kitchen.py 第 611-618 行
         KitchenArena(layout_id=self.layout_id, style_id=self.style_id, ...)
           → 读取 layout YAML → layout_config (dict)
           → 读取 style YAML → style_config (dict)
           → create_fixtures(layout_config, style_config) → 创建所有家具对象

      ④ 设置相机
         kitchen.py 第 621 行
         CamUtils.set_cameras(self)

      ⑤ 设置渲染相机（mjviewer 模式）
         kitchen.py 第 624-628 行
         camera_config = CamUtils.LAYOUT_CAMS.get(self.layout_id, DEFAULT)

      ⑥ 保存家具配置和引用
         kitchen.py 第 631-632 行
         self.fixture_cfgs = self.mujoco_arena.get_fixture_cfgs()
         self.fixtures = {cfg["name"]: cfg["model"] for cfg in self.fixture_cfgs}

      ⑦ 组装 MuJoCo 模型
         kitchen.py 第 635-641 行
         self.model = ManipulationTask(
             mujoco_arena=self.mujoco_arena,
             mujoco_robots=[robot.robot_model for robot in self.robots],
             mujoco_objects=list(self.fixtures.values()),
         )

    → _load_model 继续执行（家具放置、物体创建等）
      kitchen.py 第 643-800 行

      ⑧ 放置家具到场景中
         计算每个家具的绝对位置、处理辅助家具、碰撞检测

      ⑨ 创建可操作物体
         kitchen.py 第 800 行
         self._create_objects()
           → self._get_obj_cfgs()  # 获取物体配置列表
           → 对每个配置调用 EnvUtils.create_obj() 创建物体
           → 使用 placement_samplers 放置物体

    → 组装最终的 MuJoCo XML 并初始化仿真

  → _reset_sim()
  → _setup_scene()        # 打开柜门等场景初始化
  → _reset_internal()     # 内部状态重置
  → _initialize_robot()   # 移动机器人到初始位置
```

### 关键方法调用顺序

```
__init__ → reset → _load_model → _setup_model → KitchenArena → fixtures
                                         ↓
                                    _create_objects → _get_obj_cfgs → objects
                                         ↓
                              _setup_kitchen_references → register_fixture_ref
                                         ↓
                                    _setup_scene → open doors etc.
                                         ↓
                                    _reset_internal
                                         ↓
                                    _initialize_robot → place robot near fixture
```

---

## 5. 场景系统（Layout + Style）

### Layout（布局）— 空间结构

布局定义厨房的**几何结构**：墙壁、地面、家具的类型和位置。

**文件位置**：`robocasa/models/assets/scenes/kitchen_layouts/{test|train}/layout001-060.yaml`
- test：layout 1-10（测试集）
- train：layout 11-60（训练集）

**YAML 结构**：

```yaml
# layout007.yaml 示例

room:
  walls:
    - name: wall_room
      type: wall
      size: [3.24, 1.5, 0.02]     # [宽, 高, 厚]
      pos: [3.2, 0.02, 1.5]        # [x, y, z] 位置
  floor:
    - name: floor_room
      type: floor
      size: [2.54, 3.24, 0.02]
      pos: [3.2, -2.5, -0.02]
  wall_accessories: [...]           # 墙上装饰（开关、插座等）
  floor_accessories: [...]          # 地面装饰（凳子等）

main_group:                         # 主墙面家具组
  group_origin: [0, 0]
  group_pos: [0.0, 0.0]
  group_z_rot: 0.0                  # 整组旋转角度（弧度）
  bottom_row:                       # 底层：台面、炉灶
    - name: counter_1
      type: counter
      size: [2.0, 0.65, 0.92]
    - name: stovetop
      type: stovetop
      size: [0.944, 0.55, 0.011]
  bottom_row_cabinets: [...]        # 底层橱柜、抽屉
  top_row: [...]                    # 顶层：吊柜、微波炉
  counter_stack: [...]              # 台面上方的柜体
  counter_accessories: [...]        # 台面小物件（烤面包机等）

island_group:                       # 岛台组（有些布局没有）
  bottom_row:
    - name: sink
      type: sink
    - name: island
      type: counter
      size: [2.5, 1.55, 0.92]

left_group:                         # 左侧墙家具组
  ...

right_group:                        # 右侧墙家具组
  ...

dining_group:                       # 餐厅组（有些布局没有）
  ...
```

**家具定位方式**：

1. **绝对定位**：直接指定 `pos: [x, y, z]`
2. **相对定位**：用 `align_to` 相对另一个家具定位
   ```yaml
   - name: counter_2
     type: counter
     align_to: counter_1    # 相对 counter_1
     side: right             # 放在右边
     alignment: top_back     # 顶部对齐
   ```
3. **整组旋转**：`group_z_rot` 让整组家具绕原点旋转（弧度）

### Style（风格）— 外观材质

风格定义所有家具的**外观、材质和具体型号**。

**文件位置**：`robocasa/models/assets/scenes/kitchen_styles/{test|train}/style001-060.yaml`

**YAML 结构**：

```yaml
# style001.yaml 示例

# 橱柜外观：[颜色/纹理, 面板样式, 把手样式]
cabinet:
  default: [white, CabinetDoorPanel003, CabinetHandle014]

# 台面材质
counter:
  default: [top_gentex086, base_gentex100]

# 地面纹理
floor: light_wood_long

# 墙面纹理
wall: white_tiles

# 各类家电的具体 3D 模型编号
sink: Sink009
stove: Stove028
microwave: Microwave035
fridge_bottom_freezer: Refrigerator032
dishwasher: Dishwasher036
toaster: Toaster059
stool: Stool009
```

### Layout 与 Style 的组合

```
Layout 定义 "主台面上放一个炉灶，位置在 [2.16, -0.36, 0.528]"
      ↓
Style 定义 "炉灶用 Stove028 这个 3D 模型，白色橱柜配大理石台面"
      ↓
scene_builder.py 把两者合并 → 创建实际的家具对象
```

### Scene Registry API

```python
from robocasa.models.scenes.scene_registry import LayoutType, StyleType, get_layout_path, get_style_path

# Layout 枚举
LayoutType.LAYOUT007  # = 7
LayoutType.TEST       # = -1（layouts 1-10）
LayoutType.TRAIN      # = -2（layouts 11-60）
LayoutType.ALL        # = -3（全部）
LayoutType.NO_ISLAND  # = -4
LayoutType.ISLAND     # = -5
LayoutType.DINING     # = -6

# 路径解析
get_layout_path(7)   # → .../kitchen_layouts/test/layout007.yaml
get_style_path(1)    # → .../kitchen_styles/test/style001.yaml

# 展开分组
unpack_layout_ids(LayoutType.TRAIN)  # → [11, 12, ..., 60]
unpack_style_ids(LayoutType.ALL)     # → [1, 2, ..., 60]
```

---

## 6. 家具系统（Fixtures）

### Fixture 基类

文件：`robocasa/models/fixtures/fixture.py`

```python
class Fixture(MujocoXMLObjectRobocasa):
    # 核心属性
    @property
    def pos(self):          # 返回 np.array([x, y, z])
    @property
    def quat(self):         # 返回 np.array([w, x, y, z])
    @property
    def euler(self):        # 返回 np.array([rx, ry, rz])
    @property
    def width(self):        # x 方向尺寸
    @property
    def depth(self):        # y 方向尺寸
    @property
    def height(self):       # z 方向尺寸
    @property
    def size(self):         # 返回 np.array([width, depth, height])
```

**注意**：`pos` 和 `euler` 返回的是 `string_to_array()` 的结果，可能是 list 而非 ndarray，使用时需要 `np.array(fxtr.pos, dtype=float)`。

### Fixture 子类

| 类型 | 文件 | 说明 |
|------|------|------|
| Counter | cabinets.py | 台面 |
| Stove | stove.py | 炉灶（含烤箱） |
| Stovetop | stove.py | 灶台（炉灶顶部） |
| Sink | sink.py | 水槽 |
| Microwave | microwave.py | 微波炉 |
| Oven | oven.py | 烤箱 |
| HingeCabinet | cabinets.py | 铰链门橱柜 |
| SingleCabinet | cabinets.py | 单门橱柜 |
| PanelCabinet | cabinets.py | 面板橱柜 |
| Drawer | cabinets.py | 抽屉 |
| FridgeBottomFreezer | fridge.py | 底部冷冻室冰箱 |
| FridgeSideBySide | fridge.py | 对开门冰箱 |
| Dishwasher | dishwasher.py | 洗碗机 |
| Hood | hood.py | 抽油烟机 |
| CoffeeMachine | coffee_machine.py | 咖啡机 |
| Toaster | toaster.py | 烤面包机 |
| Stool | accessories.py | 凳子 |
| Wall | wall.py | 墙壁 |
| Floor | floor.py | 地面 |

### Fixture 操作方法

```python
# 开关门（适用于 HingeCabinet, Microwave, Fridge 等）
fixture.open_door(env, min=0.5, max=1.0)   # 开门到 50%-100%
fixture.close_door(env, min=0.0, max=0.2)  # 关门到 0%-20%

# 开关抽屉
fixture.open_door(env, min=0.5, max=1.0)   # Drawer 也用 open_door

# 状态更新（每帧调用）
fixture.update_state(env)
```

### 从环境中查询家具

```python
# Kitchen 类的 get_fixture 方法
# kitchen.py 第 1628-1745 行

# 按名称精确查找
fxtr = env.get_fixture("counter_1_main_group")

# 按类型查找（随机返回一个匹配的）
from robocasa.models.fixtures import FixtureType
fxtr = env.get_fixture(FixtureType.COUNTER)

# 按类型 + 参照物查找（找离参照最近的）
fxtr = env.get_fixture(FixtureType.COUNTER, ref=stove_fixture)

# 按名称模糊匹配
fxtr = env.get_fixture("counter")  # 匹配名称包含 "counter" 的

# 获取所有匹配的
fxtrs = env.get_fixture(FixtureType.COUNTER, return_all=True)
```

### 注册家具引用（任务中使用）

```python
# 在 _setup_kitchen_references() 中注册
# 这样 _get_obj_cfgs() 中的 placement 就可以用注册名引用
self.counter = self.register_fixture_ref("counter", dict(id=FixtureType.COUNTER, ref=self.cab))
self.cab = self.register_fixture_ref("cab", dict(id=FixtureType.CABINET))
```

---

## 7. 物体系统（Objects）

### 物体来源

物体分为三个来源（`obj_registries`）：

| 来源 | 路径 | 说明 |
|------|------|------|
| `objaverse` | `models/assets/objects/objaverse/` | 开源 3D 模型库 |
| `lightwheel` | `models/assets/objects/lightwheel/` | RoboCasa 自带模型 |
| `aigen` | `models/assets/objects/aigen/` | AI 生成模型 |

### 物体分类（groups）

物体按类别分组，常见的 group 名称：

```
pot, pan, saucepan, kettle_non_electric, glass_cup, mug, bowl, plate,
fork, knife, spoon, spatula, cutting_board, dish_rack, sponge,
vegetable (carrot, tomato, bell_pepper, ...), fruit (apple, banana, ...),
can, bottle, jar, bread, cake, meat, egg, ...
```

### 采样物体

```python
# 从物体库随机采样一个物体
from robocasa.models.objects.kitchen_object_utils import sample_kitchen_object

mjcf_kwargs, info = sample_kitchen_object(
    groups="all",                    # 从所有类别采样
    obj_registries=["objaverse", "lightwheel"],
)
# info 包含：
#   mjcf_path: 模型文件路径
#   cat: 类别名（如 "pot"）
```

### 物体配置格式（在 _get_obj_cfgs 中使用）

```python
cfgs.append(dict(
    name="obj",                      # 物体名称（唯一标识）
    obj_groups="pot",                # 从 pot 类别采样
    exclude_obj_groups=None,         # 排除的类别
    graspable=True,                  # 是否可抓取
    washable=None,                   # 是否可水洗（放在水槽时自动设为 True）
    microwavable=None,               # 是否可微波
    cookable=None,                   # 是否可烹饪

    placement=dict(
        fixture=self.counter,         # 放在哪个家具上（fixture 对象或注册名）
        sample_region_kwargs=dict(    # 放置区域参数
            ref=self.stove,           # 参照家具
            loc="left_right",         # 位置方向
        ),
        size=(0.60, 0.30),           # 放置区域大小 [x, y]
        pos=("ref", -1.0),           # 放置位置（"ref" 表示参照家具方向）
        offset=(0.0, 0.10),          # 位置偏移
        rotation=(0, 0),             # 旋转范围 [min, max] 弧度
        margin=0.03,                 # 边距
        try_to_place_in=None,        # 尝试放入（容器类家具）
    ),
))
```

### 物体状态查询

```python
import robocasa.utils.object_utils as OU

# 检查物体是否被抓住
OU.check_obj_grasped(env, "obj", threshold=0.035)

# 检查物体是否在家具内
OU.obj_inside_of(env, "obj", "cabinet", partial_check=False, th=0.05)

# 检查物体是否在容器中
OU.check_obj_in_receptacle(env, "obj", "container")

# 检查物体是否直立
OU.check_obj_upright(env, "obj", th=15)

# 检查物体与家具的接触
OU.check_obj_fixture_contact(env, "obj", "stove")

# 检查夹爪是否远离物体
OU.gripper_obj_far(env, "obj", th=0.25)

# 物体与家具的最小距离
OU.obj_fixture_bbox_min_dist(env, "obj", fixture)
```

### 从仿真中获取物体信息

```python
# 获取物体位置
obj_pos = env.sim.data.body_xpos[env.obj_body_id["obj"]]

# 获取物体朝向（四元数）
obj_quat = env.sim.data.body_xquat[env.obj_body_id["obj"]]
```

---

## 8. 机器人控制

### PandaOmron 机器人

PandaOmron = Franka Panda 7-DOF 机械臂 + Omron 移动底座

**Body 名称**：
- `robot0_base` — 底座
- `robot0_link0` ~ `robot0_link7` — 机械臂关节
- `robot0_right_hand` — 末端执行器（夹爪）
- `gripper0_right_right_gripper` / `gripper0_right_leftfinger` — 夹爪手指

### 动作空间

动作是 12 维向量（对应 composite controller）：

```
action[0:3]   → 末端执行器位置增量 [dx, dy, dz]
action[3:6]   → 末端执行器旋转增量 [droll, dpitch, dyaw]
action[6:7]   → 夹爪 [0=打开, 1=关闭]
action[7:11]  → 底座移动 [dx, dy, drot, ?]
action[11:12] → 控制模式切换
```

### 控制器

```python
from robosuite.controllers import load_composite_controller_config

# 加载 PandaOmron 的复合控制器配置
config = load_composite_controller_config(robot="PandaOmron")
# 配置文件位置：robosuite/controllers/config/robots/default_pandaomron.json
```

### 键盘控制映射

在 `collect_human_trajectory` 中，键盘输入通过 `device.input2action()` 转换为动作：

| 按键 | 功能 |
|------|------|
| W/S | 沿 x 轴前后移动末端 |
| A/D | 沿 y 轴左右移动末端 |
| Q/E | 沿 z 轴上下移动末端 |
| 方向键 | 旋转末端执行器 |
| Z | 关闭夹爪 |
| X | 打开夹爪 |

### 获取机器人状态

```python
# 末端执行器位置
ee_id = env.sim.model.body_name2id("robot0_right_hand")
ee_pos = env.sim.data.body_xpos[ee_id].copy()

# 底座位置
base_id = env.sim.model.body_name2id("robot0_base")
base_pos = env.sim.data.body_xpos[base_id].copy()

# 末端执行器朝向
ee_quat = env.sim.data.body_xquat[ee_id].copy()
```

---

## 9. 渲染系统

### 两种渲染模式

| 模式 | 参数 | 说明 |
|------|------|------|
| **On-screen** | `has_renderer=True, renderer="mjviewer"` | 打开 MuJoCo 窗口，可交互 |
| **Off-screen** | `has_offscreen_renderer=True` | 渲染到内存，用于保存图片/训练 |

**注意**：`has_renderer=True` 时不需要 `has_offscreen_renderer=True`，二者通常是互斥的。

### MjviewerRenderer 的工作方式

文件：`robosuite/renderers/viewer/mjviewer_renderer.py`

```python
class MjviewerRenderer:
    def render(self):
        pass  # 空方法！什么都不做

    def update(self):
        if self.viewer is None:
            self.viewer = viewer.launch_passive(...)  # 首次创建 viewer
            # 设置相机参数
            self.viewer.cam.lookat = ...
            self.viewer.cam.distance = ...
            self.viewer.cam.azimuth = ...
            self.viewer.cam.elevation = ...
        self.viewer.sync()  # 同步画面
```

### 重要陷阱：mjviewer 的 update 调用时机

```python
# robosuite/environments/base.py 第 512-518 行

# 在 env.step() 内部
if self.viewer is not None and self.renderer != "mujoco":
    self.viewer.update()                    # ← 只有非 mjviewer 才自动调用
elif self.has_renderer and self.renderer == "mjviewer" and self.viewer is None:
    self.initialize_renderer()
    self.viewer.update()                    # ← 仅在 viewer 为 None 时调用一次
```

**结论**：使用 `renderer="mjviewer"` 时，`viewer.update()` 不会在 `step()` 中自动调用。
必须在循环中手动调用 `env.viewer.update()`，否则画面冻结且无法鼠标交互。

### 相机配置

```python
# 每个 layout 有预设的最佳相机角度
# robocasa/utils/camera_utils.py

# kitchen.py 第 624-628 行
if self.renderer == "mjviewer":
    camera_config = CamUtils.LAYOUT_CAMS.get(self.layout_id, CamUtils.DEFAULT_LAYOUT_CAM)
    self.renderer_config = {"cam_config": camera_config}
```

默认相机参数（DEFAULT_LAYOUT_CAM）：

```python
DEFAULT_FREE_CAM = {
    "lookat": [0, 0, 1],
    "distance": 2,
    "azimuth": 180,
    "elevation": -20,
}
```

### EnclosingWallRenderWrapper

```python
from robocasa.wrappers.enclosing_wall_render_wrapper import (
    EnclosingWallRenderWrapper,
    install_enclosing_wall_hotkeys,
)

# 包裹环境，让外墙半透明
env = EnclosingWallRenderWrapper(env, alpha=0.1, enabled=True)

# 安装热键回调
install_enclosing_wall_hotkeys(env)
# Esc — 切换墙壁 透明/不透明
# [   — 强制墙壁不透明
# ]   — 强制墙壁透明
```

---

## 10. Demo 脚本分析

### demo_kitchen_scenes.py — 场景浏览 + 遥操作

```python
# 创建环境（不指定 layout/style，后续动态设置）
env = robosuite.make("Kitchen", ...)
env = EnclosingWallRenderWrapper(env, ...)

# 动态设置 layout/style
env.layout_and_style_ids = [[layout, style]]

# 通过 collect_human_trajectory 进行遥操作
collect_human_trajectory(env, device, "right", "single-arm-opposed", ...)
```

**关键点**：
- 环境创建时不指定 layout/style
- 在每次循环前通过 `env.layout_and_style_ids` 设置
- `collect_human_trajectory` 内部调用 `env.reset()` 使设置生效
- 使用 `has_offscreen_renderer=False`（纯屏幕渲染）
- `has_renderer=True, renderer="mjviewer"`

### collect_human_trajectory 的内部流程

```python
def collect_human_trajectory(env, device, arm, env_configuration, ...):
    env.reset()                   # 重置环境
    env.render()                  # 首次渲染
    device.start_control()        # 启动设备监听

    # 做一个空的 dummy step 初始化
    env.step(zero_action)

    while True:
        input_ac_dict = device.input2action()  # 读取输入

        if input_ac_dict is None:  # 用户按了退出键
            break

        if 没有有效输入:
            env.render()           # 仍然刷新画面
            continue               # 不执行 step

        env.step(action)           # 执行动作
        env.render()               # 刷新画面

        if 任务连续成功15帧:
            break

        if max_fr:
            sleep(...)             # 帧率控制
```

### demo_objects.py — 物体查看器

```python
# 随机采样物体
mjcf_kwargs, info = sample_kitchen_object(groups="all")

# 加载模型（添加白色背景和光源）
sim = read_model(filepath, hide_sites=False)

# 渲染
viewer = render_model(sim, cam_settings)
# 按 N 查看下一个，Q 退出
```

---

## 11. 已知陷阱与踩坑记录

### 1. 必须导入 robocasa

```python
import robocasa  # 缺少这行 → robosuite.make("Kitchen") 报 "Environment Kitchen not found"
```

**原因**：Kitchen 类通过元类在 `import` 时注册到 `REGISTERED_ENVS`。

### 2. mjviewer 需要手动 update

```python
# ❌ 错误：画面冻结，无法鼠标交互
env.step(action)
env.render()

# ✅ 正确：手动 sync
env.step(action)
env.render()
env.viewer.update()
```

### 3. has_renderer 和 has_offscreen_renderer 的关系

```python
# ❌ 两个都 True：浪费资源
has_renderer=True, has_offscreen_renderer=True

# ✅ 屏幕渲染模式
has_renderer=True, has_offscreen_renderer=False

# ✅ 离屏渲染模式（训练/录制视频）
has_renderer=False, has_offscreen_renderer=True
```

### 4. Fixture 的 pos/size/euler 类型不稳定

```python
# pos 可能返回 list 或 ndarray，取决于 XML 解析
fxtr.pos    # 可能是 list
fxtr.euler  # 可能是 list

# 安全做法
np.array(fxtr.pos, dtype=float)
np.array(fxtr.size, dtype=float)
```

### 5. layout_id/style_id 在 reset() 之后才设置

```python
env = robosuite.make("Kitchen", layout_and_style_ids=[[7, 1]])
# 此时 env.layout_id 不存在！

env.reset()
# 现在 env.layout_id = 7, env.style_id = 1
# env.fixtures 字典可用
```

### 6. PandaOmron 的末端执行器名称

```python
# ❌ 不存在 "robot0_left_hand"
ee_id = env.sim.model.body_name2id("robot0_left_hand")  # ValueError

# ✅ 正确名称
ee_id = env.sim.model.body_name2id("robot0_right_hand")
```

### 7. KitchenArena 支持 dict 传入

```python
# 标准用法（从路径读取 YAML）
arena = KitchenArena(layout_id=7, style_id=1)

# 直接传 dict（不读文件）
layout_config = yaml.safe_load(open("layout007.yaml"))
style_config = yaml.safe_load(open("style001.yaml"))
arena = KitchenArena(layout_id=layout_config, style_id=style_config)
```

这个特性可用于从本地 `scene/` 目录加载自定义配置。

### 8. Kitchen 基类没有物体

`Kitchen` 的 `_get_obj_cfgs()` 返回 `[]`，所以场景里只有固定家具，没有可抓取的物体。
需要继承 Kitchen 并重写 `_get_obj_cfgs()` 才能添加物体。

### 9. renderer 参数不能为 None

```python
# ❌ 不渲染时不能传 renderer=None
env = robosuite.make("Kitchen", ..., renderer=None)  # AttributeError

# ✅ 不渲染时不传 renderer 参数
env = robosuite.make("Kitchen", ..., has_renderer=False, has_offscreen_renderer=True)
```

### 10. 相机视角依赖 layout_id

```python
# kitchen.py 第 624-628 行
camera_config = CamUtils.LAYOUT_CAMS.get(self.layout_id, CamUtils.DEFAULT_LAYOUT_CAM)
```

当 `layout_id` 是 dict 时（自定义配置），相机视角会回退到 DEFAULT_LAYOUT_CAM。
如果需要特定视角，需要手动设置 `renderer_config`。

---

## 12. 项目自定义改造（MyKitchen）

### 当前项目结构

```
FQPlanner/serve/
├── main.py               # 主程序入口
├── utils/
│   └── utils.py           # 工具函数（create_scene、init_device 等）
└── scene/
    ├── make_scene.py      # MyKitchen 子类（核心）
    ├── config/
    │   ├── layout.yaml    # 布局配置（从 robocasa layout07 复制）
    │   ├── style.yaml     # 风格配置（从 robocasa style01 复制）
    │   └── objects.yaml   # 物体配置（自定义）
    └── utils/
        └── get_available_object.py  # 物体类别查询工具
```

### MyKitchen 类的设计

继承 Kitchen，重写三个方法：

1. **`_setup_model()`**：从本地 `scene/config/` 读取 layout.yaml 和 style.yaml，以 dict 传给 KitchenArena，绕过 robocasa 标准路径
2. **`_setup_kitchen_references()`**：从 `objects.yaml` 的 `fixture_refs` 部分注册家具引用（counter、stove、island 等）
3. **`_get_obj_cfgs()`**：从 `objects.yaml` 的 `objects` 部分读取物体配置，解析字符串引用为实际 fixture 对象

### 关键调用顺序

```
_load_model()
  → _setup_model()              # 创建场景、家具（layout.yaml + style.yaml）
  → _setup_kitchen_references() # 注册家具引用（objects.yaml fixture_refs）
  → _create_objects()            # 创建物体
      → _get_obj_cfgs()          # 读取物体配置（objects.yaml objects）
```

`_setup_kitchen_references()` 在 `_create_objects()` 之前调用（kitchen.py 797 vs 800 行），所以 `_get_obj_cfgs()` 中可以用 `self.counter` 等引用。

### CamUtils 导入方式

```python
# ❌ 不存在 CamUtils 类
from robocasa.utils.camera_utils import CamUtils

# ✅ 正确：导入模块本身
import robocasa.utils.camera_utils as CamUtils
```

---

## 13. 物体配置系统（objects.yaml）

### 配置格式

```yaml
# 家具引用注册
fixture_refs:
  - name: counter
    id: COUNTER              # FixtureType 枚举名
  - name: stove
    id: STOVE
  - name: island
    id: ISLAND
  - name: cab
    id: CABINET
    ref: counter             # 可选：参照已注册的家具（找离 counter 最近的 CABINET）

# 物体列表
objects:
  - name: pot
    obj_groups: pot          # 类别名或分组名
    graspable: true
    placement:
      fixture: counter       # 引用 fixture_refs 中的名称
      sample_region_kwargs:
        ref: stove           # 引用 fixture_refs 中的名称
      size: [0.50, 0.30]    # 放置区域大小（不是物体大小）
      pos: ["ref", -1.0]
```

### 物体尺寸

物体尺寸由 3D 模型文件决定，无法通过配置修改。`placement.size` 控制的是**放置区域大小**（物体可以落在哪块范围内），不是物体本身的尺寸。

### FixtureType 可用枚举

| 枚举 | 说明 |
|------|------|
| COUNTER | 台面 |
| ISLAND | 岛台 |
| STOVE | 炉灶 |
| SINK | 水槽 |
| CABINET | 橱柜 |
| FRIDGE | 冰箱 |
| MICROWAVE | 微波炉 |
| OVEN | 烤箱 |
| DISHWASHER | 洗碗机 |
| DINING_COUNTER | 餐台 |
| DRAWER | 抽屉 |

### 物体类别与分组

- **类别（category）**：198 个，最小单位，如 `pot`、`apple`、`fork`
- **分组（group）**：230 个，类别的集合，如 `cookware = [pan, pot, saucepan, kettle_non_electric]`
- `obj_groups` 字段填类别名或分组名都可以
- 查询工具：`python scene/utils/get_available_object.py --search pot`

### 常用分组

| 分组 | 包含 |
|------|------|
| cookware | pan, pot, saucepan, kettle_non_electric |
| food | 130+ 个食物类 |
| fruit | apple, banana, orange 等 19 个 |
| vegetable | carrot, tomato 等 36 个 |
| meat | fish, steak 等 18 个 |
| drink | beer, water, milk 等 13 个 |
| utensil | fork, knife, spoon 等 7 个 |
| dairy | cheese, egg, milk 等 5 个 |
