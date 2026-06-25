#!/usr/bin/env python3
"""Generate navigation operation objects from a single parameter table."""

from __future__ import annotations

import csv
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh
from scipy.cluster.vq import kmeans2


ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "tools/operation_object_parameters.csv"
SCENE_XML = ROOT / "assets/scene_3dgs/nav_scene_1/mjcf/scene.xml"
CONFIG_JSON = ROOT / "assets/scene_3dgs/config.json"
MESH_DIR = ROOT / "assets/scene_3dgs/nav_scene_1/meshes"

ASSET_BEGIN = "    <!-- BEGIN OPERATION_OBJECT_ASSETS -->"
ASSET_END = "    <!-- END OPERATION_OBJECT_ASSETS -->"
BODY_BEGIN = "    <!-- BEGIN OPERATION_OBJECT_BODIES -->"
BODY_END = "    <!-- END OPERATION_OBJECT_BODIES -->"

OLD_BLOCKS = (
    ("    <!-- BEGIN MULTIBODY_TOWEL_ASSETS -->", "    <!-- END MULTIBODY_TOWEL_ASSETS -->"),
    ("    <!-- BEGIN MULTIBODY_TOWEL_BODIES -->", "    <!-- END MULTIBODY_TOWEL_BODIES -->"),
    ("  <!-- BEGIN MULTIBODY_TOWEL_EQUALITY -->", "  <!-- END MULTIBODY_TOWEL_EQUALITY -->"),
    ("    <!-- BEGIN TOWEL_VARIANT_ASSETS -->", "    <!-- END TOWEL_VARIANT_ASSETS -->"),
    ("    <!-- BEGIN TOWEL_VARIANT_BODIES -->", "    <!-- END TOWEL_VARIANT_BODIES -->"),
    ("  <!-- BEGIN TOWEL_VARIANT_EQUALITY -->", "  <!-- END TOWEL_VARIANT_EQUALITY -->"),
    (ASSET_BEGIN, ASSET_END),
    (BODY_BEGIN, BODY_END),
)


@dataclass(frozen=True)
class ObjectSpec:
    name: str
    link: str
    source_mesh: Path
    asset_file: Path
    target_size: np.ndarray
    mass: float
    collision_mode: str
    collision_parts: int
    seed: int
    body_pos: str
    body_quat: str
    body_euler_deg: str
    friction: str
    solref: str
    solimp: str
    material_rgba: str


def parse_vec(text: str, expected: int, field_name: str) -> np.ndarray:
    values = np.asarray([float(x) for x in text.split()], dtype=float)
    if values.shape != (expected,):
        raise ValueError(f"{field_name} should have {expected} values, got: {text}")
    return values


def resolve_path(path_text: str) -> Path:
    path = Path(path_text).expanduser()
    if path.is_absolute():
        return path
    return ROOT / path


def read_table(path: Path = TABLE) -> list[ObjectSpec]:
    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    specs: list[ObjectSpec] = []
    for row in csv.DictReader(lines):
        if row.get("enabled", "1").strip() not in {"1", "true", "True", "yes"}:
            continue
        specs.append(
            ObjectSpec(
                name=row["name"].strip(),
                link=row["link"].strip(),
                source_mesh=resolve_path(row["source_mesh"].strip()),
                asset_file=Path(row["asset_file"].strip()),
                target_size=parse_vec(row["target_size_m"], 3, "target_size_m"),
                mass=float(row["mass_kg"]),
                collision_mode=row["collision_mode"].strip(),
                collision_parts=int(row["collision_parts"]),
                seed=int(row["seed"]),
                body_pos=row["body_pos"].strip(),
                body_quat=row["body_quat"].strip(),
                body_euler_deg=row["body_euler_deg"].strip(),
                friction=row["friction"].strip(),
                solref=row["solref"].strip(),
                solimp=row["solimp"].strip(),
                material_rgba=row["material_rgba"].strip(),
            )
        )
    return specs


def load_mesh(path: Path) -> trimesh.Trimesh:
    loaded = trimesh.load(path, force="scene", process=False)
    if isinstance(loaded, trimesh.Trimesh):
        mesh = loaded
    else:
        geoms = [geom.copy() for geom in loaded.geometry.values()]
        if not geoms:
            raise ValueError(f"mesh has no geometry: {path}")
        mesh = trimesh.util.concatenate(geoms) if len(geoms) > 1 else geoms[0]
    if len(mesh.faces) == 0:
        raise ValueError(f"mesh has no faces: {path}")
    return mesh


def copy_visual_asset(spec: ObjectSpec) -> Path:
    dest = MESH_DIR / spec.asset_file
    dest.parent.mkdir(parents=True, exist_ok=True)
    if spec.source_mesh.resolve() != dest.resolve():
        shutil.copy2(spec.source_mesh, dest)
        if spec.source_mesh.suffix.lower() == ".obj":
            for sidecar in spec.source_mesh.parent.iterdir():
                if sidecar.suffix.lower() in {".mtl", ".png", ".jpg", ".jpeg"}:
                    shutil.copy2(sidecar, dest.parent / sidecar.name)
    return dest


