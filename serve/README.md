# OmniGibson Server

OmniGibson 仿真服务器，为 FQPlanner 提供机器人仿真执行后端。

## 功能概述

- **场景管理**: 加载 Rs_int 场景，管理物体状态
- **机器人控制**: 导航、抓取、放置、开关物体等操作
- **相机系统**: 观察者视角和机器人视角截图
- **视频录制**: 1Hz 录制任务执行过程
- **中英文支持**: 物体名称支持中英文自动映射

## 环境要求

```bash
conda activate behavior
```

依赖: omnigibson, flask, torch, numpy, opencv-python

## 首次使用

### 1. 获取场景数据

```bash
cd /home/fangqi/WorkXCJ/FQPlanner/serve
conda activate behavior
python get_scene_data.py
```

生成 `profile.yaml`（场景物体配置）。

### 2. 启动服务器

```bash
python omnigibson_server.py
```

服务器从 `profile.yaml` 加载物体到仿真器。

## API 端点

### 状态查询
| 端点 | 方法 | 说明 |
|------|------|------|
| `/status` | GET | 健康检查 |
| `/objects` | GET | 列出场景物体 |
| `/robot/state` | GET | 机器人状态 |

### 任务管理
| 端点 | 方法 | 说明 |
|------|------|------|
| `/task/list` | GET | 列出可用任务 |
| `/task/current` | GET | 当前任务信息 |
| `/task/load` | POST | 加载/切换任务 |
| `/scene/profile` | GET | 场景 profile 数据 |
| `/scene/profile/save` | POST | 保存当前场景数据 |

### 机器人操作
| 端点 | 方法 | 说明 |
|------|------|------|
| `/action/navigate` | POST | 导航到目标位置 |
| `/action/grasp` | POST | 抓取物体 |
| `/action/place_on_top` | POST | 放在物体上面 |
| `/action/place_inside` | POST | 放入物体内部 |
| `/action/open` | POST | 打开物体 |
| `/action/close` | POST | 关闭物体 |
| `/action/release` | POST | 释放物体 |

### 相机与录制
| 端点 | 方法 | 说明 |
|------|------|------|
| `/camera/viewer` | GET | 观察者视角截图 |
| `/camera/robot` | GET | 机器人视角截图 |
| `/camera/top_down` | GET | 俯视视角截图 |
| `/camera/viewer_base64` | GET | 观察者视角（base64） |
| `/camera/robot_base64` | GET | 机器人视角（base64） |
| `/camera/top_down_base64` | GET | 俯视视角（base64） |
| `/record/start` | POST | 开始录制 |
| `/record/stop` | POST | 停止录制 |

## 当前场景物体

基于 `profile.yaml` 配置：

| 名称 | 类型 | 位置 | 说明 |
|------|------|------|------|
| breakfast_table | table | [0.5, 0.0, 0.0] | 早餐桌（含 laptop, cup） |
| coffee_table | table | [-1.5, -1.0, 0.0] | 咖啡桌（含 book） |
| dining_table | table | [-0.5, -2.0, 0.0] | 餐桌（含 bowl） |
| countertop | table | [2.0, 0.5, 0.9] | 料理台 |
| fridge | container | [2.5, 0.0, 0.0] | 冰箱 |
| microwave | container | [2.0, 0.8, 0.9] | 微波炉 |
| trash_can | container | [1.5, -1.5, 0.0] | 垃圾桶 |
| bottom_cabinet | container | [2.0, -0.5, 0.0] | 底柜 |
| top_cabinet | container | [2.0, -0.5, 0.9] | 吊柜 |
| laptop | object | [0.5, 0.0, 0.82] | 笔记本电脑 |
| cup | object | [0.3, 0.2, 0.82] | 杯子 |
| book | object | [-1.5, -1.0, 0.52] | 书 |
| bowl | object | [-0.5, -2.0, 0.77] | 碗 |
| apple | object | [0.6, -0.15, 0.82] | 苹果 |

## 中英文映射

| 中文 | 英文 |
|------|------|
| 早餐桌 | breakfast_table |
| 咖啡桌 | coffee_table |
| 笔记本电脑 | laptop |
| 冰箱 | fridge |
| 垃圾桶 | trash_can |
| 杯子 | cup |
| 苹果 | apple |

## 使用示例

```bash
# 查看场景物体
curl http://127.0.0.1:5001/objects

# 导航到早餐桌
curl -X POST http://127.0.0.1:5001/action/navigate \
  -H "Content-Type: application/json" \
  -d '{"target_name": "breakfast_table"}'

# 截图
curl http://127.0.0.1:5001/camera/viewer -o screenshot.png

# 保存场景数据
curl -X POST http://127.0.0.1:5001/scene/profile/save
```

## 文件说明

```
serve/
├── omnigibson_server.py   # 主服务器
├── get_scene_data.py      # 场景数据提取脚本
├── profile.yaml           # 场景配置
└── README.md              # 本文档
```

## 注意事项

1. **首次使用**: 必须先运行 `get_scene_data.py` 或手动创建 `profile.yaml`
2. **线程安全**: 所有仿真操作通过主线程队列执行
3. **无头模式**: 默认 `OMNIGIBSON_HEADLESS=True`
4. **GPU 内存**: RTX 3070 8GB 可能需要关闭其他 GPU 应用
