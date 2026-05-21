# FQPlanner 使用指南

## 系统概述

FQPlanner 是基于"大脑-小脑"分层架构的 LLM 机器人任务规划系统，支持跨形态多机器人协作。

```
用户 → Web 控制台 (8888) → Master (5000) → Redis → Slaver
                                                       ↓
                                            MCP 工具调用 (stdio)
                                                       ↓
                                            OmniGibson Server (5001)
                                                       ↓
                                            Tiago 机器人仿真
```

- **Master**: LLM 任务规划，任务分解，经验学习
- **Slaver**: 任务执行，工具调用，场景监控
- **OmniGibson Server**: 仿真后端，物理模拟
- **Web 控制台**: 可视化管理界面

## 环境准备

### Conda 环境

本项目需要两个 Conda 环境：

```bash
# 环境 1: FQPlanner（Master/Slaver/Web 控制台）
conda create -n FQPlanner python=3.10
conda activate FQPlanner
pip install -r requirements.txt

# 环境 2: behavior（OmniGibson 仿真服务器）
# 已预装在 /home/fangqi/.conda/envs/behavior
```

### 配置 API Key

编辑 `.env` 文件：

```bash
CLOUD_API_KEY=your_api_key_here
```

当前使用阿里云 Qwen 模型（`qwen3.5-plus-2026-02-15`），API Key 从 `.env` 读取。

### 安装 Redis

```bash
# Ubuntu
sudo apt install redis-server

# 或直接运行
redis-server
```

## 启动系统

### 启动顺序

必须按以下顺序启动：

```
1. Redis  →  2. OmniGibson Server  →  3. Master  →  4. Slaver  →  5. Web Console
   (6379)        (5001)                  (5000)                     (8888)
```

### 1. 启动 Redis

```bash
redis-server
```

### 2. 启动 OmniGibson 仿真服务器

```bash
conda activate behavior
cd /home/fangqi/WorkXCJ/FQPlanner/serve

# 基础模式（只有家具）
python omnigibson_server.py Rs_int 5001

# 任务模式（推荐，有丰富物体）
python omnigibson_server.py Rs_int 5001 picking_up_trash
```

验证：
```bash
curl http://127.0.0.1:5001/status
curl http://127.0.0.1:5001/objects
```

### 3. 启动 Master

```bash
conda activate FQPlanner
cd /home/fangqi/WorkXCJ/FQPlanner
python master/run.py
```

Master 运行在 `http://127.0.0.1:5000`。

### 4. 启动 Slaver

```bash
conda activate FQPlanner
cd /home/fangqi/WorkXCJ/FQPlanner
python slaver/run.py
```

Slaver 启动后会：
1. 连接到 MCP 工具服务（skill.py）
2. 注册工具列表
3. 向 Master 注册机器人
4. 开始监听任务

### 5. 启动 Web 控制台（可选）

```bash
conda activate FQPlanner
cd /home/fangqi/WorkXCJ/FQPlanner
python deploy/run.py
```

访问 `http://127.0.0.1:8888`。

## 快速访问链接

系统启动后，可以直接访问以下链接：

| 链接 | 说明 |
|------|------|
| http://127.0.0.1:8888 | Web 控制台（主界面） |
| http://127.0.0.1:5001/camera/viewer | 观察者视角截图（PNG） |
| http://127.0.0.1:5001/camera/robot | 机器人视角截图（PNG） |
| http://127.0.0.1:5001/camera/top_down | 俯视跟随视角截图（PNG） |
| http://127.0.0.1:5001/camera/side | 侧面视角截图（PNG） |
| http://127.0.0.1:5001/objects | 查看场景物体（JSON） |
| http://127.0.0.1:5001/robot/state | 机器人状态（JSON） |
| http://127.0.0.1:5001/status | 服务器状态检查 |

## 使用 Web 控制台

### 发送任务

1. 打开 `http://127.0.0.1:8888`
2. 在输入框输入自然语言任务，例如：
   - "把笔记本电脑从早餐桌拿到咖啡桌上"
   - "打开冰箱"
   - "导航到早餐桌并抓取笔记本电脑"
   - "打扫厨房"
3. 点击发送

### 查看仿真画面

Web 控制台提供"刷新画面"按钮，点击后会：
1. 推进仿真一步
2. 捕获观察者视角截图
3. 显示在页面上

