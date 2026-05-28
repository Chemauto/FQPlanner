# Slaver - 任务执行节点

"小脑"模块，负责连接机器人、接收子任务、匹配工具并执行，将结果和场景变化回传给 Master。

## 目录结构

```
slaver/
├── run.py              # 启动入口（MCP 连接、Redis 监听、任务分发）
├── config.yaml         # 配置文件（API key 通过 ${CLOUD_API_KEY} 从 .env 读取）
├── agents/
│   ├── slaver_agent.py # ToolCallingAgent - ReAct 循环、工具执行、judge 决策
│   └── models.py       # LLM 模型客户端（OpenAI / Azure 兼容）
├── tools/
│   ├── tool_matcher.py # 语义工具匹配（TF-IDF / sentence-transformers）
│   ├── utils.py        # 配置加载（支持 ${ENV_VAR} 替换）
│   ├── memory.py       # SceneMemory - 场景状态管理（add/remove/move）
│   ├── judge.py        # 失败判定（retry/skip/terminate）
│   ├── monitoring.py   # 日志 + SceneDetector 场景变化检测器
│   └── state_decorator.py
└── robot/
    ├── skill.py        # MCP 服务器入口，注册所有工具模块
    └── module/
        ├── base.py     # navigate_to_target 工具（导航，坐标格式）
        ├── grasp.py    # grasp_object 工具（抓取）
        ├── place.py    # place_on_top / place_object 工具（放置）
        └── example.py  # 示例模板
```

## 启动

```bash
conda activate FQPlanner
cd /home/fangqi/WorkXCJ/FQPlanner

# 确保 .env 中配置了 CLOUD_API_KEY
# 确保 Master 已启动
python slaver/run.py
```

## 配置

编辑 `config.yaml`，主要配置项：

- **model.model_select** — LLM 模型（如 qwen3.6-35b-a3b）
- **model.model_dict.cloud_api_key** — API key（通过 `${CLOUD_API_KEY}` 从 `.env` 读取）
- **collaborator** — Redis 连接信息（需与 Master 一致）
- **robot.call_type** — `local`（本地 MCP）或 `remote`（远程 HTTP）
- **robot.path** — 本地目录名或远程 URL
- **robot.name** — 机器人名称（如 FQrobot）
- **tool.matching** — 工具匹配配置（max_tools、min_similarity）
- **robocasa.server_url** — RoboCasa 仿真服务器地址（默认 http://127.0.0.1:5001）

## 工作流程

```
启动 → MCP 连接机器人 → 获取工具列表 → 注册到 Master
    → 启动 SceneDetector（场景变化检测）
    → 监听 fqplanner_to_{robot_name} 频道
    → 收到任务 → ToolMatcher 匹配相关工具
    → ReAct 循环：
        LLM 决策 → 执行工具 → 解析结果
        ├─ 成功 → 更新场景状态 → 继续/结束
        └─ 失败 → judge_on_failure()
                   ├─ retry → 重试（最多 3 次）
                   ├─ skip → 跳过子任务
                   └─ terminate → 终止整个任务
    → 回传结果 + scene_changes 给 Master
```

## 工具模块

所有模块通过 `serve/sim.py` 调用 RoboCasa 仿真 API。

### base.py - 导航

| 工具 | 参数 | 说明 |
|------|------|------|
| `navigate_to_target` | `target` | 导航到目标坐标，格式 `"(x, y)"` |

### grasp.py - 抓取

| 工具 | 参数 | 说明 |
|------|------|------|
| `grasp_object` | `object_name` | 抓取物体（如 "mug"、"apple"） |

### place.py - 放置

| 工具 | 参数 | 说明 |
|------|------|------|
| `place_on_top` | `obj_name`, `target_name` | 放到目标物体上方 |
| `place_object` | `obj_name`, `x`, `y`, `z` | 放到指定坐标 |

## 场景变化检测（SceneDetector）

`monitoring.py` 中的 `SceneDetector` 类以后台线程运行，定期读取 Redis 场景状态并检测变化：

- 启动时拍摄场景快照作为基准（baseline）
- 每 2 秒对比当前场景与基准快照
- 检测新增物体（added）和消失物体（removed）
- 检测到变化后更新基准，避免重复报告

## 添加新工具模块

1. 在 `robot/module/` 下创建新文件
2. 实现 `register_tools(mcp)` 函数，用 `@mcp.tool()` 装饰器注册工具
3. 在 `robot/module/__init__.py` 中导入
4. 重启 Slaver

```python
# robot/module/my_tool.py
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from serve.sim import call_sim

def register_tools(mcp):
    @mcp.tool()
    async def my_tool(param: str) -> str:
        """工具描述"""
        result = call_sim("/my_endpoint", {"param": param})
        return result.get("result", "失败")
```

## 依赖

- FQPlanner conda 环境
- Redis 服务
- RoboCasa 仿真服务器（serve/main.py）
