# 物体渲染与动力学仿真研究记录

负责人：待补充

记录时间：2026-06-25

## 复现项目与本地路径

复现项目：

```text
https://github.com/Chemauto/FQPlanner/tree/compose
```

当前本地路径：

```text
/home/dw/RoboOS_Agent/FQPlanner
```

当前工作分支：

```text
compose1
```

Hunyuan3D 生成物体路径：

```text
/home/dw/gs_playground/hunyuan3D
```

当前目标是在 FQPlanner 的四视角 3DGS + MotrixSim 环境中，导入真实场景背景和 Hunyuan3D 操作物体，使操作物体可以参与动力学仿真，并能在四个视角小窗中被合成渲染。

## 一、物体渲染和动力学仿真

### 1. 地瓜桌面生成与 Hunyuan3D 操作物体生成

操作物体来自 `/home/dw/gs_playground/hunyuan3D` 下的 Hunyuan3D 多图生模型结果。

当前接入的操作物体包括：

```text
bottle
lajitong
bianzhidai
bag
maojin
yujin
```

技术路线：

```text
多图采集 / 生成式建模
        ↓
Hunyuan3D 生成 glb / obj 模型
        ↓
写入 FQPlanner 场景资产目录
        ↓
根据参数表对齐真实尺寸
        ↓
写入 MJCF 场景并注册为操作物体
```

### 2. 四视角合成渲染

项目中四视角环境使用 3DGS 作为真实背景渲染，同时将操作物体 mesh 根据 MotrixSim 中的 link 位姿叠加到 RGB 图像中。

合成渲染主要依赖：

```text
serve_3dgs/backend/sim_env.py
serve_3dgs/backend/mesh_compositor.py
serve_3dgs/backend/gs_config.py
assets/scene_3dgs/config.json
```

技术路线：

```text
3DGS 背景 RGB / depth
        +
操作物体 visual mesh
        +
MotrixSim link 位姿
        ↓
基于深度遮挡关系进行合成
        ↓
四个相机小窗显示动态操作物体
```

当前四个视角：

```text
follower
head_cam
right_arm_cam
left_arm_cam
```

### 3. 凹面物体碰撞分解

问题：

凹面物体如果直接使用原始 mesh 碰撞，容易出现穿模、碰撞不稳定、凹陷区域无法正确接触等问题。

当前方案：

对凹面或复杂物体进行凸包分解，把一个 visual mesh 对应为一个刚体 body 下的多个 convex collision geom。

当前分解设置：

| 物体 | 碰撞方式 | 分解块数 |
|---|---|---:|
| bag | 凸包分解 | 20 |
| lajitong | 凸包分解 | 20 |
| yujin | 凸包分解 + 软接触 | 20 |

技术路线：

```text
原始 mesh
        ↓
按三角面空间位置聚类
        ↓
每个聚类生成 convex hull
        ↓
写入 MJCF collision geoms
        ↓
保持 visual mesh 和 collision mesh 使用同一 scale
```

### 4. 柔性布料相关尝试

#### 多刚体二维分解和条状分解

尝试内容：

- 二维网格分解毛巾；
- 条状分解毛巾；
- 小块之间用约束或关节连接；
- visual patch 做重叠，避免视觉间隙。

问题：

- 二维分解容易碎裂；
- 条状分解视觉效果不好；
- 约束过硬会导致仿真闪退；
- 约束过软会导致毛巾散开；
- 四视角环境中性能压力较大。

结论：

```text
多刚体分解方案目前不适合作为主方案。
```

#### MuJoCo flex cloth

尝试内容：

使用 MuJoCo 的 flex cloth / flexcomp 机制模拟柔性布料。

效果：

```text
柔性效果较好，可以实现布料下垂、弯折和接触。
```

问题：

当前四视角环境底层是 MotrixSim，MotrixSim 不支持 MuJoCo 的 `flexcomp`，因此 flex cloth 只能在 MuJoCo viewer 中单独测试，无法直接放入当前四视角环境。

结论：

```text
MuJoCo flex cloth 是效果较好的参考方案，但当前不能直接用于 MotrixSim 四视角环境。
```

#### 当前方案：单刚体软接触

当前四视角环境中采用稳定优先方案：

- `maojin`：单 box 碰撞 + 软接触；
- `yujin`：单刚体 + 20 个凸包碰撞块 + 软接触。

说明：

`yujin` 虽然有 20 个碰撞块，但它们都挂在同一个 body 下，所以仍然是单刚体，不会产生真实布料弯折，只是碰撞外形更贴近 visual mesh。

### 5. 尺寸匹配与统一参数表

问题：

Hunyuan3D 生成模型通常没有可靠的真实米制尺度，如果手动调 scale，后续维护非常困难。

