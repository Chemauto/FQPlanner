# office — 用 PGSR 的 mesh + gaussian 起 3DGS 仿真

把 PGSR 重建(`pgsr_office.obj` + `pgsr_office.ply`)塞进 serve_3dgs,起一个照片级渲染 + 物理碰撞的
office 场景,给导航组 / VLA 组联调。数据流:

```
pgsr_office.obj  → 物理场景(可视 mesh + 凸分解碰撞:机器人走/避障/不穿墙)
pgsr_office.ply  → 3DGS 渲染背景(CUDA gsplat:给相机/VLA 看照片级真实图)
两者 PGSR 同一次重建、天然对齐 —— 摆正一次,mesh 和 gaussian 一起对齐。
```

## 0. 放文件
```
assets/scene_3dgs/office/meshes/pgsr_office.obj
assets/scene_3dgs/office/3dgs/pgsr_office.ply
```

## 步骤(在 GPU 电脑,repo 根目录跑)

**1. 凸分解出碰撞**(⚠️ 不做 = 机器人进不去屋子):
```bash
pip install coacd trimesh
python assets/scene_3dgs/office/gen_collision.py          # 块太多加 --threshold 0.1
```
生成 `meshes/office_collision_assets.xml` + `office_collision.xml` + `coll_*.obj`,scene.xml 已 include。

**2. 摆正落地**(⚠️ 最花时间):编辑 `mjcf/scene.xml` 里 `<body name="mesh">` 的 `pos` / `euler`,
让 office **正立、地板贴 z=0**。3DGS 常 Y-up,先试 `euler="-90 0 0"`,起服务(第 5 步)截图看,反复调。

**3. ply 跟着对齐**(读 scene.xml 的 mesh 变换,应用到 gaussian):
```bash
python assets/scene_3dgs/office/transform_ply.py         # → pgsr_office_transformed.ply
```

**4.（导航要）生成 2D 占据地图**:
```bash
python assets/scene_3dgs/office/gen_map2d.py --z-min 0.1 --z-max 1.8
```
→ `maps/scene_map.pgm` + `scene_map.yaml`(Nav2 格式,给导航组)。

**5. 起服务 + 冒烟**:
```bash
# ⚠️ --scene_config 用绝对路径(GSConfig 以 config 文件所在目录做基准 resolve scene/ply)
python serve_3dgs/main.py --no-viewer \
  --scene_config "$(pwd)/assets/scene_3dgs/office/config.json" --port 5002
# 另开终端:
curl -X POST localhost:5002/screenshot -o office.jpg     # 验收:正立?渲染照片级?机器人在地面?
```

调对 2/3 后 `office.jpg` 应是照片级、机器人站地面。之后按主指南 **Part E/F**:大脑机
`robot_api/config.yaml` → `active_backend: mujoco_3dgs` + url 指到这台 IP:5002,再接导航/VLA。

## 注意
- **先跑第 1 步再起服务**,否则 scene.xml 引用的碰撞 include 文件不存在会报错。
- 机器人由 `assets/config.yaml` 的 `robot:` 决定(现 `BlueThink`),换 G1 改那里 + 放 G1 的 assets。
- 第 2 步摆正靠截图迭代,是整个流程最容易卡的地方;摆对了 ply(第 3 步)和地图(第 4 步)自动跟着对。
- CUDA/gsplat:`torch.cuda.is_available()` 必须 True,gsplat 首次 import 会 JIT 编译(要 CUDA 12.4 toolkit)。

## 另一台机器上跑(pull 后)

⚠️ `pgsr_office.obj`(916M)+ `.ply`(304M)**被 `.gitignore`,不在 git 里**(太大)。pull 下来只有脚手架,要**单独把这两个文件放进** `office/meshes/` 和 `office/3dgs/`(scp 过去,或像 `point_cloud.ply` 那样传 HuggingFace 再下)。之后按上面 1–5 步跑。

## 接 G1control 导航(同源,可路 B 深整合)

我们的 office 和 **G1control**(YeLuo-123/G1control)那套 G1 ROS2 导航栈的 office **极可能同源、坐标系对齐**(X 起点 ≈ −7、Y ≈ ±6)。所以:
- **导航**用 G1control 栈(它自带 Cartographer 地图 + Dijkstra + nav2point 避障),大脑通过桥 `docker/nav2/.../g1_nav_bridge.py`(HTTP `/nav` → `/g1pilot/goal` topic)发目标;它的 `/map` 可直接当导航地图,**不必再跑 `gen_map2d.py`**。
- **渲染**用这套 serve_3dgs 的 3DGS(给 VLA/相机照片级图)。
- 两者位姿在同一坐标系 → 同一个 office,物理导航走 G1control、看图走 3DGS。对接细节见 `docs/对接手册-导航组-接待demo.md`。
