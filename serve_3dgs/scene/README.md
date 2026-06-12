# scene/ — 场景生成和状态管理

## 文件说明

```
scene/
├── scene_generator.py         # 场景生成器（RoboCasa 厨房 + XLeRobot 合并）
├── scene_memory.py            # 场景状态记忆（物体在哪个家具/工作点上）
├── __init__.py
└── config/
    ├── layout.yaml            # 房间布局（墙壁、地面、家具位置）
    ├── style.yaml             # 外观风格（材质、颜色、型号）
    ├── objects.yaml           # 物体列表（名称、类别、放置规则）
    ├── camera.yaml            # 截图和按需相机预览配置
    ├── waypoints.yaml         # 导航工作点（坐标、服务哪些物体）
    ├── scene_state.yaml       # 当前场景状态（物体在哪个位置）
    └── scene_state_initial.yaml  # 初始场景状态（重启时恢复）
```

## scene_generator.py — 场景生成器

读取 config 下的配置文件，调用 RoboCasa 生成真实厨房几何和物体模型，
合并 XLeRobot 机器人，输出最终的 MuJoCo 场景。

**输入：**
- `config/layout.yaml` — 房间结构
- `config/style.yaml` — 外观风格
- `config/objects.yaml` — 物体配置
- `config/camera.yaml` — `/screenshot` 默认尺寸、`/camera/latest` 预览相机和尺寸
- `assets/xlerobot/xlerobot.xml` — 机器人模型

**输出：**
- `assets/scene/scene.xml` — 合并后的 MuJoCo 场景
- `assets/scene/scene_meta.json` — 物体和家具的元信息

注意：`assets/scene/scene.xml` 是生成文件，里面会包含当前机器 RoboCasa
安装目录下的 mesh/texture 绝对路径。上传 GitHub 后不要把它当成便携
源文件使用；别人 clone 后应安装依赖并通过 `serve/main.py` 重新生成。

**主要函数：**

| 函数 | 作用 |
|------|------|
| `build_scene_xml()` | 主入口：加载配置 → 创建厨房 → 放物体 → 合并机器人 → 后处理 |
| `_merge_robocasa_into_robot()` | 将 RoboCasa 厨房 MJCF 合并到机器人 XML |
| `_set_generated_compiler_paths()` | 设置 meshdir 使场景能找到机器人 mesh |
| `_add_cameras()` | 添加 overhead/side/frontview/eye_in_hand 相机 |
| `_set_robot_initial_pose()` | 设置底盘初始位置 [3.2, -1.5, z] |
| `_add_missing_robot_inertials()` | 给相机 body 补充 inertial |
| `_hide_nonvisual_geoms()` | 隐藏碰撞体/registry 等非视觉几何 |
| `_enable_robocasa_collisions()` | 恢复 RoboCasa 碰撞几何的 contype/conaffinity |

## scene_memory.py — 场景状态记忆

记录每个物体当前在哪个工作点/家具上，动作执行后自动更新。

| 函数 | 作用 |
|------|------|
| `get_object_location(obj)` | 返回物体所在的工作点名 |
| `get_object_coords(obj)` | 返回物体所在工作点的坐标 |
| `move_object(obj, location)` | 更新物体位置（位置名或 'robot_hand'） |
| `coords_to_waypoint(pos)` | 根据坐标找最近的工作点 |
| `get_all_locations()` | 返回所有位置及其物体列表 |
| `reset_to_initial()` | 重置为初始场景状态 |

## 修改场景

**增删物体：** 编辑 `config/objects.yaml`，重启 `serve/main.py` 自动重新生成。

**修改房间布局：** 编辑 `config/layout.yaml` 和 `config/style.yaml`。

**修改导航工作点：** 运行 `python nav2/workpoints_generator.py` 重新生成。
