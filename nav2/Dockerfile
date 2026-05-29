FROM ros:humble

# 安装 Nav2 和相关依赖
RUN apt-get update && apt-get install -y \
    ros-humble-navigation2 \
    ros-humble-nav2-bringup \
    ros-humble-nav2-msgs \
    ros-humble-nav2-simple-commander \
    ros-humble-robot-state-publisher \
    ros-humble-rviz2 \
    ros-humble-xacro \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python HTTP 依赖（桥接用）
RUN pip3 install --no-cache-dir requests

WORKDIR /nav2

# 复制所有 Nav2 配置和脚本
COPY bridge_node.py .
COPY map_generator.py .
COPY pandaomron.urdf .
COPY nav2_params.yaml .
COPY launch.sh .

RUN chmod +x launch.sh

# 桥接节点 HTTP 端口（接收导航目标）
EXPOSE 5002

# 默认启动：source ROS2 + 启动桥接节点 + Nav2
CMD ["./launch.sh"]
