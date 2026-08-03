#!/usr/bin/env python3
"""把 pgsr_office.obj 凸分解成碰撞几何(MuJoCo/MotrixSim 的 mesh 碰撞必须是凸的;
大非凸场景直接当碰撞会被取凸包 → 屋子变一坨实心、机器人进不去)。

生成(都写到 meshes/ 下,供 scene.xml 的两个 <include> 引用):
  coll_*.obj                    每个凸块
  office_collision_assets.xml   <mesh> 注册(scene.xml 的 <asset> 里 include)
  office_collision.xml          <geom> 碰撞(scene.xml 的 mesh body 里 include)

用法(repo 根):
  pip install coacd trimesh
  python assets/scene_3dgs/office/gen_collision.py
  python assets/scene_3dgs/office/gen_collision.py --threshold 0.1   # 块太多就调大(粗=快)
"""
import argparse
import os
from pathlib import Path

import numpy as np
import trimesh
import coacd


def main():
    d = Path(__file__).parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--obj", default=str(d / "meshes" / "pgsr_office.obj"))
    ap.add_argument("--out-dir", default=str(d / "meshes"))
    ap.add_argument("--threshold", type=float, default=0.05,
                    help="coacd 凸分解精度:越小越碎越准也越慢(0.03~0.1)")
    args = ap.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    m = trimesh.load(args.obj, force="mesh")
    print(f"载入 {args.obj}: {len(m.vertices)} 顶点 / {len(m.faces)} 面")
    parts = coacd.run_coacd(coacd.Mesh(m.vertices, m.faces), threshold=args.threshold)
    print(f"凸分解 → {len(parts)} 块")

    asset_lines, geom_lines = [], []
    for i, (v, f) in enumerate(parts):
        name = f"coll_{i}"
        trimesh.Trimesh(np.asarray(v), np.asarray(f)).export(out / f"{name}.obj")
        asset_lines.append(f'  <mesh name="{name}" file="{name}.obj"/>')
        geom_lines.append(
            f'  <geom type="mesh" mesh="{name}" group="3" '
            f'contype="1" conaffinity="1" rgba="0 1 0 0"/>')

    (out / "office_collision_assets.xml").write_text(
        "<mujocoinclude>\n" + "\n".join(asset_lines) + "\n</mujocoinclude>\n", encoding="utf-8")
    (out / "office_collision.xml").write_text(
        "<mujocoinclude>\n" + "\n".join(geom_lines) + "\n</mujocoinclude>\n", encoding="utf-8")

    print(f"写出 office_collision_assets.xml + office_collision.xml({len(parts)} 块)")
    if len(parts) > 200:
        print("⚠ 块数偏多(>200),物理会慢;调大 --threshold 减少块数")


if __name__ == "__main__":
    main()
