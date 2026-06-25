# 操作物体参数表说明

脚本读取的参数源是 `operation_object_parameters.csv`。这个 Markdown 文件只用于人工快速查看。

| 物体 | link | 目标真实尺寸 m | 质量 kg | 碰撞方式 | 分解块数 | 场景位置 | 说明 |
|---|---|---:|---:|---|---:|---|---|
| bottle | hunyuan_bottle_body | 0.066 x 0.066 x 0.235 | 0.20 | 单 mesh | 1 | 0.0 1.2 0.1400000 | 常见 500ml 瓶子估计 |
| lajitong | hunyuan_lajitong_body | 0.260 x 0.260 x 0.320 | 0.35 | 凸包分解 | 20 | -0.45 1.2 0.258493105 | 小型桌面垃圾桶估计 |
| bianzhidai | hunyuan_bianzhidai_body | 0.360 x 0.250 x 0.300 | 0.15 | 单 mesh | 1 | 0.45 -1.2 0.303874049 | 小型编织袋/收纳袋估计 |
| bag | hunyuan_bag_convex_body | 0.400 x 0.200 x 0.360 | 0.25 | 凸包分解 | 20 | 0.72 0.0 0.005 | 中小型手提包/软包估计 |
| maojin | hunyuan_maojin_body | 0.200 x 0.200 x 0.008 | 0.06 | 单 box 软接触 | 1 | 0.720000 0.000000 0.420000 | 20cm x 20cm x 8mm 硬毛巾测试件 |
| yujin | hunyuan_yujin_body | 0.240 x 0.160 x 0.080 | 0.35 | 凸包分解软接触 | 20 | -0.720000 0.000000 0.000000 | 24cm x 16cm x 8cm 折叠浴巾实体 |

注意：

- 这些尺寸是先按常见真实物体给出的第一版估计值，后续可以直接改 `operation_object_parameters.csv`。
- `target_size_m` 的三个数对应模型本地 X/Y/Z 方向，生成脚本会自动根据原始 mesh 包围盒计算 `scale`。
- `bag`、`lajitong`、`yujin` 会自动生成 20 个凸包碰撞块；visual mesh 仍然只有一个，并会进入四视角小窗合成渲染。
- `yujin` 的 20 个碰撞块都在同一个刚体 body 下，因此它仍然是单刚体，只是碰撞外形更贴合。
