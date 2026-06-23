# 浴巾 Soft-Cloth Demo

生成来源：

`/home/dw/gs_playground/hunyuan3D/maojin/c5492efea47170a1ea6e0349128e67af/0a6bf3c2d16eaf94a957350e746d954a.obj`

输出内容：

- `visual/`：从 Hunyuan3D 毛巾源目录复制过来的 OBJ、MTL 和贴图文件。
- `bag_convex/`：从 `bag_convex_demo` 复制过来的 bag visual mesh 和 convex collision parts。
- `towel_softcloth_drop_test.xml`：主要的 MuJoCo 柔性布料验证场景。
- `towel_flex_drop_test.xml`、`towel_grid_drop_test.xml`、`towel_chain_drop_test.xml`、`towel_physics_drop_test.xml`：与主场景内容一致的兼容文件。
- `maojin.png`：从源目录复制过来的参考图。

建模方式：

- 实际参与仿真的浴巾是 MuJoCo `flexcomp type="grid"`，并启用 `mujoco.elasticity.shell`。
- 重力和接触碰撞都已开启。
- 浴巾当前没有任何一侧固定，所有 flex 节点都会在重力和接触作用下自由运动。
- 红色小球会自由下落到布料上，用来观察布料弯曲、拉伸和接触稳定性。
- 场景右侧加入了之前完成的 bag 凹面物体分解碰撞测试：bag 使用 `20` 个 convex collision parts，一个较大的红色小球从 bag 正上方落下。
- Hunyuan3D OBJ 保留为视觉参考，不参与碰撞计算。
- `flexcomp` 已绑定 `towel_mat`，使用 `visual/texture_pbr_20250901_roughness.png` 作为贴图；在 MuJoCo 3.3.1 中，给 flex 指定 material 后会自动生成 texture coordinates。
- 当前 `robocasa` 环境的 MuJoCo 3.3.1 不接受 `flexcomp` 内的 `<skin>` 子标签，也不接受 `subgrid` 和 `inflate` 属性，所以这里没有把它们写进 XML；视觉平滑主要通过 `flatskin="false"` 和贴图完成，真实接触厚度仍由 `radius` 和 shell `thickness` 控制。

当前参数：

- flex 分辨率：`10 x 7` 顶点
- towel length：`0.3`
- towel width：`0.15`
- 视觉 mesh 缩放：`0.35`
- bag mesh 缩放：`0.5`
- bag convex parts：`20`
- towel mass：`0.12`
- shell young：`50000.0`
- shell damping：`0.4`
- shell thickness：`0.01`
- flex contact radius：`0.003`
- 建议 skin subgrid：`2`，当前 MuJoCo 3.3.1 XML schema 不支持写入
- 建议 skin inflate：`0.02`，当前 MuJoCo 3.3.1 XML schema 不支持写入
- all-edge equality constraint：`True`
- 2D elasticity mode：`bend`

说明：`edge equality` 现在默认开启，用来抑制毛巾被随意拉长；如果需要做拉伸对照测试，可以在生成命令中显式加入 `--no-edge-equality`。

重新生成场景：

```bash
cd /home/dw/RoboOS_Agent/FQPlanner
conda activate robocasa
python tools/prepare_towel_multibody_demo.py \
  --young 5e4 \
  --damping 0.4 \
  --thickness 0.01 \
  --radius 0.003 \
  --bag-scale 0.5 \
  --edge-equality \
  --elastic2d bend
```

打开 MuJoCo viewer 测试：

```bash
cd /home/dw/RoboOS_Agent/FQPlanner
conda activate robocasa
python -c "import mujoco.viewer; mujoco.viewer.launch_from_path('assets/scene_3dgs/towel_multibody_demo/towel_softcloth_drop_test.xml')"
```
