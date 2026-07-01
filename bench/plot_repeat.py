#!/usr/bin/env python3
"""bench/plot_repeat.py — 画 Phase 0 的 steps-vs-run 折线。

读 repeat_results.csv(run_repeat.py 产出),画"同一个 game 重复跑,步数随 run 下降"。
步数降 + won 全程 True = Phase 0 通过。

    python bench/plot_repeat.py --csv bench/repeat_results.csv
"""

import argparse
import csv
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--csv", default=os.path.join(HERE, "repeat_results.csv"))
    p.add_argument("--out", default=None)
    args = p.parse_args()

    runs, steps, wons = [], [], []
    with open(args.csv, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            runs.append(int(row["run_k"]))
            steps.append(int(row["steps"]))
            wons.append(str(row["won"]).strip().lower() in ("true", "1"))

    out = args.out or args.csv.replace(".csv", ".png")
    plt.figure(figsize=(7, 4))
    plt.plot(runs, steps, "-o", color="tab:blue", label="steps")
    fail = [(r, s) for r, s, w in zip(runs, steps, wons) if not w]
    if fail:
        plt.scatter([r for r, _ in fail], [s for _, s in fail],
                    color="red", zorder=5, label="won=False")
    plt.xlabel("repeat (run_k)")
    plt.ylabel("steps to complete")
    plt.title("Phase 0: same game repeated — steps should drop")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(out, dpi=120)
    print(f"✓ {out}")


if __name__ == "__main__":
    main()
