"""
获取 Rs_int 场景的物体数据（轻量版）

用法:
    conda activate behavior
    python get_scene_data.py
"""

import os
import sys
os.environ["OMNIGIBSON_HEADLESS"] = "True"

import yaml
import json

# 分类集合
TABLE_CATS = {"breakfast_table", "coffee_table", "dining_table", "desk",
              "side_table", "console_table", "countertop", "workbench"}
CONTAINER_CATS = {"fridge", "bottom_cabinet", "top_cabinet", "microwave", "oven",
                  "dishwasher", "public_trash_can", "trash_can", "cabinet", "drawer"}
SKIP_CATS = {"ceilings", "floors", "walls", "agent", "door", "openable_window",
             "electric_switch", "floor_lamp", "table_lamp", "mirror", "picture",
             "towel_rack", "shower_stall", "toilet", "pedestal_sink", "furniture_sink", "carpet"}

# 中文描述
ZH_DESC = {
    "breakfast_table": "早餐桌", "coffee_table": "咖啡桌", "dining_table": "餐桌",
    "desk": "书桌", "side_table": "边桌", "console_table": "玄关桌",
    "countertop": "料理台", "workbench": "工作台",
    "fridge": "冰箱", "microwave": "微波炉", "oven": "烤箱", "dishwasher": "洗碗机",
    "bottom_cabinet": "底柜", "top_cabinet": "吊柜", "cabinet": "柜子",
    "public_trash_can": "垃圾桶", "trash_can": "垃圾桶",
    "laptop": "笔记本电脑", "cup": "杯子", "bowl": "碗", "plate": "盘子",
    "apple": "苹果", "banana": "香蕉", "orange": "橘子",
    "book": "书", "phone": "手机", "bottle": "瓶子",
}


