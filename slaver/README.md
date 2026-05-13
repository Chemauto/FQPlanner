# Slaver - 任务执行节点

"小脑"模块，负责连接机器人、接收子任务、匹配工具并执行，将结果和场景变化回传给 Master。

## 目录结构

```
slaver/
├── run.py              # 启动入口（MCP 连接、Redis 监听、任务分发、场景模拟与检测）
├── config.yaml         # 配置文件（API key 通过 ${CLOUD_API_KEY} 从 .env 读取）
├── agents/
│   ├── slaver_agent.py # ToolCallingAgent - ReAct 循环、工具执行、judge 决策
│   └── models.py       # LLM 模型客户端（OpenAI / Azure 兼容）
├── tools/
│   ├── tool_matcher.py # 语义工具匹配（TF-IDF / sentence-transformers）
│   ├── utils.py        # 配置加载（支持 ${ENV_VAR} 替换）
│   ├── memory.py       # SceneMemory - 场景状态管理（add/remove/move）
│   ├── judge.py        # 失败判定（retry/skip/terminate）
│   ├── SceneChange.py  # 场景变化模拟（后台随机增减物体，部署时注释掉）
│   ├── monitoring.py   # 日志 + SceneDetector 场景变化检测器
│   └── state_decorator.py
└── robot/
    ├── skill.py        # MCP 服务器入口，注册所有工具模块
    ├── skill_remote.py # 远程 MCP 服务器
    └── module/
        ├── base.py     # navigate_to_target / move 工具
        ├── grasp.py    # grasp_object 工具（模拟抓取）
        ├── swap.py     # clean_area 工具（模拟打扫）
        └── example.py  # 示例模板
```

## 启动

```bash
# 确保 .env 中配置了 CLOUD_API_KEY
python slaver/run.py
```

## 配置

编辑 `config.yaml`，主要配置项：

- **model.model_select** — LLM 模型（如 qwen3.5-plus-2026-02-15）
- **model.model_dict.cloud_api_key** — API key（通过 `${CLOUD_API_KEY}` 从 `.env` 读取）
- **collaborator** — Redis 连接信息（需与 Master 一致）
- **robot.call_type** — `local`（本地 MCP）或 `remote`（远程 HTTP）
- **robot.path** — 本地目录名或远程 URL
- **robot.name** — 机器人名称（如 FQrobot）
- **tool.matching** — 工具匹配配置（max_tools、min_similarity）
- **profiling** — 是否输出详细调试信息（true/false）

## 工作流程

```
启动 → MCP 连接机器人 → 获取工具列表 → 注册到 Master
    → 启动 SceneChanger（场景模拟，部署时禁用）
    → 启动 SceneDetector（场景变化检测）
    → 监听 fqplanner_to_{robot_name} 频道
    → 收到任务 → ToolMatcher 匹配相关工具
    → ReAct 循环：
        LLM 决策 → 执行工具 → 解析结果
        ├─ 成功 → 更新场景状态 → 继续/结束
        └─ 失败 → judge_on_failure()
                   ├─ retry（>0.4）→ 重试（最多 3 次）
                   ├─ skip（0.1~0.4）→ 跳过子任务
                   └─ terminate（<0.1）→ 终止整个任务
    → 回传结果 + scene_changes 给 Master
```

## 场景变化模拟（SceneChanger）

⚠️ 仅用于模拟环境，部署到真实机器人时注释掉即可。

`SceneChange.py` 中的 `SceneChanger` 类以后台线程运行，模拟真实场景中物体的随机增减：

- 每 2 秒检测一次，`random > 0.96` 时触发变化（约 4% 概率）
- 只修改 `kitchenTable` 的 `contains` 列表
- 10% 概率移除一个模拟物体，90% 概率增加一个新物体
- 候选新物体：Strawberry、Grape、Watermelon、Pineapple、Mango
- 自动去重：不会重复添加已存在的物体
- 保护原始物体：移除操作只针对模拟新增的物体，不碰原始物体
- 场景未初始化时不操作（contains 少于 3 个时跳过）

启动方式：在 `run.py` 的 `RobotManager.__init__` 中创建并调用 `start()`。

## 场景变化检测（SceneDetector）

`monitoring.py` 中的 `SceneDetector` 类以后台线程运行，定期读取 Redis 场景状态并检测变化：

- 启动时拍摄场景快照作为基准（baseline）
- 每 2 秒对比当前场景与基准快照
- 检测新增物体（added）和消失物体（removed）
- 检测到变化后更新基准，避免重复报告
- 变化记录累积在 `self.changes` 中，供 `_send_result()` 读取

部署到真实机器人时，将 `_detect_changes()` 替换为真实传感器或 VLM 接口即可。

## 场景变化上报

Slaver 在每个子任务完成后，通过 `_send_result()` 将场景变化上报给 Master：

```python
payload = {
    "robot_name": "FQrobot",
    "subtask_handle": "抓取苹果",
    "subtask_result": "...",
    "scene_changes": [{"location": "kitchenTable", "added": ["Pineapple"], ...}],
    ...
}
```

Master 收到后累积变化，在所有子任务完成后决定是否重新规划。详见 Master README。

## 场景状态管理

工具执行后，`memory_predict` 用 LLM 分类动作类型（add_object / remove_object / position），自动更新 Redis 中的场景状态。

`SceneMemory` 维护中文描述→英文 Redis key 的映射，支持中文位置名查找。

## Judge 失败决策

`judge.py` 在工具执行失败时随机决策：
- `retry`（概率 0.6）— 重新执行，最多 3 次
- `skip`（概率 0.3）— 跳过当前子任务
- `terminate`（概率 0.1）— 终止整个任务链，通知 Master 停止后续子任务

## 添加新工具模块

1. 在 `robot/module/` 下创建新文件
2. 实现 `register_tools(mcp)` 函数，用 `@mcp.tool()` 装饰器注册工具
3. 在 `robot/skill.py` 中导入并调用
4. 重启 Slaver

详见 `robot/README_MODULES.md`。
