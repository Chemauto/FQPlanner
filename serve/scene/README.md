# scene/ - RoboCasa 厨房场景配置

## 主要功能
该文件夹下的功能主要是建立仿真环境，放置物体。

## 目录结构

```
scene/
├── make_scene.py      # MyKitchen 子类，从本地 YAML 加载场景和物体
├── config/
│   ├── layout.yaml    # 布局配置（墙壁、家具位置和类型）
│   ├── style.yaml     # 风格配置（3D 模型、材质纹理）
│   └── objects.yaml   # 物体配置（要放置的可操作物体）
└── utils/
    └── get_available_object.py  # 查询RoboCasa中所有可用物体类别和分组
```

## 配置文件说明

### layout.yaml — 布局
定义厨房的几何结构：墙壁、地面、家具的类型和位置。
编辑后下次加载生效，不需要改代码。

### style.yaml — 风格
定义家具的外观：具体的 3D 模型编号、橱柜颜色、台面材质等。

### objects.yaml — 物体
定义场景中要放置的可操作物体，包含两部分：

- `fixture_refs`：注册家具引用（counter、stove、island 等）
- `objects`：物体列表，每个物体指定类别、放置位置

```yaml
fixture_refs:
  - name: counter
    id: COUNTER

objects:
  - name: pot
    obj_groups: pot        # 物体类别名或分组名
    graspable: true
    placement:
      fixture: counter     # 放在哪个家具上
      size: [0.50, 0.30]  # 放置区域大小
```

## 常用操作

```bash
# 查看可用物体类别
python scene/utils/get_available_object.py

# 搜索物体
python scene/utils/get_available_object.py --search cup

# 查看分组详情
python scene/utils/get_available_object.py --detail cookware
```
