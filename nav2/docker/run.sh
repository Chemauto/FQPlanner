#!/bin/bash
# 启动 Nav2 容器（前台运行，Ctrl+C 退出）
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "[run] 启动 Nav2 容器 (host 网络)..."
echo "[run]   - Map Server: kitchen_map.yaml"
echo "[run]   - Bridge Node: http://127.0.0.1:5002/navigate"
echo "[run]   - MuJoCo API: http://127.0.0.1:5001"
echo "[run] Ctrl+C 退出"
echo ""

if command -v xhost >/dev/null 2>&1 && [ -n "$DISPLAY" ]; then
    xhost +local:docker >/dev/null 2>&1 || true
fi

docker run --rm -it \
    --name fqplanner_nav2 \
    --network host \
    -e DISPLAY="$DISPLAY" \
    -e QT_X11_NO_MITSHM=1 \
    -e RUN_RVIZ="${RUN_RVIZ:-1}" \
    -e LINEAR_SCALE="${LINEAR_SCALE:-1.0}" \
    -e ANGULAR_SCALE="${ANGULAR_SCALE:-1.0}" \
    -e MAX_LINEAR="${MAX_LINEAR:-0.35}" \
    -e MAX_ANGULAR="${MAX_ANGULAR:-0.25}" \
    -e CMD_SMOOTHING="${CMD_SMOOTHING:-0.35}" \
    -e MUJOCO_API_URL=http://127.0.0.1:5001 \
    -e BRIDGE_PORT=5002 \
    -v /tmp/.X11-unix:/tmp/.X11-unix \
    -v "$PROJECT_DIR/maps:/nav2/maps" \
    -v "$PROJECT_DIR/rviz_config.rviz:/nav2/rviz_config.rviz" \
    -v "$PROJECT_DIR/launch.sh:/nav2/launch.sh" \
    -v "$PROJECT_DIR/bridge_node.py:/nav2/bridge_node.py" \
    -v "$PROJECT_DIR/pandaomron.urdf:/nav2/pandaomron.urdf" \
    -v "$PROJECT_DIR/nav2_params.yaml:/nav2/nav2_params.yaml" \
    fqplanner_nav2
