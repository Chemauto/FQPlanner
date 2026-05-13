# Master - 任务规划节点

"大脑"模块，负责接收任务、分解子任务、分发给机器人并收集结果，支持场景变化驱动的动态重规划。

## 目录结构

```
master/
├── run.py              # 启动入口（Flask 服务，端口 5000）
├── config.yaml         # 配置文件（API key 通过 ${CLOUD_API_KEY} 从 .env 读取）
├── agents/
│   ├── agent.py        # GlobalAgent - 任务编排、对话历史、terminate 传播、场景变化重规划
│   ├── planner.py      # GlobalTaskPlanner - LLM 任务分解（兼容 Qwen list 格式）
│   └── prompts.py      # Prompt 模板（任务分解指引）
└── scene/
    └── profile.yaml    # 场景定义（位置、物体、坐标、中英文名称）
```

## 启动

```bash
# 确保 .env 中配置了 CLOUD_API_KEY
python master/run.py
```

## 配置

编辑 `config.yaml`，主要配置项：

- **model_select** — LLM 模型（如 qwen3.5-plus-2026-02-15）
- **model_dict.cloud_api_key** — API key（通过 `${CLOUD_API_KEY}` 从项目根目录 `.env` 读取）
- **collaborator** — Redis 连接信息（host、port、password、db）
- **profile.path** — 场景配置文件路径

## 核心流程

```
用户任务 → GlobalTaskPlanner(LLM 分解) → subtask_list
    → 按 subtask_order 分组（同组并行，不同组串行）
    → 通过 Redis 分发给 Slaver
    → 收集结果 + 场景变化（scene_changes）
    → 所有子任务完成后检查是否需要重规划
```

## 场景变化重规划（Replan）

当 Slaver 执行子任务过程中检测到场景变化（如新物体出现），会将变化信息随结果上报给 Master。Master 累积这些变化，在所有子任务完成后进行评估：

1. Slaver 每个子任务完成后，在结果 payload 中附带 `scene_changes` 字段
2. Master 在 `_handle_result()` 中提取并累积到 `pending_scene_changes`
3. 所有子任务执行完毕后，检查是否有累积的场景变化
4. 如果有变化 → 构造包含变化摘要的 replan 提示词 → 调用 LLM 重新规划
5. LLM 判断是否需要补充新子任务 → 如需要，补发给 Slaver 执行

```
原始任务完成 → 检查 pending_scene_changes
    ├─ 有变化 → "执行过程中 kitchenTable 新增了 Pineapple，是否需要补充任务？"
    │         → LLM 返回新的 subtask_list → 补发执行
    └─ 无变化 → 结束
```

重规划生成的子任务会以 `原task_id + "_replan"` 作为新的 task_id，避免与原任务冲突。

## Terminate 传播

当 Slaver 的 judge 判定终止时：
1. Slaver 返回 `terminated: true` + `task_id`
2. Master 将 `task_id` 加入 `terminated_tasks` 集合
3. `_dispath_subtasks_async` 在每组任务前检查，跳过剩余子任务

## API

| 接口 | 方法 | 说明 |
|------|------|------|
| `/publish_task` | POST | 发布任务，body: `{"task": "前往卧室"}` |
| `/robot_status` | GET | 查询已注册机器人状态 |
| `/system_status` | GET | 查询系统 CPU/内存状态 |
