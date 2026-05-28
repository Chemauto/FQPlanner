# FQPlanner 使用指南

## 启动系统

按以下顺序启动：

```
1. Redis (6379)  →  2. 仿真后端 (5001)  →  3. Master (5000)  →  4. Slaver  →  5. Web 控制台 (8888)
```

### 1. 启动 Redis

```bash
redis-server
```

### 2. 启动 RoboCasa 仿真后端

```bash
conda activate robocasa
cd /home/fangqi/WorkXCJ/FQPlanner/serve
python sim.py
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

### 4. 启动 Slaver

```bash
conda activate FQPlanner
cd /home/fangqi/WorkXCJ/FQPlanner
python slaver/run.py
```

### 5. 启动 Web 控制台（可选）

```bash
cd /home/fangqi/WorkXCJ/FQPlanner
python deploy/run.py
```

访问 `http://127.0.0.1:8888`

---

## 快速访问

| 链接 | 说明 |
|------|------|
| http://127.0.0.1:8888 | Web 控制台 |
| http://127.0.0.1:5001/status | 仿真状态 |
| http://127.0.0.1:5001/objects | 场景物体列表 |
| http://127.0.0.1:5001/arm_status | 机械臂状态 |

---

## 可用工具

| 工具 | 参数 | 说明 |
|------|------|------|
| `navigate_to_target` | `target` (坐标) | 导航底盘，如 `"(1.5, -0.5)"` |
| `grasp_object` | `object_name` | 抓取物体 |
| `place_on_top` | `obj_name`, `target_name` | 放到目标物体上方 |
| `place_object` | `obj_name`, `x`, `y`, `z` | 放到指定坐标 |
| `release_object` | 无 | 释放当前抓取的物体 |

---

## 文件结构

```
FQPlanner/
├── master/              # Master（任务规划）
│   ├── run.py           # 启动入口 (5000)
│   └── config.yaml
├── slaver/              # Slaver（任务执行）
│   ├── run.py           # 启动入口
│   ├── config.yaml
│   └── robot/module/    # 技能模块（调用 serve.sim）
├── serve/               # RoboCasa 仿真服务
│   ├── main.py          # 启动入口 (5001)
│   ├── sim.py           # 仿真接口
│   ├── tools/           # arm.py, move.py
│   ├── service/         # server.py, web.py
│   └── scene/           # 场景配置
├── deploy/              # Web 控制台 (8888)
└── .env                 # API Key
```

---

## 配置

`.env` 文件：
```
CLOUD_API_KEY=your_api_key_here
```

`slaver/config.yaml` 中 `robocasa.server_url` 需指向仿真服务地址（默认 `http://127.0.0.1:5001`）。
