"""serve_alfworld/main.py — launch ALFWorld Flask backend on port 5301.

Usage:
    conda activate alfworld
    export ALFWORLD_DATA=~/alfworld_data
    cd /Users/christinebi/FQPlanner
    python serve_alfworld/main.py
    python serve_alfworld/main.py --split eval_out_of_distribution
"""

from __future__ import annotations

import argparse
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import serve_alfworld.server as srv
from serve_alfworld.alf_env import AlfEnv

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5301)
    parser.add_argument("--split", default="train")
    parser.add_argument("--game", type=int, default=-1,
                        help="rng seed to select a specific game; -1 = random")
    args = parser.parse_args()

    config_path = os.environ.get(
        "ALFWORLD_CONFIG",
        os.path.expanduser("~/alfworld-repo/configs/base_config.yaml"),
    )
    os.environ["ALFWORLD_SPLIT"] = args.split

    # eager init so first action doesn't need a /reset call
    # Seed precedence: --game flag > ALFWORLD_SEED env > random. The benchmark needs a
    # FIXED seed (it's what makes index→game reproducible); set --game 0 or ALFWORLD_SEED=0.
    if args.game >= 0:
        seed = args.game
    elif os.environ.get("ALFWORLD_SEED", "") != "":
        seed = int(os.environ["ALFWORLD_SEED"])
    else:
        seed = random.randint(0, 9999)
    srv._env = AlfEnv(config_path=config_path, split=args.split, rng_seed=seed)
    snap = srv._env.reset()
    print(f"[alfworld] seed  : {seed}")
    print(f"[alfworld] task : {snap['task']}")
    print(f"[alfworld] split: {args.split}")
    print(f"[alfworld] http  : http://127.0.0.1:{args.port}")

    srv.app.run(host="127.0.0.1", port=args.port, debug=False)