def main():
    print("=" * 60)
    print("Rs_int 场景数据提取")
    print("=" * 60)

    import omnigibson as og
    from omnigibson.macros import gm

    gm.USE_GPU_DYNAMICS = False
    gm.ENABLE_FLATCACHE = True

    # 加载场景
    config_path = os.path.join(og.example_config_path, "tiago_primitives.yaml")
    with open(config_path, "r") as f:
        cfg = yaml.safe_load(f)

    cfg["scene"]["scene_model"] = "Rs_int"
    cfg["task"] = {"type": "DummyTask"}

    # 最小化渲染
    cfg["render"]["viewer_width"] = 64
    cfg["render"]["viewer_height"] = 64
    for robot_cfg in cfg.get("robots", []):
        if "sensor_config" in robot_cfg:
            for sensor_name, sensor_cfg in robot_cfg["sensor_config"].items():
                if "sensor_kwargs" in sensor_cfg:
                    sensor_cfg["sensor_kwargs"]["image_height"] = 32
                    sensor_cfg["sensor_kwargs"]["image_width"] = 32

    print("\n[1/3] 加载 Rs_int 场景...")
    sys.stdout.flush()

    try:
        env = og.Environment(configs=cfg)
        env.reset()
    except Exception as e:
        print(f"加载失败: {e}")
        return

    print("[1/3] 场景加载完成")
    sys.stdout.flush()

    # 收集物体
    print("[2/3] 读取物体数据...")
    sys.stdout.flush()

    tables = []
    containers = []
    objects = []

    try:
        for obj in env.scene.object_registry.objects:
            cat = getattr(obj, "category", "")
            if cat in SKIP_CATS:
                continue

            pos, _ = obj.get_position_orientation()
            pos_list = [round(float(p), 3) for p in pos.tolist()]

            if cat in TABLE_CATS:
                tables.append({"name": obj.name, "category": cat, "position": pos_list})
            elif cat in CONTAINER_CATS:
                containers.append({"name": obj.name, "category": cat, "position": pos_list})
            elif cat in ZH_DESC:
                objects.append({"name": obj.name, "category": cat, "position": pos_list})
    except Exception as e:
        print(f"读取物体失败: {e}")

    print(f"[2/3] 找到 {len(tables)} 个桌子, {len(containers)} 个容器, {len(objects)} 个物体")
    sys.stdout.flush()

    # 打印结果
    print("\n--- 桌子 ---")
    for t in tables:
        desc = ZH_DESC.get(t["category"], t["category"])
        print(f"  {t['name']:30s} [{t['position'][0]:7.3f}, {t['position'][1]:7.3f}, {t['position'][2]:7.3f}]  {desc}")

    print("\n--- 容器 ---")
    for c in containers:
        desc = ZH_DESC.get(c["category"], c["category"])
        print(f"  {c['name']:30s} [{c['position'][0]:7.3f}, {c['position'][1]:7.3f}, {c['position'][2]:7.3f}]  {desc}")

    print("\n--- 常见物体 ---")
    for o in objects:
        desc = ZH_DESC.get(o["category"], o["category"])
        print(f"  {o['name']:30s} [{o['position'][0]:7.3f}, {o['position'][1]:7.3f}, {o['position'][2]:7.3f}]  {desc}")

    sys.stdout.flush()

    # 保存 JSON
    all_data = {"tables": tables, "containers": containers, "objects": objects}
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scene_objects.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)
    print(f"\n✓ 原始数据已保存: {json_path}")

    # 生成 profile.yaml
    print("\n[3/3] 生成 profile.yaml...")
    profile = generate_profile(tables, containers, objects)
    profile_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profile.yaml")
    with open(profile_path, "w", encoding="utf-8") as f:
        yaml.dump(profile, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    print(f"✓ Profile 已保存: {profile_path}")

    # 复制到 FQPlanner
    fqplanner_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "master", "scene", "profile.yaml")
    fqplanner_path = os.path.normpath(fqplanner_path)
    try:
        with open(fqplanner_path, "w", encoding="utf-8") as f:
            yaml.dump(profile, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        print(f"✓ FQPlanner profile 已更新: {fqplanner_path}")
    except Exception as e:
        print(f"✗ 无法更新 FQPlanner profile: {e}")

    sys.stdout.flush()
    print("\n完成！")


def generate_profile(tables, containers, objects):
    """生成 profile.yaml 格式"""
    scene = []

    # 添加桌子
    for t in tables:
        entry = {
            "name": t["name"],
            "category": t["category"],
            "type": "table",
            "position": t["position"],
            "description": ZH_DESC.get(t["category"], t["category"]),
        }
        # 查找附近的物体
        nearby = []
        for o in objects:
            dx = t["position"][0] - o["position"][0]
            dy = t["position"][1] - o["position"][1]
            dist = (dx**2 + dy**2) ** 0.5
            if dist < 1.0:
                nearby.append(o["name"])
        if nearby:
            entry["contains"] = nearby
        scene.append(entry)

    # 添加容器
    for c in containers:
        scene.append({
            "name": c["name"],
            "category": c["category"],
            "type": "container",
            "position": c["position"],
            "description": ZH_DESC.get(c["category"], c["category"]),
        })

    # 添加独立物体
    for o in objects:
        scene.append({
            "name": o["name"],
            "category": o["category"],
            "type": "object",
            "position": o["position"],
            "description": ZH_DESC.get(o["category"], o["category"]),
        })

    # 添加固定位置
    scene.extend([
        {"name": "livingRoom", "type": "location", "position": [0.0, 0.0, 0.0], "description": "客厅"},
        {"name": "bedroom", "type": "location", "position": [-2.0, 2.0, 0.0], "description": "卧室"},
        {"name": "kitchen", "type": "location", "position": [2.0, 0.0, 0.0], "description": "厨房"},
        {"name": "bathroom", "type": "location", "position": [2.0, 2.0, 0.0], "description": "浴室"},
        {"name": "entrance", "type": "location", "position": [0.0, -2.0, 0.0], "description": "入口"},
    ])

    return {"scene": scene}


if __name__ == "__main__":
    main()
