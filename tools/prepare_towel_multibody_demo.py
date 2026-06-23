#!/usr/bin/env python3
"""Prepare a MuJoCo soft-cloth towel and convex-bag validation scene.

This version uses MuJoCo's native flex system with the
`mujoco.elasticity.shell` plugin. Gravity and contact are enabled. One dynamic
ball drops onto the cloth, and another drops onto the convex-decomposed bag.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import trimesh


DEFAULT_SOURCE = Path(
    "/home/dw/gs_playground/hunyuan3D/maojin/c5492efea47170a1ea6e0349128e67af"
)
DEFAULT_REF_IMAGE = Path("/home/dw/gs_playground/hunyuan3D/maojin/maojin.png")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = PROJECT_ROOT / "assets/scene_3dgs/towel_multibody_demo"
DEFAULT_BAG_DEMO = PROJECT_ROOT / "assets/scene_3dgs/bag_convex_demo"


def load_mesh(path: Path) -> trimesh.Trimesh:
    mesh = trimesh.load(path, force="mesh", process=False)
    if not isinstance(mesh, trimesh.Trimesh):
        raise TypeError(f"Expected a mesh, got {type(mesh)!r}")
    if len(mesh.faces) == 0:
        raise ValueError(f"Mesh has no faces: {path}")
    return mesh


def copy_source_assets(source_dir: Path, out_dir: Path, ref_image: Path | None) -> Path:
    visual_dir = out_dir / "visual"
    visual_dir.mkdir(parents=True, exist_ok=True)
    for src in source_dir.iterdir():
        if src.is_file() and src.suffix.lower() in {".obj", ".mtl", ".png", ".jpg", ".jpeg"}:
            shutil.copy2(src, visual_dir / src.name)
    if ref_image and ref_image.exists():
        shutil.copy2(ref_image, out_dir / ref_image.name)
    objs = sorted(visual_dir.glob("*.obj"))
    if not objs:
        raise FileNotFoundError(f"No OBJ copied from {source_dir}")
    return objs[0]


def copy_bag_demo_assets(bag_demo_dir: Path, out_dir: Path) -> tuple[Path, list[Path]]:
    bag_dir = out_dir / "bag_convex"
    visual_dir = bag_dir / "visual"
    collision_dir = bag_dir / "collision_parts"
    visual_dir.mkdir(parents=True, exist_ok=True)
    collision_dir.mkdir(parents=True, exist_ok=True)

    source_visual_dir = bag_demo_dir / "visual"
    source_collision_dir = bag_demo_dir / "collision_parts"
    if not source_visual_dir.exists() or not source_collision_dir.exists():
        raise FileNotFoundError(
            f"Bag demo assets are missing. Expected {source_visual_dir} and {source_collision_dir}"
        )

    for src in source_visual_dir.iterdir():
        if src.is_file():
            shutil.copy2(src, visual_dir / src.name)
    for src in source_collision_dir.glob("bag_part_*.obj"):
        shutil.copy2(src, collision_dir / src.name)

    visual_objs = sorted(visual_dir.glob("*.obj"))
    part_paths = sorted(collision_dir.glob("bag_part_*.obj"))
    if not visual_objs:
        raise FileNotFoundError(f"No bag visual OBJ copied from {source_visual_dir}")
    if not part_paths:
        raise FileNotFoundError(f"No bag collision parts copied from {source_collision_dir}")
    return visual_objs[0], part_paths


def bag_asset_xml(out_dir: Path, bag_visual_obj: Path, bag_part_paths: list[Path], scale: float) -> str:
    lines = [
        (
            '    <mesh name="bag_visual_mesh" '
            f'file="{bag_visual_obj.relative_to(out_dir).as_posix()}" '
            f'scale="{scale} {scale} {scale}" />'
        )
    ]
    for part in bag_part_paths:
        lines.append(
            f'    <mesh name="{part.stem}" file="{part.relative_to(out_dir).as_posix()}" '
            f'scale="{scale} {scale} {scale}" />'
        )
    return "\n".join(lines)


def bag_collision_geom_xml(bag_part_paths: list[Path]) -> str:
    lines = []
    for part in bag_part_paths:
        lines.append(
            f'      <geom name="{part.stem}_collision" type="mesh" mesh="{part.stem}" '
            'rgba="0.1 0.8 0.1 0.22" contype="1" conaffinity="1" '
            'friction="0.8 0.05 0.01" />'
        )
    return "\n".join(lines)


def write_mujoco_scene(
    out_dir: Path,
    visual_obj: Path,
    bag_visual_obj: Path,
    bag_part_paths: list[Path],
    cols: int,
    rows: int,
    scale: float,
    bag_scale: float,
    length: float,
    width: float,
    mass: float,
    young: float,
    damping: float,
    thickness: float,
    radius: float,
    skin_inflate: float,
    skin_subgrid: int,
    edge_equality: bool,
    elastic2d: str,
) -> Path:
    soft_xml = out_dir / "towel_softcloth_drop_test.xml"
    flex_compat_xml = out_dir / "towel_flex_drop_test.xml"
    grid_compat_xml = out_dir / "towel_grid_drop_test.xml"
    chain_compat_xml = out_dir / "towel_chain_drop_test.xml"
    physics_compat_xml = out_dir / "towel_physics_drop_test.xml"

    rel_visual = visual_obj.relative_to(out_dir).as_posix()
    towel_texture = out_dir / "visual" / "texture_pbr_20250901_roughness.png"
    towel_texture_xml = ""
    towel_material_texture = ""
    if towel_texture.exists():
        towel_texture_xml = (
            '    <texture name="towel_tex" type="2d" '
            f'file="{towel_texture.relative_to(out_dir).as_posix()}" />\n'
        )
        towel_material_texture = ' texture="towel_tex" texrepeat="1 1"'
    spacing_x = length / max(cols - 1, 1)
    spacing_y = width / max(rows - 1, 1)
    cloth_z = 0.22
    ball_z = 0.42
    bag_x = 0.70
    bag_ball_z = 0.68

    edge_xml = ""
    if edge_equality:
        edge_xml = (
            "\n"
            '      <edge equality="true" solref="0.006 1" '
            'solimp="0.95 0.995 0.0005" />'
        )

    plugin_xml = ""
    if elastic2d == "bend":
        plugin_xml = f'''
      <plugin plugin="mujoco.elasticity.shell">
        <config key="young" value="{young:.6g}" />
        <config key="poisson" value="0.30" />
        <config key="thickness" value="{thickness:.6g}" />
        <config key="damping" value="{damping:.6g}" />
      </plugin>'''
    elif elastic2d != "none":
        raise ValueError(f"Unsupported --elastic2d mode: {elastic2d}")

    bag_mesh_assets = bag_asset_xml(out_dir, bag_visual_obj, bag_part_paths, bag_scale)
    bag_collision_geoms = bag_collision_geom_xml(bag_part_paths)

    xml = f'''<mujoco model="towel_softcloth_drop_test">
  <compiler angle="degree" meshdir="." autolimits="true" />
  <option timestep="0.001" gravity="0 0 -9.81" integrator="implicit" iterations="100" tolerance="1e-10" />
  <extension>
    <plugin plugin="mujoco.elasticity.shell" />
  </extension>

  <asset>
    <texture name="grid" type="2d" builtin="checker" rgb1="0.18 0.18 0.18" rgb2="0.28 0.28 0.28" width="512" height="512" />
{towel_texture_xml.rstrip()}
    <material name="floor_mat" texture="grid" texrepeat="4 4" reflectance="0.15" />
    <material name="towel_mat"{towel_material_texture} rgba="0.72 0.72 0.68 1" roughness="0.75" />
    <material name="towel_ref_mat" rgba="0.78 0.78 0.74 0.38" />
    <material name="clamp_mat" rgba="0.16 0.18 0.20 1" />
    <material name="ball_mat" rgba="0.95 0.18 0.12 1" />
    <material name="bag_mat" rgba="0.85 0.62 0.36 1" />
    <mesh name="towel_full_visual" file="{rel_visual}" scale="{scale} {scale} {scale}" />
{bag_mesh_assets}
  </asset>

  <worldbody>
    <light name="key" pos="0 -3 4" dir="0 1 -1" diffuse="0.9 0.9 0.9" />
    <camera name="overview" pos="0.35 -2.3 1.15" xyaxes="1 0 0 0 0.45 0.89" />
    <geom name="floor" type="plane" size="2.5 2.5 0.05" material="floor_mat" friction="1.0 0.05 0.01" />

    <!-- Actual soft towel cloth. Gravity and contacts are enabled; no edge is pinned. -->
    <flexcomp name="towel" type="grid" dim="2"
              count="{cols} {rows} 1"
              spacing="{spacing_x:.6f} {spacing_y:.6f} 0.020"
              pos="0 0 {cloth_z:.6f}"
              mass="{mass:.6f}"
              radius="{radius:.6f}"
              material="towel_mat"
              flatskin="false"
              rgba="0.72 0.72 0.68 1">{edge_xml}{plugin_xml}
    </flexcomp>

    <!-- Hunyuan3D visual reference, not used for collision. -->
    <body name="reference_full_towel_visual" pos="0 0.50 0.09" euler="90 0 0">
      <geom name="reference_full_towel_visual_geom" type="mesh" mesh="towel_full_visual" material="towel_ref_mat" contype="0" conaffinity="0" group="2" />
    </body>

    <body name="towel_drop_ball" pos="0.05 0 {ball_z:.6f}">
      <freejoint name="towel_drop_ball_freejoint" />
      <geom name="towel_drop_ball_geom" type="sphere" size="0.030" mass="0.010" material="ball_mat" friction="0.7 0.02 0.01" solref="0.02 1" solimp="0.8 0.95 0.001" />
    </body>

    <!-- Convex-decomposed bag collision test, copied from bag_convex_demo. -->
    <body name="bag" pos="{bag_x:.6f} 0 0.005" euler="90 0 0">
      <freejoint name="bag_freejoint" />
      <inertial pos="0 0 0.08" mass="0.15" diaginertia="0.01 0.01 0.01" />
      <geom name="bag_visual" type="mesh" mesh="bag_visual_mesh" material="bag_mat" contype="0" conaffinity="0" group="2" />
{bag_collision_geoms}
    </body>

    <body name="bag_drop_ball" pos="{bag_x:.6f} 0 {bag_ball_z:.6f}">
      <freejoint name="bag_drop_ball_freejoint" />
      <geom name="bag_drop_ball_geom" type="sphere" size="0.055" mass="0.08" material="ball_mat" contype="1" conaffinity="1" friction="0.7 0.02 0.01" />
    </body>
  </worldbody>
</mujoco>
'''

    for path in (soft_xml, flex_compat_xml, grid_compat_xml, chain_compat_xml, physics_compat_xml):
        path.write_text(xml, encoding="utf-8")
    return soft_xml


def write_readme(
    out_dir: Path,
    source_obj: Path,
    cols: int,
    rows: int,
    scale: float,
    length: float,
    width: float,
    bag_scale: float,
    bag_parts: int,
    mass: float,
    young: float,
    damping: float,
    thickness: float,
    radius: float,
    skin_inflate: float,
    skin_subgrid: int,
    edge_equality: bool,
    elastic2d: str,
) -> None:
    readme = f"""# 浴巾 Soft-Cloth Demo