def visual_mesh_name(spec: ObjectSpec) -> str:
    return "hunyuan_bag_visual" if spec.name == "bag" else f"hunyuan_{spec.name}"


def material_name(spec: ObjectSpec) -> str:
    return f"hunyuan_{spec.name}_mat"


def scale_for(mesh: trimesh.Trimesh, target_size: np.ndarray) -> np.ndarray:
    extents = np.maximum(mesh.extents.astype(float), 1e-8)
    return target_size / extents


def fmt_vec(values: np.ndarray) -> str:
    return " ".join(f"{float(v):.6f}" for v in values)


def box_inertia(mass: float, size: np.ndarray) -> tuple[float, float, float]:
    sx, sy, sz = [float(v) for v in size]
    ixx = mass * (sy * sy + sz * sz) / 12.0
    iyy = mass * (sx * sx + sz * sz) / 12.0
    izz = mass * (sx * sx + sy * sy) / 12.0
    return max(ixx, 1e-7), max(iyy, 1e-7), max(izz, 1e-7)


def export_convex_parts(spec: ObjectSpec, mesh: trimesh.Trimesh) -> list[Path]:
    part_count = int(spec.collision_parts)
    out_dir = MESH_DIR / f"hunyuan3d/{spec.name}/collision_parts"
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob(f"{spec.name}_part_*.obj"):
        old.unlink()

    centroids = mesh.triangles_center
    extents = np.maximum(mesh.extents, 1e-8)
    features = (centroids - mesh.bounds[0]) / extents

    best_paths: list[Path] = []
    for attempt in range(8):
        np.random.seed(spec.seed + attempt)
        _, labels = kmeans2(features, part_count, minit="points", iter=100)

        paths: list[Path] = []
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
            except Exception:
                continue
            if hull.is_empty or len(hull.faces) == 0:
                continue
            path = out_dir / f"{spec.name}_part_{len(paths):02d}.obj"
            hull.export(path)
            paths.append(path)

        if len(paths) == part_count:
            return paths
        if len(paths) > len(best_paths):
            best_paths = paths

    raise RuntimeError(
        f"{spec.name}: expected {part_count} collision parts, generated {len(best_paths)}"
    )


def asset_lines(specs: list[ObjectSpec], meshes: dict[str, trimesh.Trimesh]) -> list[str]:
    lines = [ASSET_BEGIN]
    for spec in specs:
        mesh = meshes[spec.name]
        scale = scale_for(mesh, spec.target_size)
        if spec.name == "maojin":
            lines.append(
                '    <texture name="hunyuan_maojin_tex" type="2d" '
                'file="../../towel_multibody_demo/visual/texture_pbr_20250901_roughness.png" />'
            )
            lines.append(
                f'    <material name="{material_name(spec)}" texture="hunyuan_maojin_tex" '
                f'texrepeat="1 1" rgba="{spec.material_rgba}" roughness="0.75" />'
            )
        else:
            lines.append(
                f'    <material name="{material_name(spec)}" rgba="{spec.material_rgba}" roughness="0.80" />'
            )
        lines.append(
            f'    <mesh name="{visual_mesh_name(spec)}" file="{spec.asset_file.as_posix()}" '
            f'scale="{fmt_vec(scale)}" />'
        )
        if spec.collision_mode == "convex_parts":
            for idx in range(spec.collision_parts):
                part_file = f"hunyuan3d/{spec.name}/collision_parts/{spec.name}_part_{idx:02d}.obj"
                lines.append(
                    f'    <mesh name="hunyuan_{spec.name}_part_{idx:02d}" file="{part_file}" '
                    f'scale="{fmt_vec(scale)}" />'
                )
    lines.append(ASSET_END)
    return lines


