# scene_3dgs - 3DGS 导航场景

基于 3D Gaussian Splatting 渲染的室内导航场景，用于 MuJoCo 仿真中的机器人导航任务。

## 目录结构

```
scene_3dgs/
├── config.json              # 场景入口配置（机器人、3DGS 资源、物体列表）
├── config.yaml              # 地图生成参数配置
├── map_generator.py         # 从碰撞 XML 生成 Nav2 占据地图
├── maps/
│   ├── scene_map.pgm        # 2D 占据栅格地图（黑白 PGM）
│   └── scene_map.yaml       # Nav2 地图元数据（分辨率、原点）
└── nav_scene_1/
    ├── 3dgs/
    │   └── point_cloud.ply  # 3DGS 高斯点云（~94 万点，含外观参数）
    ├── meshes/
    │   ├── object/mesh/     # 场景环境 mesh
    │   ├── object/mesh_raw_prune/  # V-HACD 碰撞分解 mesh（1630 个子部件）
    │   └── hunyuan3d/       # Hunyuan3D 生成的操作物体（glb 格式）
    └── mjcf/
        ├── scene.xml        # 主场景 XML（含 body 变换、碰撞引用）
        ├── simulate.xml     # 仿真用场景
        └── object/
            └── sugar_collision.xml  # 碰撞几何体（7348 个 box）
```

## 场景物体

| 名称 | link | 说明 |
|------|------|------|
| bottle | `hunyuan_bottle_body` | 瓶子 |
| maojin | `hunyuan_maojin_body` | 毛巾 |
| lajitong | `hunyuan_lajitong_body` | 垃圾桶 |
| bianzhidai | `hunyuan_bianzhidai_body` | 编织袋 |

物体模型由 [Hunyuan3D](https://github.com/Tencent/Hunyuan3D-1) 生成，以 GLB 格式存储，通过 `composite_mesh_objects` 配置自动合成到 3DGS 场景中。

## 地图生成

从碰撞 XML（V-HACD 分解的 box 集合）生成 Nav2 格式的 2D 占据地图：

```bash
python assets/scene_3dgs/map_generator.py
# 或指定配置文件
python assets/scene_3dgs/map_generator.py --config assets/scene_3dgs/config.yaml
```

### 生成流程

1. 解析 `sugar_collision.xml` 中的 7348 个 box 碰撞几何体
2. 应用 `scene.xml` 中 mesh body 的世界变换（位置 + 欧拉角旋转）
3. 按高度过滤，仅保留 z ∈ `[z_min, z_max]` 范围内的碰撞体（默认 0~2m）
4. 将每个 OBB 的 8 顶角投影到 XY 平面，光栅化为占据栅格
5. 膨胀闭合 V-HACD 分块间的缝隙，添加边框和最终安全膨胀
6. 输出 PGM（P5 灰度）+ YAML 元数据

### 配置参数

所有参数定义在 `config.yaml` 中：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `map.resolution` | 0.05 | 栅格分辨率（米/像素） |
| `map.z_min` | 0.0 | 碰撞高度下限（米） |
| `map.z_max` | 2.0 | 碰撞高度上限（米） |
| `map.vahacd_dilation` | 0.15 | V-HACD 缝隙闭合膨胀（米） |
| `map.inflate_radius` | 0.05 | 障碍物最终膨胀半径（米） |
| `map.border_margin` | 0.20 | 地图四周障碍边框宽度（米） |
| `map.bounds_padding` | 1.0 | 碰撞包围盒外扩（米） |

### 输出说明

- `scene_map.pgm`：P5 格式灰度图，像素值 0=障碍物，254=可通行
- `scene_map.yaml`：Nav2 标准地图元数据，包含分辨率、原点坐标
