#!/bin/bash
# 在已经运行的 Nav2 容器中打开 RViz2
set -e

if ! docker ps --format '{{.Names}}' | grep -qx fqplanner_nav2; then
    echo "[rviz] 容器 fqplanner_nav2 未运行，请先执行: bash docker/run.sh"
    exit 1
fi

echo "[rviz] 启动 RViz2..."
docker exec -it \
    -e DISPLAY="$DISPLAY" \
    -e QT_X11_NO_MITSHM=1 \
    fqplanner_nav2 \
    bash -lc "source /opt/ros/humble/setup.bash && rviz2"