也可以直接访问：
- http://127.0.0.1:5001/camera/viewer （观察者视角 PNG）
- http://127.0.0.1:5001/camera/robot （机器人视角 PNG）
- http://127.0.0.1:5001/camera/top_down （俯视跟随视角 PNG）
- http://127.0.0.1:5001/camera/side （侧面视角 PNG）

### 录制视频

Web 控制台提供视频录制功能（1Hz）：
1. 点击"开始录制"
2. 执行任务
3. 点击"停止录制"，视频自动保存

录制文件保存在 `/home/fangqi/WorkXCJ/BEHAVIOR-1K/My_code/recordings/`

### 查看场景状态

Web 控制台会显示当前场景信息，包括：
- 桌子及其上物品
- 容器（冰箱、柜子等）
- 位置（厨房、卧室等）

## 可用工具

| 工具名 | 参数 | 说明 |
|--------|------|------|
| `navigate_to_target` | `target` | 导航到目标位置/物体（支持中英文） |
| `grasp_object` | `object_name` | 抓取物体（支持中英文） |
| `place_on_top` | `target_name` | 放在目标上面（支持中英文） |
| `place_inside` | `target_name` | 放入目标内部（支持中英文） |
| `open_object` | `target_name` | 打开物体 |
| `close_object` | `target_name` | 关闭物体 |
| `release_object` | 无 | 释放当前抓取的物体 |

## 中英文名称映射

OmniGibson 服务器支持中文物体名称，自动映射到英文：

| 中文 | 英文 | 中文 | 英文 |
|------|------|------|------|
| 早餐桌 | breakfast_table | 笔记本电脑 | laptop |
| 咖啡桌 | coffee_table | 杯子 | cup |
| 餐桌 | dining_table | 碗 | bowl |
| 冰箱 | fridge | 苹果 | apple |
| 垃圾桶 | trash_can | 书 | book |
| 柜子 | cabinet | 手机 | phone |

完整映射见 `serve/omnigibson_server.py` 中的 `ZH_EN_MAP` 字典。

## 场景配置

### 场景定义文件

`master/scene/profile.yaml` 定义了 FQPlanner 已知的场景信息：

```yaml
scene:
  - name: breakfast_table    # 物体名称
    type: table              # 类型：table/container/location
    position: [1.0, 2.0, 0.0]
    description: "早餐桌"     # 中文名称
    contains:                # 包含的物品
      - laptop
      - pot_plant
```

### 当前场景内容

| 名称 | 类型 | 说明 |
|------|------|------|
| breakfast_table | table | 早餐桌（含 laptop、pot_plant） |
| coffee_table | table | 咖啡桌 |
| countertop | table | 厨房台面 |
| fridge | container | 冰箱（可开关） |
| public_trash_can | container | 垃圾桶 |
| bottom_cabinet | container | 底柜（可开关） |
| top_cabinet | container | 顶柜（可开关） |
| microwave | container | 微波炉（可开关） |
| oven | container | 烤箱（可开关） |
| dishwasher | container | 洗碗机（可开关） |
| livingRoom | location | 客厅 |
| bedroom | location | 卧室 |
| kitchen | location | 厨房 |
| bathroom | location | 浴室 |
| entrance | location | 入口 |

### 加载 BEHAVIOR 任务（增加物体）

OmniGibson 服务器支持通过 API 加载 BEHAVIOR-1K 任务，加载后场景会自动添加任务所需的物体：

```bash
# 列出可用任务
curl http://127.0.0.1:5001/task/list

# 搜索相关任务
curl "http://127.0.0.1:5001/task/list?filter=cleaning"

# 加载任务
curl -X POST http://127.0.0.1:5001/task/load \
  -H "Content-Type: application/json" \
  -d '{"task_name": "picking_up_trash"}'
```

## 配置说明

### Master 配置 (`master/config.yaml`)

```yaml
model:
  model_select: "qwen3.5-plus-2026-02-15"   # LLM 模型
  model_dict:
    cloud_api_key: "${CLOUD_API_KEY}"         # 从 .env 读取
    cloud_server: "https://dashscope.aliyuncs.com/compatible-mode/v1/"
    max_chat_message: 50                       # 上下文长度

collaborator:
  host: "127.0.0.1"
  port: 6379                                   # Redis 端口
```

