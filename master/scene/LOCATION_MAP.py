"""
位置名称映射表 (Location Name Mapping)

当修改场景配置文件时，需要同步更新此文件以保持中英文映射一致。

相关文件：
1. 场景配置文件：master/scene/profile.yaml
2. 映射配置文件：master/scene/LOCATION_MAP.py（本文件）
3. 使用映射的文件：slaver/demo_robot_local/base.py

修改场景时的步骤：
1. 在 master/scene/profile.yaml 中添加/修改场景定义
2. 在本文件的 LOCATION_MAP 中添加/修改对应的中英文映射
3. 重启 Master 和 Slaver 使配置生效

示例：
如果 profile.yaml 中添加了：
  - name: balcony
    type: location
    position: [5.0, 2.0, 0.0]
    description: "阳台"

则需要在 LOCATION_MAP 中添加：
    "阳台": "balcony"
"""

# 中文位置名称 -> 英文位置名称的映射
# 必须与 master/scene/profile.yaml 中的 name 字段保持一致
LOCATION_MAP = {
    # 场景位置 (Locations)
    "卧室": "bedroom",
    "客厅": "livingRoom",
    "入口": "entrance",
    "厨房": "kitchen",

    # 桌子 (Tables)
    "厨房桌子": "kitchenTable",
    "自定义桌子": "customTable",
    "服务桌": "servingTable",

    # 容器 (Containers)
    "篮子": "basket",
    "垃圾桶": "trashCan",
}

# 使用说明：
# from LOCATION_MAP import LOCATION_MAP
# target_en = LOCATION_MAP.get(target, target)
