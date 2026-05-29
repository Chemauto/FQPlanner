#!/usr/bin/env python3
"""Check whether world points fall on free cells in the Nav2 map."""

import argparse
import re
from pathlib import Path


def read_map_yaml(path):
    text = Path(path).read_text()
    image = re.search(r"^image:\s*(.+)$", text, re.M).group(1).strip()
    resolution = float(re.search(r"^resolution:\s*([-0-9.]+)$", text, re.M).group(1))
    origin_block = re.search(r"^origin:\s*\n-\s*([-0-9.]+)\n-\s*([-0-9.]+)", text, re.M)
    origin = (float(origin_block.group(1)), float(origin_block.group(2)))
    return image, resolution, origin


def read_pgm(path):
    with Path(path).open("rb") as f:
        if f.readline().strip() != b"P5":
            raise ValueError("Only binary PGM (P5) is supported")
        line = f.readline()
        while line.startswith(b"#"):
            line = f.readline()
        width, height = map(int, line.split())
        max_value = int(f.readline())
        data = f.read()
    if max_value != 255:
        raise ValueError(f"Unsupported max value: {max_value}")
    return width, height, data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("points", nargs="+", help="World points as x,y")
    parser.add_argument("--map", default="maps/kitchen_map.yaml")
    args = parser.parse_args()

    image, resolution, origin = read_map_yaml(args.map)
    map_dir = Path(args.map).resolve().parent
    width, height, data = read_pgm(map_dir / image)
    print(f"map range x=[{origin[0]:.2f}, {origin[0] + width * resolution:.2f}] "
          f"y=[{origin[1]:.2f}, {origin[1] + height * resolution:.2f}]")

    for point in args.points:
        x_text, y_text = point.split(",", 1)
        x, y = float(x_text), float(y_text)
        px = int((x - origin[0]) / resolution)
        py = int((origin[1] + height * resolution - y) / resolution)
        if not (0 <= px < width and 0 <= py < height):
            print(f"{point}: outside map, pixel=({px}, {py})")
            continue
        value = data[py * width + px]
        state = "free" if value >= 250 else "occupied/unknown"
        print(f"{point}: {state}, pixel=({px}, {py}), value={value}")


if __name__ == "__main__":
    main()
