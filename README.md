# FQPlanner

FQPlanner 是基于"大脑-小脑"分层架构的机器人操作系统，通过大语言模型实现跨形态多机器人协作。

**核心功能**
- **任务规划** - LLM 自动分解复杂任务为子任务序列
- **仿真执行** - OmniGibson 物理仿真后端，支持导航、抓取、放置等操作
- **Web 控制台** - 可视化任务发布、场景查看、视频录制
- **中英文支持** - 物体名称支持中英文自动映射

## 快速入门

### 1. 环境要求

- Python 3.10+
- Conda
- Redis 服务
- OmniGibson（仿真模式）

### 2. 安装

```bash
git clone https://github.com/Chemauto/FQPlanner.git
cd FQPlanner

# 创建 FQPlanner 环境（Master/Slaver/Web 控制台）
conda create -n FQPlanner python=3.10
conda activate FQPlanner
pip install -r requirements.txt
```

### 3. 模型配置

修改 `master/config.yaml` 和 `slaver/config.yaml` 中的 `model_select` 字段。

```yaml
model_select: "qwen-plus"

model_dict:
  cloud_model: "qwen-plus"
  cloud_type: "default"
  cloud_api_key: "CLOUD_API_KEY"
  cloud_server: "https://dashscope.aliyuncs.com/compatible-mode/v1/"
```

新建 `.env` 文件，写入 API Key：
```bash
CLOUD_API_KEY=sk-xxxxxxxxxxxxxxx
```

### 4. 启动 Redis

```bash
redis-server
```

### 5. 运行系统

需要 3-4 个独立终端：

```bash
# 终端 1 - OmniGibson 仿真服务器（behavior 环境）
conda activate behavior
cd serve
python omnigibson_server.py Rs_int 5001 picking_up_trash

# 终端 2 - Master（FQPlanner 环境）
conda activate FQPlanner
python master/run.py

# 终端 3 - Slaver（FQPlanner 环境）
conda activate FQPlanner
python slaver/run.py

# 终端 4 - Web 控制台（可选，FQPlanner 环境）
conda activate FQPlanner
python deploy/run.py
```

### 6. 发布任务

访问 http://127.0.0.1:8888 ，在页面中输入任务。

**任务示例：**
- "把 laptop 从早餐桌拿到咖啡桌上"
- "打开冰箱"
- "先去厨房，然后去卧室"
- "抓取早餐桌上的笔记本电脑放到咖啡桌上"

### 7. 查看日志

```bash
tail -f master/.logs/master_agent.log  # Master 日志
tail -f slaver/.log/agent.log          # Slaver 日志
```

## 项目结构

```
FQPlanner/
├── agent/                    # 协作通信与工具匹配
│   ├── collaboration/        #   Redis 通信（Master-Slaver 消息）
│   └── tool_match/           #   语义工具匹配引擎
│
├── master/                   # Master 节点（任务规划）
│   ├── agents/               #   规划 Agent
│   ├── scene/                #   场景配置
│   └── run.py                #   启动脚本 (端口 5000)
│
├── slaver/                   # Slaver 节点（任务执行）
│   ├── agents/               #   执行 Agent
│   ├── robot/module/         #   机器人功能模块
│   │   ├── base.py           #     导航
│   │   ├── grasp.py          #     抓取
│   │   ├── place.py          #     放置/开关
│   │   └── omnigibson_client.py  # OmniGibson HTTP 客户端
│   └── run.py                #   启动脚本
│
├── serve/                    # OmniGibson 仿真服务器
│   ├── omnigibson_server.py  #   Flask + 仿真后端 (端口 5001)
│   └── README.md             #   服务器文档
│
├── deploy/                   # Web 控制台
│   ├── run.py                #   Flask 后端 (端口 8888)
│   └── templates/index.html  #   前端页面
│
├── .env                      # API Key
└── requirements.txt          # Python 依赖
```

## Conda 环境

| 环境 | 用途 | 包含 |
|------|------|------|
| `FQPlanner` | Master、Slaver、Web 控制台 | flask, redis, requests, pyyaml |
| `behavior` | OmniGibson 仿真服务器 | omnigibson, torch, flask |

## 文档

- [使用指南](usage.md) - 详细使用说明
- [OmniGibson 服务器](serve/README.md) - 仿真后端文档
- [Master 节点](master/README.md) - 任务规划模块
- [Slaver 节点](slaver/README.md) - 任务执行模块
- [Agent 模块](agent/README.md) - 通信与工具匹配

## 项目感谢

本项目基于 [FlagScale](https://github.com/flagos-ai/FlagScale) 和 [RoboOS](https://github.com/FlagOpen/RoboOS) 进行开发。