当前方案：

建立统一参数表，记录每个操作物体的真实尺寸、质量、碰撞方式、分解块数和场景位置。脚本根据参数表自动计算 scale，并写入场景。

参数表：

```text
tools/operation_object_parameters.csv
```

易读说明：

```text
tools/operation_object_parameters.md
```

统一生成脚本：

```text
tools/prepare_nav_operation_objects.py
```

当前尺寸参数：

| 物体 | 目标尺寸 m | 碰撞方式 | 分解块数 |
|---|---:|---|---:|
| bottle | 0.066 x 0.066 x 0.235 | 单 mesh | 1 |
| lajitong | 0.260 x 0.260 x 0.320 | 凸包分解 | 20 |
| bianzhidai | 0.360 x 0.250 x 0.300 | 单 mesh | 1 |
| bag | 0.400 x 0.200 x 0.360 | 凸包分解 | 20 |
| maojin | 0.200 x 0.200 x 0.008 | 单 box 软接触 | 1 |
| yujin | 0.240 x 0.160 x 0.080 | 凸包分解软接触 | 20 |

后续修改尺寸、位置、质量、碰撞方式时，优先只修改：

```text
tools/operation_object_parameters.csv
```

然后重新运行生成脚本即可。

## 二、真实场景背景

### 1. 3DGS 重建 + mesh 生成 + cube 碰撞模拟

技术路线：

```text
真实场景采集
        ↓
3DGS 重建
        ↓
获得真实背景高斯表示
        ↓
生成或导出辅助 mesh
        ↓
根据高斯点 / mesh 生成 cube 碰撞近似
        ↓
接入 MotrixSim 背景碰撞
```

作用：

- 3DGS 负责真实背景视觉渲染；
- cube 或简化 mesh 负责背景物理碰撞；
- 操作物体作为动态 mesh 合成到四视角画面中。

主要问题：

- 高斯点本身不是物理碰撞体；
- cube 数量过多会影响性能；
- cube 太稀疏会导致碰撞不准；
- 需要保证视觉背景和碰撞体空间对齐。

### 2. 2DGS 重建 + mesh 生成 + cube 碰撞模拟

技术路线：

```text
真实场景采集
        ↓
2DGS 重建
        ↓
生成场景 mesh / 表面结构
        ↓
根据 mesh 或高斯点生成 cube 碰撞近似
        ↓
接入 MotrixSim 作为背景碰撞
```

潜在优势：

- 表面结构可能更适合 mesh 提取；
- 有利于从视觉重建结果生成物理碰撞近似；
- 可作为 3DGS 背景碰撞生成的替代路线。

仍需验证：

- 2DGS mesh 质量是否稳定；
- cube 碰撞粒度如何选择；
- 真实背景视觉和物理碰撞如何精确对齐。

## 三、当前操作指令

### 1. 根据参数表生成操作物体

```bash
cd /home/dw/RoboOS_Agent/FQPlanner
conda activate robocasa

python tools/prepare_nav_operation_objects.py
```

### 2. 启动四视角环境

```bash
cd /home/dw/RoboOS_Agent/FQPlanner
conda activate robocasa

./tools/run_xlerobot_nav_demo.sh
```

`run_xlerobot_nav_demo.sh` 已经固定默认环境变量和四视角启动参数，因此不需要每次手动输入很长的启动命令。

### 3. 单独测试 MuJoCo flex cloth

```bash
cd /home/dw/RoboOS_Agent/FQPlanner
conda activate robocasa

python -c "import mujoco.viewer; mujoco.viewer.launch_from_path('assets/scene_3dgs/towel_multibody_demo/towel_softcloth_drop_test.xml')"
```

## 四、当前结论

目前已经完成：

- 复现 FQPlanner compose 分支；
- 将 Hunyuan3D 操作物体导入四视角环境；
- 实现操作物体在四个小窗中的合成渲染；
- 完成 `bag / lajitong / yujin` 的 20 块凸包碰撞分解；
- 尝试并记录柔性布料多刚体分解失败原因；
- 验证 MuJoCo flex cloth 效果较好但不能直接用于 MotrixSim；
- 确定当前四视角环境中的布料近似方案为单刚体软接触；
- 建立统一尺寸参数表和一键生成脚本。

当前主线方案：

```text
Hunyuan3D visual mesh
        +
真实尺寸参数表自动缩放
        +
凸包分解 / box / mesh 碰撞
        +
MotrixSim 动力学
        +
3DGS 四视角合成渲染
```

后续主要工作：

- 实测真实物体尺寸并更新 CSV；
- 继续优化背景 3DGS / 2DGS 的碰撞生成；
- 如果 MotrixSim 后续支持软体或 flex，再迁移更真实的布料方案。