### Slaver 配置 (`slaver/config.yaml`)

```yaml
tool:
  support_tool_calls: true    # 启用工具调用
  matching:
    max_tools: 3              # 每次最多匹配 3 个工具
    min_similarity: 0.1       # 最小相似度阈值

robot:
  call_type: local            # local（stdio）或 remote（HTTP）
  name: FQrobot               # 机器人名称

omnigibson:
  server_url: "http://127.0.0.1:5001"   # OmniGibson 服务器地址
  timeout: 120                           # 请求超时（秒）
```

## 常见问题

### Slaver 启动报 ModuleNotFoundError

```
ModuleNotFoundError: No module named 'omnigibson_client'
```

确认 `slaver/robot/module/omnigibson_client.py` 存在，且模块内使用相对导入：
```python
from .omnigibson_client import call_omnigibson  # 正确
# from omnigibson_client import call_omnigibson  # 错误
```

### 网络连接失败

```
Network connection failed, falling back to TF-IDF matching
```

正常提示。无网络时会自动回退到 TF-IDF 关键词匹配（不需要 sentence-transformers）。

### 工具执行返回"物体不在场景中"

FQPlanner 发送的物体名称需要和 OmniGibson 场景中的匹配。检查：
1. `curl http://127.0.0.1:5001/objects` 看实际有哪些物体
2. `master/scene/profile.yaml` 里的名称是否一致
3. 考虑加载 BEHAVIOR 任务来增加物体
4. 中文名称已支持自动映射，见"中英文名称映射"章节

### OmniGibson 服务器连不上

1. 确认 OmniGibson 在 `behavior` 环境下启动
2. 确认端口 5001 没被占用
3. 确认 `slaver/config.yaml` 中 `omnigibson.server_url` 端口一致

### 相机截图空白

确保 OmniGibson 服务器已完成初始化（看到"服务器已启动"日志），然后点击"刷新画面"按钮。

## 文件结构

```
FQPlanner/
├── master/                   # Master 节点
│   ├── run.py                # 启动入口 (端口 5000)
│   ├── config.yaml           # 配置
│   ├── agents/               # 规划 Agent
│   │   ├── agent.py          # GlobalAgent
│   │   ├── planner.py        # 任务分解
│   │   └── prompts.py        # Prompt 模板
│   └── scene/
│       └── profile.yaml      # 场景定义
│
├── slaver/                   # Slaver 节点
│   ├── run.py                # 启动入口
│   ├── config.yaml           # 配置
│   ├── agents/
│   │   └── slaver_agent.py   # ToolCallingAgent (ReAct)
│   ├── robot/
│   │   ├── skill.py          # MCP 入口
│   │   └── module/           # 工具模块
│   │       ├── base.py       # 导航
│   │       ├── grasp.py      # 抓取
│   │       ├── place.py      # 放置/开关
│   │       └── omnigibson_client.py  # HTTP 客户端
│   └── tools/
│       ├── memory.py         # 场景记忆
│       ├── judge.py          # 失败判断
│       └── monitoring.py     # 日志监控
│
├── serve/                    # OmniGibson 仿真服务器
│   ├── omnigibson_server.py  # Flask + 仿真后端 (端口 5001)
│   └── README.md             # 服务器文档
│
├── deploy/                   # Web 控制台
│   ├── run.py                # Flask (端口 8888)
│   └── templates/
│       └── index.html        # 前端页面
│
├── .env                      # API Key
└── requirements.txt          # 依赖
```

## 任务示例

以下是在 Web 控制台 (`http://127.0.0.1:8888`) 中可以输入的任务示例。

### 当前场景物体

| 物体 | 位置 | 说明 |
|------|------|------|
| breakfast_table | [1.47, 0.42, 0.60] | 早餐桌 |
| coffee_table | [-0.48, -1.22, 0.27] | 咖啡桌（含 laptop） |
| dining_table | [-0.50, -2.00, 0.00] | 餐桌 |
| countertop | [-0.81, 1.53, 1.06] | 料理台 |
| fridge | [0.10, 3.15, 0.74] | 冰箱 |
| microwave | [-1.78, 3.12, 1.46] | 微波炉 |
| oven | [-1.66, 2.14, 0.60] | 烤箱 |
| dishwasher | [-1.80, 3.13, 1.07] | 洗碗机 |
| public_trash_can | [-1.76, 2.63, 0.21] | 垃圾桶 |
| bottom_cabinet | 多个位置 | 底柜 |
| top_cabinet | 多个位置 | 吊柜 |
| laptop | [-0.58, -1.51, 0.43] | 笔记本电脑（在咖啡桌上） |

