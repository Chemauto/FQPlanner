#!/usr/bin/env python3
"""Export candidate navigable points from the generated Nav2 occupancy map."""

import argparse
import json
import math
import re
from pathlib import Path


def read_map_yaml(path):
    text = Path(path).read_text()
    image = re.search(r"^image:\s*(.+)$", text, re.M).group(1).strip()
    resolution = float(re.search(r"^resolution:\s*([-0-9.]+)$", text, re.M).group(1))
    origin_match = re.search(r"^origin:\s*\n-\s*([-0-9.]+)\n-\s*([-0-9.]+)", text, re.M)
    origin = (float(origin_match.group(1)), float(origin_match.group(2)))
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
        raise ValueError(f"Unsupported PGM max value: {max_value}")
    return width, height, data


def world_from_pixel(px, py, origin, resolution, height):
    x = origin[0] + (px + 0.5) * resolution
    y = origin[1] + height * resolution - (py + 0.5) * resolution
    return x, y


def distance_to_obstacle(px, py, occupied, resolution, max_cells):
    best = max_cells + 1
    for ox, oy in occupied:
        dx = abs(px - ox)
        dy = abs(py - oy)
        if dx > best or dy > best:
            continue
        dist = math.hypot(dx, dy)
        if dist < best:
            best = dist
    return best * resolution


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", default="maps/kitchen_map.yaml")
    parser.add_argument("--output", default="maps/free_points.json")
    parser.add_argument("--spacing", type=float, default=0.5)
    parser.add_argument("--clearance", type=float, default=0.35)
    args = parser.parse_args()

    image, resolution, origin = read_map_yaml(args.map)
    map_dir = Path(args.map).resolve().parent
    width, height, data = read_pgm(map_dir / image)

    occupied = [(i % width, i // width) for i, value in enumerate(data) if value < 128]
    step = max(1, round(args.spacing / resolution))
    max_cells = max(1, math.ceil(args.clearance / resolution))

    points = []
    for py in range(0, height, step):
        for px in range(0, width, step):
            if data[py * width + px] < 250:
                continue
            clearance = distance_to_obstacle(px, py, occupied, resolution, max_cells)
            if clearance < args.clearance:
                continue
            x, y = world_from_pixel(px, py, origin, resolution, height)
            points.append({
                "name": f"nav_{len(points):03d}",
                "x": round(x, 3),
                "y": round(y, 3),
                "clearance": round(clearance, 3),
            })

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "map": str(args.map),
        "spacing": args.spacing,
        "clearance": args.clearance,
        "points": points,
    }, indent=2))
    print(f"[free_points] exported {len(points)} points -> {output}")


if __name__ == "__main__":
    main()
