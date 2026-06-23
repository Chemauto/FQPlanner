# 毛巾半尺寸调整前记录

记录时间：2026-06-23

本记录对应将毛巾长宽缩小为一半之前的场景状态，用作后续对比和回退参考。

## 调整前参数

- `cols`: `20`
- `rows`: `15`
- `length`: `0.6`
- `width`: `0.3`
- `mass`: `0.12`
- `young`: `50000`
- `damping`: `0.4`
- `thickness`: `0.01`
- `radius`: `0.003`
- `edge_equality`: `True`
- `elastic2d`: `bend`
- `bag_scale`: `0.5`
- bag collision `friction`: `0.8 0.05 0.01`
- 毛巾贴图：`visual/texture_pbr_20250901_roughness.png`

## 当前现象判断

毛巾在 MuJoCo viewer 中用 `Ctrl+右键` 拖拽时显得很难举起来，主要可疑原因不是总质量，而是约束和刚度叠加：

- `20 x 15` 会生成 300 个 flex 节点，节点和边约束数量明显增加。
- `edge equality` 会强力抑制边长变化，能减少拉伸，但也会让局部拖拽更像在拖一整张受约束的网。
- `mujoco.elasticity.shell` 中 `young=50000`、`thickness=0.01` 会提供较强的 shell 弯曲/面内刚度。
- viewer 的鼠标扰动通常作用在局部选中的 body/节点上，不等价于真实夹爪托住整片布，因此高约束布料会显得特别“沉”和“硬”。

## 本次调整目标

保持当前质量和材料参数不变，仅将毛巾几何长宽缩小为一半：

- `length`: `0.6` -> `0.3`
- `width`: `0.3` -> `0.15`

这样可以单独观察尺寸缩小对 viewer 交互手感、接触区域和布料形变的影响。
