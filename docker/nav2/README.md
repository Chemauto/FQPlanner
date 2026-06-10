# FQPlanner Nav2 Docker

This Docker context contains the copied ROS2 navigation bridge package and the
current FQPlanner Nav2 maps/config needed to run Nav2 against a MuJoCo backend.

Build from the project root:

```bash
./docker/build.sh
```

Enter the container:

```bash
./docker/run.sh
```

Inside the container, launch Nav2 without RViz:

```bash
ros2 launch fqplanner_nav_bridge mujoco_navigation.launch.py \
  backend_url:=http://host.docker.internal:5001 \
  http_host:=0.0.0.0 \
  http_port:=5102 \
  launch_rviz:=false
```

On the host, point project navigation calls at the container bridge:

```bash
export ROBOT_API_URL=http://127.0.0.1:5102
```

The MuJoCo backend should be running on the host before launching Nav2:

```bash
conda run -n robocasa python serve/main.py --no-viewer
```
