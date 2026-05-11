# FQPlanner

FQPlanner 是基于"大脑-小脑"分层架构的机器人操作系统，通过大语言模型实现跨形态多机器人协作。

**核心功能**
- **底盘导航** - 模拟底盘导航与位置追踪
- **远程通信** - 网络化机器人协作
- **Web 控制台** - 可视化任务发布与系统管理

## 快速入门

### 1. 环境要求

- Python 3.10+
- Conda
- Redis 服务

### 2. 安装

```bash
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
  cloud_api_key: "sk-xxxxxxxxxxxxxxx"  # 替换为你的 API Key
  cloud_server: "https://dashscope.aliyuncs.com/compatible-mode/v1/"
```

### 4. 启动 Redis

```bash
redis-server
```

### 5. 运行系统

在 2 个独立终端中分别启动：

```bash
# 终端 1 - Master
conda activate FQPlanner
python master/run.py

# 终端 2 - Slaver
python slaver/run.py
```

### 6. 发布任务

**方式一：Web 控制台（推荐）**

```bash
# 终端 3
python deploy/run.py
```

访问 http://127.0.0.1:8888 ，在页面中输入任务。

**方式二：API 调用**

```bash
curl -X POST http://127.0.0.1:5000/publish_task -H "Content-Type: application/json" -d "{\"task\": \"前往卧室\"}"
```

**任务示例：**
- "前往卧室" / "到客厅"
- "先去厨房，然后去卧室"

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
│   └── run.py                #   启动脚本
│
├── slaver/                   # Slaver 节点（任务执行）
│   ├── agents/               #   执行 Agent
│   ├── robot/module/         #   机器人功能模块
│   └── run.py                #   启动脚本
│
├── deploy/                   # Web 控制台
│   ├── run.py                #   Flask 后端
│   └── templates/index.html  #   前端页面
│
├── grasp_server.py           # 抓取服务器
└── requirements.txt          # Python 依赖
```

## 项目感谢

本项目基于 [FlagScale](https://github.com/flagos-ai/FlagScale) 和 [RoboOS](https://github.com/FlagOpen/RoboOS) 进行开发。
