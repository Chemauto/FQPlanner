#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

export LD_PRELOAD="/lib/x86_64-linux-gnu/libffi.so.7${LD_PRELOAD:+:${LD_PRELOAD}}"

python serve_3dgs/demo.py
