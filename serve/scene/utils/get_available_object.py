"""
查询当前 objects.yaml 中配置的本地 MuJoCo 对象。
"""

import argparse
import os

import yaml


def load_objects():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "config", "objects.yaml")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("objects", [])


def main():
    parser = argparse.ArgumentParser(description="查询当前场景可用物体")
    parser.add_argument("--names-only", action="store_true")
    args = parser.parse_args()

    objects = load_objects()
    for obj in objects:
        if args.names_only:
            print(obj.get("name", ""))
        else:
            print(f"{obj.get('name', ''):<20s} {obj.get('obj_groups', '')}")


if __name__ == "__main__":
    main()