生成来源：

`{source_obj}`

输出内容：

- `visual/`：从 Hunyuan3D 毛巾源目录复制过来的 OBJ、MTL 和贴图文件。
- `bag_convex/`：从 `bag_convex_demo` 复制过来的 bag visual mesh 和 convex collision parts。
- `towel_softcloth_drop_test.xml`：主要的 MuJoCo 柔性布料验证场景。
- `towel_flex_drop_test.xml`、`towel_grid_drop_test.xml`、`towel_chain_drop_test.xml`、`towel_physics_drop_test.xml`：与主场景内容一致的兼容文件。
- `maojin.png`：从源目录复制过来的参考图。

建模方式：

- 实际参与仿真的浴巾是 MuJoCo `flexcomp type="grid"`，并启用 `mujoco.elasticity.shell`。
- 重力和接触碰撞都已开启。
- 浴巾当前没有任何一侧固定，所有 flex 节点都会在重力和接触作用下自由运动。
- 红色小球会自由下落到布料上，用来观察布料弯曲、拉伸和接触稳定性。
- 场景右侧加入了之前完成的 bag 凹面物体分解碰撞测试：bag 使用 `{bag_parts}` 个 convex collision parts，一个较大的红色小球从 bag 正上方落下。
- Hunyuan3D OBJ 保留为视觉参考，不参与碰撞计算。
- `flexcomp` 已绑定 `towel_mat`，使用 `visual/texture_pbr_20250901_roughness.png` 作为贴图；在 MuJoCo 3.3.1 中，给 flex 指定 material 后会自动生成 texture coordinates。
- 当前 `robocasa` 环境的 MuJoCo 3.3.1 不接受 `flexcomp` 内的 `<skin>` 子标签，也不接受 `subgrid` 和 `inflate` 属性，所以这里没有把它们写进 XML；视觉平滑主要通过 `flatskin="false"` 和贴图完成，真实接触厚度仍由 `radius` 和 shell `thickness` 控制。

