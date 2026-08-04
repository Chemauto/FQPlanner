#!/usr/bin/env python3
"""把 pgsr_office.obj 凸分解成碰撞几何(MuJoCo/MotrixSim 的 mesh 碰撞必须是凸的;大非凸场景直接
当碰撞会被取凸包 → 屋子变一坨实心、机器人进不去)。

⚠️ PGSR 重建 mesh 顶点极多(office 近千万顶点),coacd 直接分解会卡死/跑几小时 → **先简化到
~max_faces 再分解**(碰撞用不着精细)。简化用 trimesh 的 quadric decimation,需要:
  pip install fast-simplification

生成(都写到 meshes/ 下,scene.xml 的两个 <include> 引用):
  coll_*.obj / office_collision_assets.xml(<mesh> 注册) / office_collision.xml(<geom> 碰撞)

用法(repo 根):
  pip install coacd trimesh fast-simplification
  python assets/scene_3dgs/office/gen_collision.py
  python assets/scene_3dgs/office/gen_collision.py --max-faces 40000 --threshold 0.12   # 更快更粗
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
    ap.add_argument("--max-faces", type=int, default=60000,
                    help="碰撞用不着精细:先简化到这个面数再凸分解(越小越快;40000 更快)")
    ap.add_argument("--threshold", type=float, default=0.08,
                    help="coacd 凸分解精度(越大越粗越快,0.05~0.15)")
    args = ap.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    print(f"载入 {args.obj}(大 mesh 读盘也要一会儿)...", flush=True)
    # process=False:跳过顶点合并/修复,970万顶点的 mesh 加载快 10 倍+、省内存(默认那步会卡几分钟/swap)
    m = trimesh.load(args.obj, force="mesh", process=False)
    print(f"  原始: {len(m.vertices)} 顶点 / {len(m.faces)} 面", flush=True)

    if len(m.faces) > args.max_faces:
        print(f"  面数过高 → 先简化到 ~{args.max_faces}(否则 coacd 极慢)...", flush=True)
        try:
            m = m.simplify_quadric_decimation(args.max_faces)
        except Exception as e:
            raise SystemExit(
                f"简化失败({e})。请先 `pip install fast-simplification` 再重跑。")
        print(f"  简化后: {len(m.faces)} 面", flush=True)

    print(f"凸分解中(threshold={args.threshold},这一步可能要几分钟,别急)...", flush=True)
    parts = coacd.run_coacd(coacd.Mesh(m.vertices, m.faces), threshold=args.threshold)
    print(f"  → {len(parts)} 个凸块", flush=True)

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
    print(f"写出 office_collision_assets.xml + office_collision.xml({len(parts)} 块)", flush=True)
    if len(parts) > 200:
        print("⚠ 凸块偏多(>200),物理会慢;可调大 --threshold", flush=True)


if __name__ == "__main__":
    main()
