#!/usr/bin/env python3
"""Prepare a MuJoCo validation scene for a Hunyuan3D bag mesh.

The source mesh is used as a visual mesh. Collision is approximated by splitting
faces into spatial clusters and building one convex hull per cluster.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import numpy as np
import trimesh
from scipy.cluster.vq import kmeans2


DEFAULT_SOURCE = Path(
    "/home/dw/gs_playground/hunyuan3D/bag/287c09edd9d4025dc609b20e451bec13"
)
DEFAULT_OUT = Path("assets/scene_3dgs/bag_convex_demo")


def load_mesh(path: Path) -> trimesh.Trimesh:
    mesh = trimesh.load(path, force="mesh", process=False)
    if not isinstance(mesh, trimesh.Trimesh):
        raise TypeError(f"Expected a mesh, got {type(mesh)!r}")
    if len(mesh.faces) == 0:
        raise ValueError(f"Mesh has no faces: {path}")
    return mesh


def copy_visual_assets(source_dir: Path, out_dir: Path) -> Path:
    visual_dir = out_dir / "visual"
    visual_dir.mkdir(parents=True, exist_ok=True)
    for name in [
        "5778521f0eabef128c97d8ba866f96c7.obj",
        "material.mtl",
        "texture_pbr_20250901.png",
        "texture_pbr_20250901_metallic.png",
        "texture_pbr_20250901_normal.png",
        "texture_pbr_20250901_roughness.png",
    ]:
        src = source_dir / name
        if src.exists():
            shutil.copy2(src, visual_dir / name)
    return visual_dir / "5778521f0eabef128c97d8ba866f96c7.obj"


def export_convex_parts(
    mesh: trimesh.Trimesh,
    out_dir: Path,
    part_count: int,
    seed: int,
) -> list[Path]:
    collision_dir = out_dir / "collision_parts"
    collision_dir.mkdir(parents=True, exist_ok=True)
    for old in collision_dir.glob("bag_part_*.obj"):
        old.unlink()

    centroids = mesh.triangles_center
    extents = np.maximum(mesh.extents, 1e-6)
    features = (centroids - mesh.bounds[0]) / extents

    np.random.seed(seed)
    _, labels = kmeans2(features, part_count, minit="points", iter=80)

    part_paths: list[Path] = []
    for idx in range(part_count):
        face_ids = np.flatnonzero(labels == idx)
        if len(face_ids) < 4:
            continue
        vertex_ids = np.unique(mesh.faces[face_ids].reshape(-1))
        points = mesh.vertices[vertex_ids]
        if len(points) < 4:
            continue
        try:
            hull = trimesh.Trimesh(vertices=points, process=True).convex_hull
        except Exception as exc:
            print(f"[warn] skip part {idx}: convex hull failed: {exc}")
            continue
        if hull.is_empty or len(hull.faces) == 0:
            continue
        path = collision_dir / f"bag_part_{len(part_paths):02d}.obj"
        hull.export(path)
        part_paths.append(path)

    return part_paths


def write_mujoco_scene(
    out_dir: Path,
    visual_obj: Path,
    part_paths: list[Path],
    scale: float,
) -> Path:
    xml_path = out_dir / "bag_drop_test.xml"
    rel_visual = visual_obj.relative_to(out_dir).as_posix()

    mesh_assets = [
        f'    <mesh name="bag_visual_mesh" file="{rel_visual}" scale="{scale} {scale} {scale}" />'
    ]
    for part in part_paths:
        rel = part.relative_to(out_dir).as_posix()
        mesh_assets.append(
            f'    <mesh name="{part.stem}" file="{rel}" scale="{scale} {scale} {scale}" />'
        )

    collision_geoms = []
    for part in part_paths:
        collision_geoms.append(
            f'      <geom name="{part.stem}_collision" type="mesh" mesh="{part.stem}" '
            'rgba="0.1 0.8 0.1 0.22" contype="1" conaffinity="1" '
            'friction="0.8 0.05 0.01" />'
        )

    xml = f'''<mujoco model="bag_convex_drop_test">
  <compiler angle="degree" meshdir="." autolimits="true" />
  <option timestep="0.002" gravity="0 0 -9.81" integrator="implicit" />

  <asset>
    <texture name="grid" type="2d" builtin="checker" rgb1="0.18 0.18 0.18" rgb2="0.28 0.28 0.28" width="512" height="512" />
    <material name="floor_mat" texture="grid" texrepeat="4 4" reflectance="0.15" />
    <material name="bag_mat" rgba="0.85 0.62 0.36 1" />
    <material name="ball_mat" rgba="0.95 0.15 0.12 1" />
{chr(10).join(mesh_assets)}
  </asset>

  <worldbody>
    <light name="key" pos="0 -3 4" dir="0 1 -1" diffuse="0.9 0.9 0.9" />
    <camera name="overview" pos="0 -3.2 1.8" xyaxes="1 0 0 0 0.45 0.89" />
    <geom name="floor" type="plane" size="2 2 0.05" material="floor_mat" contype="1" conaffinity="1" />

    <body name="bag" pos="0 0 0.005" euler="90 0 0">
      <freejoint name="bag_freejoint" />
      <inertial pos="0 0 0.08" mass="0.15" diaginertia="0.01 0.01 0.01" />
      <geom name="bag_visual" type="mesh" mesh="bag_visual_mesh" material="bag_mat" contype="0" conaffinity="0" group="2" />
{chr(10).join(collision_geoms)}
    </body>

    <body name="drop_ball" pos="0 0 0.65">
      <freejoint name="drop_ball_freejoint" />
      <geom name="drop_ball_geom" type="sphere" size="0.055" mass="0.08" material="ball_mat" contype="1" conaffinity="1" friction="0.7 0.02 0.01" />
    </body>
  </worldbody>
</mujoco>
'''
    xml_path.write_text(xml, encoding="utf-8")
    return xml_path


def write_readme(out_dir: Path, source_obj: Path, part_paths: list[Path], scale: float) -> None:
    readme = f"""# Bag Convex Collision Demo

Generated from:

`{source_obj}`

Outputs:

- `visual/`: original textured OBJ assets.
- `collision_parts/`: {len(part_paths)} convex hull OBJ files.
- `bag_drop_test.xml`: MuJoCo scene where a ball drops onto the bag.

The visual mesh and collision parts currently use `scale="{scale} {scale} {scale}"`.
Measure the real bag and adjust this scale before using the object in the main scene.
"""
    (out_dir / "README.md").write_text(readme, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--parts", type=int, default=20)
    parser.add_argument("--scale", type=float, default=0.25)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    source_obj = args.source_dir / "5778521f0eabef128c97d8ba866f96c7.obj"
    mesh = load_mesh(source_obj)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    visual_obj = copy_visual_assets(args.source_dir, args.out_dir)
    part_paths = export_convex_parts(mesh, args.out_dir, args.parts, args.seed)
    if not part_paths:
        raise RuntimeError("No convex collision parts were generated")

    xml_path = write_mujoco_scene(args.out_dir, visual_obj, part_paths, args.scale)
    write_readme(args.out_dir, source_obj, part_paths, args.scale)

    print(f"source vertices={len(mesh.vertices)} faces={len(mesh.faces)}")
    print(f"source bounds={mesh.bounds.tolist()}")
    print(f"source extents={mesh.extents.tolist()}")
    print(f"generated parts={len(part_paths)}")
    print(f"scene={xml_path}")


if __name__ == "__main__":
    main()
