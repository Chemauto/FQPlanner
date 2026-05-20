# OmniGibson Server

OmniGibson 仿真服务器，为 FQPlanner 提供机器人仿真执行后端。

## 功能概述

- **场景管理**: 加载 BEHAVIOR-1K 任务场景，管理物体状态
- **机器人控制**: 导航、抓取、放置、开关物体等操作
- **相机系统**: 观察者视角和机器人视角截图
- **视频录制**: 1Hz 录制任务执行过程
- **中英文支持**: 物体名称支持中英文自动映射

## 环境要求

### Conda 环境

```bash
# 激活 behavior 环境（包含 OmniGibson）
conda activate behavior
```

### 依赖包

- omnigibson >= 3.7
- flask
- torch
- numpy
- opencv-python (cv2)

## 启动服务器

```bash
# 进入 serve 目录
cd /home/fangqi/WorkXCJ/FQPlanner/serve

# 激活环境
conda activate behavior

# 启动服务器（默认端口 5001）
python omnigibson_server.py

# 或指定场景和端口
python omnigibson_server.py Rs_int 5001

# 或加载特定任务
python omnigibson_server.py Rs_int 5001 picking_up_trash
```

启动后访问: http://127.0.0.1:5001

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
| `/camera/viewer` | GET | 观察者视角截图 (PNG) |
| `/camera/robot` | GET | 机器人视角截图 (PNG) |
| `/camera/viewer_base64` | GET | 观察者视角截图 (Base64) |
| `/camera/robot_base64` | GET | 机器人视角截图 (Base64) |
| `/record/start` | POST | 开始录制 |
| `/record/stop` | POST | 停止录制并保存 |
| `/record/status` | GET | 录制状态 |

### 仿真控制

| 端点 | 方法 | 说明 |
|------|------|------|
| `/sim/step` | POST | 推进仿真步 |
| `/sim/step_and_capture` | POST | 步进并截图 |

## 使用示例

### Python 客户端

```python
from omnigibson_client import call_omnigibson

# 导航到早餐桌
result = call_omnigibson("/action/navigate", {"target_name": "breakfast_table"})

# 抓取笔记本电脑
result = call_omnigibson("/action/grasp", {"object_name": "laptop"})

# 放在咖啡桌上
result = call_omnigibson("/action/place_on_top", {"target_name": "coffee_table"})
```

### curl 命令

```bash
# 查看场景物体
curl http://127.0.0.1:5001/objects

# 导航
curl -X POST http://127.0.0.1:5001/action/navigate \
  -H "Content-Type: application/json" \
  -d '{"target_name": "breakfast_table"}'

# 截图
curl http://127.0.0.1:5001/camera/viewer -o screenshot.png
```

## 中英文名称映射

服务器支持中文物体名称，自动映射到英文：

| 中文 | 英文 |
|------|------|
| 早餐桌 | breakfast_table |
| 咖啡桌 | coffee_table |
| 笔记本电脑 | laptop |
| 冰箱 | fridge |
| 垃圾桶 | trash_can |
| 杯子 | cup |
| 苹果 | apple |

完整映射见 `omnigibson_server.py` 中的 `ZH_EN_MAP` 字典。

## 与 FQPlanner 集成

FQPlanner 的 Web 控制台 (http://127.0.0.1:8888) 可以：

1. **查看仿真画面** - 点击"刷新画面"按钮
2. **录制视频** - 开始/停止录制任务执行
3. **发布任务** - 通过 Master 下发到 Slaver 执行

## 文件说明

```
serve/
├── omnigibson_server.py  # 主服务器
└── README.md             # 本文档
```

## 注意事项

1. **线程安全**: 所有仿真操作通过主线程队列执行，Flask 在后台线程运行
2. **无头模式**: 默认启用 `OMNIGIBSON_HEADLESS=True`，不打开仿真器界面
3. **GPU 加速**: 使用 `ENABLE_FLATCACHE=True` 优化性能
4. **录制路径**: 视频保存到 `/home/fangqi/WorkXCJ/BEHAVIOR-1K/My_code/recordings/`

## 故障排查

### 服务器启动失败

```bash
# 检查 OmniGibson 是否正确安装
conda activate behavior
python -c "import omnigibson; print(omnigibson.__version__)"

# 检查端口是否被占用
lsof -i :5001
```

### 相机截图空白

确保服务器已完成初始化（看到"服务器已启动"日志），然后调用 `/sim/step` 推进仿真。

### 物体找不到

使用 `/objects` 端点查看场景中实际存在的物体名称和类别。