当前参数：

- flex 分辨率：`{cols} x {rows}` 顶点
- towel length：`{length}`
- towel width：`{width}`
- 视觉 mesh 缩放：`{scale}`
- bag mesh 缩放：`{bag_scale}`
- bag convex parts：`{bag_parts}`
- towel mass：`{mass}`
- shell young：`{young}`
- shell damping：`{damping}`
- shell thickness：`{thickness}`
- flex contact radius：`{radius}`
- 建议 skin subgrid：`{skin_subgrid}`，当前 MuJoCo 3.3.1 XML schema 不支持写入
- 建议 skin inflate：`{skin_inflate}`，当前 MuJoCo 3.3.1 XML schema 不支持写入
- all-edge equality constraint：`{edge_equality}`
- 2D elasticity mode：`{elastic2d}`

说明：`edge equality` 现在默认开启，用来抑制毛巾被随意拉长；如果需要做拉伸对照测试，可以在生成命令中显式加入 `--no-edge-equality`。

重新生成场景：

```bash
cd /home/dw/RoboOS_Agent/FQPlanner
conda activate robocasa
python tools/prepare_towel_multibody_demo.py \\
  --young 5e4 \\
  --damping 0.4 \\
  --thickness 0.01 \\
  --radius 0.003 \\
  --bag-scale 0.5 \\
  --edge-equality \\
  --elastic2d bend
```

