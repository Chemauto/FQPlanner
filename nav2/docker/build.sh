#!/bin/bash
# 构建 Nav2 Docker 镜像
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "[build] 构建 fqplanner_nav2 镜像..."
docker build -t fqplanner_nav2 "$PROJECT_DIR"
echo "[build] 完成"
