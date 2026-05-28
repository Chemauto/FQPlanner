#!/bin/bash
set -e

# Source ROS2
source /opt/ros/humble/setup.bash

echo "[nav2] 启动 MuJoCo-ROS2 桥接节点 + Nav2 ..."

# 1. 发布静态地图
ros2 run nav2_map_server map_server \
    --ros-args --params-file /nav2/nav2_params.yaml &
MAP_PID=$!

# 激活 map_server，让 /map 真正发布出来
ros2 run nav2_lifecycle_manager lifecycle_manager \
    --ros-args \
    -p use_sim_time:=false \
    -p autostart:=true \
    -p node_names:="[map_server]" &
MAP_LIFECYCLE_PID=$!

# 2. 启动 robot state publisher（发布 URDF）
ros2 run robot_state_publisher robot_state_publisher /nav2/pandaomron.urdf &
RSP_PID=$!

# 3. 发布 map → odom 静态 tf（仿真世界坐标与 Nav2 地图坐标对齐）
ros2 run tf2_ros static_transform_publisher \
    --x 0 --y 0 --z 0 \
    --roll 0 --pitch 0 --yaw 0 \
    --frame-id map --child-frame-id odom &
MAP_TF_PID=$!

# 4. 启动桥接节点（odom + cmd_vel 桥接 + HTTP 导航接口）
python3 /nav2/bridge_node.py &
BRIDGE_PID=$!

# 等待桥接节点就绪
sleep 2

# 5. 启动 Nav2 导航栈
ros2 launch nav2_bringup navigation_launch.py \
    params_file:=/nav2/nav2_params.yaml \
    use_sim_time:=false &
NAV2_PID=$!

RVIZ_PID=""
if [ "${RUN_RVIZ:-0}" = "1" ]; then
    if command -v rviz2 >/dev/null 2>&1 && [ -n "${DISPLAY:-}" ]; then
        rviz2 -d /nav2/rviz_config.rviz &
        RVIZ_PID=$!
    else
        echo "[nav2] RViz 未启动：rviz2 不存在或 DISPLAY 为空"
    fi
fi

echo "[nav2] 所有服务已启动"
echo "[nav2]   - Map Server (PID $MAP_PID)"
echo "[nav2]   - Map Lifecycle Manager (PID $MAP_LIFECYCLE_PID)"
echo "[nav2]   - Robot State Publisher (PID $RSP_PID)"
echo "[nav2]   - Static TF map->odom (PID $MAP_TF_PID)"
echo "[nav2]   - Bridge Node (PID $BRIDGE_PID)"
echo "[nav2]   - Nav2 Stack (PID $NAV2_PID)"
if [ -n "$RVIZ_PID" ]; then
    echo "[nav2]   - RViz2 (PID $RVIZ_PID)"
fi

# 等待任意进程退出
wait -n

# 清理
if [ -n "$RVIZ_PID" ]; then
    kill $RVIZ_PID 2>/dev/null
fi
kill $MAP_PID $MAP_LIFECYCLE_PID $RSP_PID $MAP_TF_PID $BRIDGE_PID $NAV2_PID 2>/dev/null