def body_lines(specs: list[ObjectSpec]) -> list[str]:
    lines = [BODY_BEGIN]
    for spec in specs:
        orientation = (
            f'quat="{spec.body_quat}"'
            if spec.body_quat
            else f'euler="{spec.body_euler_deg}"'
            if spec.body_euler_deg
            else ""
        )
        ixx, iyy, izz = box_inertia(spec.mass, spec.target_size)
        lines.extend(
            [
                f'    <body name="{spec.link}" pos="{spec.body_pos}" {orientation}>',
                f'      <joint name="{spec.link}_freejoint" type="free" />',
                f'      <inertial pos="0 0 0" mass="{spec.mass:.6f}" '
                f'diaginertia="{ixx:.8f} {iyy:.8f} {izz:.8f}" />',
                f'      <geom name="{spec.link}_visual" type="mesh" mesh="{visual_mesh_name(spec)}" '
                f'material="{material_name(spec)}" group="2" contype="0" conaffinity="0" />',
            ]
        )

        if spec.collision_mode == "convex_parts":
            for idx in range(spec.collision_parts):
                lines.append(
                    f'      <geom name="{spec.link}_part_{idx:02d}_collision" type="mesh" '
                    f'mesh="hunyuan_{spec.name}_part_{idx:02d}" group="3" rgba="0 1 0 0" '
                    f'contype="1" conaffinity="1" friction="{spec.friction}" '
                    f'solref="{spec.solref}" solimp="{spec.solimp}" />'
                )
        elif spec.collision_mode == "box":
            half = spec.target_size / 2.0
            lines.append(
                f'      <geom name="{spec.link}_collision" type="box" size="{fmt_vec(half)}" '
                f'group="3" rgba="0 1 0 0" contype="1" conaffinity="1" '
                f'friction="{spec.friction}" solref="{spec.solref}" solimp="{spec.solimp}" />'
            )
        elif spec.collision_mode == "mesh":
            lines.append(
                f'      <geom name="{spec.link}_collision" type="mesh" mesh="{visual_mesh_name(spec)}" '
                f'group="3" rgba="0 1 0 0" contype="1" conaffinity="1" '
                f'friction="{spec.friction}" solref="{spec.solref}" solimp="{spec.solimp}" />'
            )
        else:
            raise ValueError(f"unsupported collision_mode for {spec.name}: {spec.collision_mode}")

        lines.append("    </body>")
    lines.append(BODY_END)
    return lines


def strip_block(text: str, begin: str, end: str) -> str:
    return re.sub(rf"\n{re.escape(begin)}.*?{re.escape(end)}\n", "\n", text, flags=re.DOTALL)


def remove_body(text: str, name: str) -> str:
    return re.sub(rf'\n    <body name="{re.escape(name)}".*?\n    </body>\n', "\n", text, flags=re.DOTALL)


def remove_asset_name(text: str, name: str) -> str:
    return re.sub(
        rf'\n    <(?:mesh|material|texture) name="{re.escape(name)}"[^>]* />',
        "",
        text,
    )


def update_scene(specs: list[ObjectSpec], meshes: dict[str, trimesh.Trimesh]) -> None:
    text = SCENE_XML.read_text(encoding="utf-8")
    for begin, end in OLD_BLOCKS:
        text = strip_block(text, begin, end)

    stale_body_names = {
        "hunyuan_maojin_grid_body",
        "hunyuan_maojin_strip_body",
        "hunyuan_maojin_grid_support_cube",
        "hunyuan_maojin_strip_support_cube",
        "hunyuan_bag_drop_ball_body",
    }
    stale_body_names.update(spec.link for spec in specs)
    for body_name in sorted(stale_body_names):
        text = remove_body(text, body_name)

    stale_asset_names = {"hunyuan_maojin_tex"}
    for spec in specs:
        stale_asset_names.add(visual_mesh_name(spec))
        stale_asset_names.add(material_name(spec))
        for idx in range(max(spec.collision_parts, 1)):
            stale_asset_names.add(f"hunyuan_{spec.name}_part_{idx:02d}")
    for asset_name in sorted(stale_asset_names):
        text = remove_asset_name(text, asset_name)

    assets = "\n".join(asset_lines(specs, meshes))
    bodies = "\n".join(body_lines(specs))
    text = text.replace("  </asset>", f"{assets}\n  </asset>", 1)
    text = text.replace("  </worldbody>", f"{bodies}\n  </worldbody>", 1)
    SCENE_XML.write_text(text, encoding="utf-8")


def update_config(specs: list[ObjectSpec]) -> None:
    cfg = json.loads(CONFIG_JSON.read_text(encoding="utf-8"))
    cfg["objects"] = [{"name": spec.name, "link": spec.link} for spec in specs]
    cfg["composite_mesh_objects"] = [{"link": spec.link} for spec in specs]
    CONFIG_JSON.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    specs = read_table()
    meshes: dict[str, trimesh.Trimesh] = {}
    generated_counts: dict[str, int] = {}

    for spec in specs:
        copy_visual_asset(spec)
        mesh = load_mesh(spec.source_mesh)
        meshes[spec.name] = mesh
        if spec.collision_mode == "convex_parts":
            parts = export_convex_parts(spec, mesh)
            generated_counts[spec.name] = len(parts)

    update_scene(specs, meshes)
    update_config(specs)

    print(f"Read parameter table: {TABLE}")
    for spec in specs:
        raw = meshes[spec.name].extents
        scale = scale_for(meshes[spec.name], spec.target_size)
        pieces = generated_counts.get(spec.name, spec.collision_parts)
        print(
            f"{spec.name}: target={fmt_vec(spec.target_size)} m, "
            f"raw={fmt_vec(raw)} scale={fmt_vec(scale)}, "
            f"collision={spec.collision_mode}({pieces})"
        )
    print(f"Updated scene: {SCENE_XML}")
    print(f"Updated config: {CONFIG_JSON}")


if __name__ == "__main__":
    main()