打开 MuJoCo viewer 测试：

```bash
cd /home/dw/RoboOS_Agent/FQPlanner
conda activate robocasa
python -c "import mujoco.viewer; mujoco.viewer.launch_from_path('assets/scene_3dgs/towel_multibody_demo/towel_softcloth_drop_test.xml')"
```
"""
    (out_dir / "README.md").write_text(readme, encoding="utf-8")


def write_source_readme(
    source_dir: Path,
    out_dir: Path,
    length: float,
    width: float,
    young: float,
    damping: float,
    thickness: float,
    radius: float,
    skin_inflate: float,
    skin_subgrid: int,
    bag_scale: float,
    bag_parts: int,
    edge_equality: bool,
    elastic2d: str,
) -> None:
    readme_path = source_dir.parent / "README_towel_softcloth.md"
    readme = f"""# 毛巾 Soft-Cloth 调参记录

该目录保存 Hunyuan3D 毛巾源资产和当前 MuJoCo 柔性布料测试记录。由这些资产生成的验证场景是：

`{out_dir / "towel_softcloth_drop_test.xml"}`

当前生成参数：

- `young`: `{young}`
- `damping`: `{damping}`
- `thickness`: `{thickness}`
- `radius`: `{radius}`
- `length`: `{length}`
- `width`: `{width}`
- `skin_subgrid`: `{skin_subgrid}`
- `skin_inflate`: `{skin_inflate}`
- `bag_scale`: `{bag_scale}`
- `bag_parts`: `{bag_parts}`
- `edge_equality`: `{edge_equality}`
- `elastic2d`: `{elastic2d}`

关键控制项说明：

- `--radius` 控制 flex 碰撞接触半径。如果需要更厚的碰撞体，可以从 `0.003` 小幅增加到 `0.004` 或 `0.005`，但过大容易导致接触不稳定。
- `--skin-subgrid` 和 `--skin-inflate` 目前只记录建议值，不写入 XML。原因是当前 `robocasa` 环境里的 MuJoCo 3.3.1 不接受 `flexcomp` 的 `<skin>` 子标签，也不接受 `subgrid`、`inflate` 属性；如果之后升级到支持该写法的 MuJoCo 版本，可以再启用。
- `--edge-equality` 会增加 MuJoCo flex edge equality 约束，是抑制过度拉伸的主要开关。
- 当前生成脚本默认开启 `edge_equality`；只有在需要做拉伸对照测试时，才建议使用 `--no-edge-equality` 关闭。
- `--elastic2d bend` 保持 `mujoco.elasticity.shell` 插件开启，是当前用于弯曲和 shell 弹性的路径；`--elastic2d none` 仅建议作为调试对照。
- bag 使用已有的 convex decomposition 碰撞资产，并被复制到 `assets/scene_3dgs/towel_multibody_demo/bag_convex/`，这样毛巾柔性布料和 bag 凹面分解碰撞可以在一个 viewer 中同时观察。

建议调参方向：

- 如果抓取或落球时拉伸过大，优先保持 `--edge-equality` 开启，再适度提高 `young`。
- 如果浴巾太硬、不够能弯，先避免继续增加 `thickness`，把厚度感更多交给 `skin inflate` 和贴图表现。
- 如果碰撞穿透明显，再谨慎增加 `radius`，不要直接把 `skin_inflate` 当成碰撞厚度参数。
- 如果抖动或回弹像橡胶，可以适度提高 `damping`。

重新生成示例：