---

### 示例 1：抓取并移动物体

**输入：**
```
把笔记本电脑从咖啡桌拿到早餐桌上
```

**LLM 自动分解为：**
1. `navigate_to_target("coffee_table")` — 导航到咖啡桌
2. `grasp_object("laptop")` — 抓取笔记本电脑
3. `navigate_to_target("breakfast_table")` — 导航到早餐桌
4. `place_on_top("breakfast_table")` — 把笔记本电脑放在早餐桌上

**预期结果：** 笔记本电脑从咖啡桌被移到早餐桌

---

### 示例 2：打开冰箱

**输入：**
```
打开冰箱
```

**LLM 自动分解为：**
1. `navigate_to_target("fridge")` — 导航到冰箱
2. `open_object("fridge")` — 打开冰箱门

**预期结果：** 冰箱门被打开

---

### 示例 3：把笔记本电脑放进微波炉

**输入：**
```
把笔记本电脑放进微波炉里
```

**LLM 自动分解为：**
1. `navigate_to_target("coffee_table")` — 导航到咖啡桌
2. `grasp_object("laptop")` — 抓取笔记本电脑
3. `navigate_to_target("microwave")` — 导航到微波炉
4. `place_inside("microwave")` — 放入微波炉

**预期结果：** 笔记本电脑被放入微波炉

---

### 示例 4：多步厨房操作

**输入：**
```
去厨房打开微波炉，然后把咖啡桌上的笔记本电脑放进去，最后关上微波炉
```

**LLM 自动分解为：**
1. `navigate_to_target("kitchen")` — 导航到厨房
2. `open_object("microwave")` — 打开微波炉
3. `navigate_to_target("coffee_table")` — 导航到咖啡桌
4. `grasp_object("laptop")` — 抓取笔记本电脑
5. `navigate_to_target("microwave")` — 导航回微波炉
6. `place_inside("microwave")` — 把笔记本电脑放入微波炉
7. `close_object("microwave")` — 关上微波炉

**预期结果：** 微波炉被打开，笔记本电脑被放入，微波炉被关闭

---

### 示例 5：简单导航

**输入：**
```
去客厅
```

**LLM 自动分解为：**
1. `navigate_to_target("livingRoom")` — 导航到客厅

**预期结果：** 机器人移动到客厅位置

---

### 示例 6：丢弃物品

**输入：**
```
把咖啡桌上的笔记本电脑扔到垃圾桶里
```

**LLM 自动分解为：**
1. `navigate_to_target("coffee_table")` — 导航到咖啡桌
2. `grasp_object("laptop")` — 抓取笔记本电脑
3. `navigate_to_target("public_trash_can")` — 导航到垃圾桶
4. `place_inside("public_trash_can")` — 放入垃圾桶

**预期结果：** 笔记本电脑从咖啡桌被丢进垃圾桶

---

### 示例 7：放入底柜

**输入：**
```
把笔记本电脑放进底柜里
```

**LLM 自动分解为：**
1. `navigate_to_target("coffee_table")` — 导航到咖啡桌
2. `grasp_object("laptop")` — 抓取笔记本电脑
3. `navigate_to_target("bottom_cabinet")` — 导航到底柜
4. `place_inside("bottom_cabinet")` — 放入底柜

**预期结果：** 笔记本电脑被放入底柜

---

### 提示

- 使用中文或英文均可，LLM 会自动理解
- 物体名称支持中英文自动映射（如"笔记本电脑" → "laptop"）
- 复杂任务会被自动分解为多个子任务，按顺序执行
- 如果某个子任务失败，LLM 会尝试重试或调整方案
- 每次只能抓取一个物体，需要先放下当前的才能抓新的
- 点击"刷新画面"按钮可以查看仿真状态
- 当前场景中 laptop 在 coffee_table 上，可直接抓取
