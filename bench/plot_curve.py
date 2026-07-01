#!/usr/bin/env python3
"""
bench/plot_curve.py — 把 run_curve.py 的 CSV 画成双线学习曲线。

    python bench/plot_curve.py --csv bench/curve_results.csv

X = 已学习的训练任务数;两条线:
  - sr_sameset : 同集(上界 / 含背答案)—— 虚线
  - sr_heldout : valid_unseen 留出集(真·泛化)—— 实线、加粗
若两条都随训练量上升 → 经验在泛化;只有 sameset 上升 → 主要是背答案。
"""

from __future__ import annotations

import argparse
import csv
import os


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                 "curve_results.csv"))
    p.add_argument("--out", default=None, help="输出 PNG(默认与 CSV 同名 .png)")
    p.add_argument("--title", default="经验积累 vs 任务成功率(ALFWorld)")
    args = p.parse_args()

    xs, held, same = [], [], []
    with open(args.csv, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            xs.append(int(row["trained_tasks"]))
            held.append(float(row["sr_heldout"]))
            same.append(float(row["sr_sameset"]))

    if not xs:
        raise SystemExit(f"CSV 里没有数据行: {args.csv}")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(xs, same, "o--", color="#888", label="同集 (上界 / 含背答案)")
    ax.plot(xs, held, "o-", color="#1f77b4", linewidth=2.4, label="留出 valid_unseen (泛化)")
    for x, y in zip(xs, held):
        ax.annotate(f"{y:.2f}", (x, y), textcoords="offset points", xytext=(0, 7),
                    ha="center", fontsize=8, color="#1f77b4")

    ax.set_xlabel("已学习的训练任务数")
    ax.set_ylabel("任务成功率 (won / N)")
    ax.set_title(args.title)
    ax.set_ylim(0, 1)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    fig.tight_layout()

    out = args.out or os.path.splitext(args.csv)[0] + ".png"
    fig.savefig(out, dpi=150)
    print(f"saved → {out}")


if __name__ == "__main__":
    main()