```bash
cd /home/dw/RoboOS_Agent/FQPlanner
conda activate robocasa
python tools/prepare_towel_multibody_demo.py \\
  --young 5e4 \\
  --damping 0.4 \\
  --thickness 0.01 \\
  --radius 0.003 \\
  --bag-scale 0.5 \\
  --edge-equality \\
  --elastic2d bend
```

打开 viewer：

```bash
cd /home/dw/RoboOS_Agent/FQPlanner
conda activate robocasa
python -c "import mujoco.viewer; mujoco.viewer.launch_from_path('assets/scene_3dgs/towel_multibody_demo/towel_softcloth_drop_test.xml')"
```
"""
    readme_path.write_text(readme, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--bag-demo-dir", type=Path, default=DEFAULT_BAG_DEMO)
    parser.add_argument("--ref-image", type=Path, default=DEFAULT_REF_IMAGE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--cols", type=int, default=10)
    parser.add_argument("--rows", type=int, default=7)
    parser.add_argument("--scale", type=float, default=0.35)
    parser.add_argument("--bag-scale", type=float, default=0.5)
    parser.add_argument("--length", type=float, default=0.3)
    parser.add_argument("--width", type=float, default=0.15)
    parser.add_argument("--mass", type=float, default=0.12)
    parser.add_argument("--young", type=float, default=5e4)
    parser.add_argument("--damping", type=float, default=0.4)
    parser.add_argument("--thickness", type=float, default=0.01)
    parser.add_argument("--radius", type=float, default=0.003)
    parser.add_argument("--skin-inflate", type=float, default=0.02)
    parser.add_argument("--skin-subgrid", type=int, default=2)
    parser.add_argument("--edge-equality", dest="edge_equality", action="store_true", default=True)
    parser.add_argument("--no-edge-equality", dest="edge_equality", action="store_false")
    parser.add_argument("--elastic2d", choices=("bend", "none"), default="bend")
    args = parser.parse_args()

    source_objs = sorted(args.source_dir.glob("*.obj"))
    if not source_objs:
        raise FileNotFoundError(f"No OBJ found in {args.source_dir}")
    source_obj = source_objs[0]
    mesh = load_mesh(source_obj)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    visual_obj = copy_source_assets(args.source_dir, args.out_dir, args.ref_image)
    bag_visual_obj, bag_part_paths = copy_bag_demo_assets(args.bag_demo_dir, args.out_dir)
    xml_path = write_mujoco_scene(
        out_dir=args.out_dir,
        visual_obj=visual_obj,
        bag_visual_obj=bag_visual_obj,
        bag_part_paths=bag_part_paths,
        cols=args.cols,
        rows=args.rows,
        scale=args.scale,
        bag_scale=args.bag_scale,
        length=args.length,
        width=args.width,
        mass=args.mass,
        young=args.young,
        damping=args.damping,
        thickness=args.thickness,
        radius=args.radius,
        skin_inflate=args.skin_inflate,
        skin_subgrid=args.skin_subgrid,
        edge_equality=args.edge_equality,
        elastic2d=args.elastic2d,
    )
    write_readme(
        args.out_dir,
        source_obj,
        args.cols,
        args.rows,
        args.scale,
        args.length,
        args.width,
        args.bag_scale,
        len(bag_part_paths),
        args.mass,
        args.young,
        args.damping,
        args.thickness,
        args.radius,
        args.skin_inflate,
        args.skin_subgrid,
        args.edge_equality,
        args.elastic2d,
    )
    write_source_readme(
        args.source_dir,
        args.out_dir,
        args.length,
        args.width,
        args.young,
        args.damping,
        args.thickness,
        args.radius,
        args.skin_inflate,
        args.skin_subgrid,
        args.bag_scale,
        len(bag_part_paths),
        args.edge_equality,
        args.elastic2d,
    )

    print(f"source vertices={len(mesh.vertices)} faces={len(mesh.faces)}")
    print(f"source bounds={mesh.bounds.tolist()}")
    print(f"source extents={mesh.extents.tolist()}")
    print(
        f"softcloth={args.cols}x{args.rows}, length={args.length}, width={args.width}, "
        f"mass={args.mass}, radius={args.radius}, "
        f"skin_subgrid={args.skin_subgrid}, skin_inflate={args.skin_inflate}, "
        f"edge_equality={args.edge_equality}, elastic2d={args.elastic2d}"
    )
    print(f"bag_convex_parts={len(bag_part_paths)}, bag_scale={args.bag_scale}")
    print(
        "note=MuJoCo 3.3.1 in robocasa rejects flexcomp <skin>, subgrid, and inflate; "
        "the XML uses textured flex material with flatskin=false instead."
    )
    print(f"scene={xml_path}")


if __name__ == "__main__":
    main()
