# Agent 模块

FQPlanner 的基础通信与工具匹配模块，为 Master-Slaver 架构提供底层支持。

## 目录结构

```
Agent/
├── collaboration/
│   ├── __init__.py          # 导出 Collaborator
│   └── collaborator.py      # Redis 通信核心类
│
├── tool_match/
│   ├── __init__.py          # 导出 ToolRegistry, ToolMatcher
│   ├── tool_registry.py     # 工具注册中心
│   └── tool_matcher.py      # 语义工具匹配引擎
│
└── __init__.py
```

## collaboration/ - 协作通信

`Collaborator` 类基于 Redis 实现 Master 和 Slaver 之间的通信。

**消息通信：**
- `send(channel, message)` — 发布消息到 Redis 频道
- `listen(channel, callback)` — 订阅频道并回调处理

**Agent 管理：**
- `register_agent(name, data)` — 注册 Agent 信息
- `read_agent_info(name)` / `read_all_agents_info()` — 读取 Agent 信息
- `update_agent_busy(name, busy)` — 标记 Agent 忙闲状态
- `wait_agents_free(names)` — 等待指定 Agent 全部空闲

**环境状态：**
- `record_environment(name, value)` — 记录环境信息
- `read_environment(name)` — 读取环境信息
- `record_agent_status(name, value)` — 记录 Agent 状态快照

**使用方式：**
```python
from agent.collaboration import Collaborator

collaborator = Collaborator(host="127.0.0.1", port=6379, db=0, password="xxx")
# 或从配置字典创建
collaborator = Collaborator.from_config(config_dict)
```

## tool_match/ - 工具匹配

将自然语言任务描述智能匹配到具体的工具函数。

### 评分机制

采用多权重评分系统：

| 维度 | 权重 | 说明 |
|------|------|------|
| semantic | 0.7 | 基于 sentence-transformers 的语义相似度 |
| keyword | 0.2 | 关键词重叠匹配 |
| category | 0.1 | 分类相关性 |

支持**降级机制**：当模型不可用或网络不通时，自动降级 semantic 组件，退化为纯关键词匹配，权重自动归一化。

### ToolRegistry — 工具注册中心

- `register_tool(tool, category)` — 注册单个工具
- `register_tools(tools, category)` — 批量注册工具
- `search_tools(query, category=None)` — 搜索匹配的工具
- `get_tool_by_name(name)` — 按名称查找
- `get_tools_by_category(category)` — 按分类查找
- `get_stats()` — 获取统计信息

**降级控制：**
- `set_degradation(component, degraded)` — 设置组件降级
- `get_degradation_status()` — 获取降级状态
- `reset_degradation()` — 重置所有降级标志

### ToolMatcher — 语义匹配引擎

**配置参数：**
- `max_tools` — 返回的最大工具数（默认 3）
- `min_similarity` — 最低相似度阈值（默认 0.1）

**预定义分类：** general / file / search / data / network / system

### 工具格式

```python
tool = {
    "function": {
        "name": "tool_name",
        "description": "tool description",
        "parameters": {
            "type": "object",
            "properties": {
                "param1": {"type": "string", "description": "param description"}
            }
        }
    }
}
```

### 使用方式

```python
from agent.tool_match import ToolRegistry

registry = ToolRegistry(max_tools=3, min_similarity=0.1)

# 注册工具
registry.register_tool(tool, category="file")

# 搜索匹配工具
matched = registry.search_tools("read file content")
# 返回 [("read_file", 0.92), ...]
```

### 依赖

```bash
# 完整功能（推荐）
pip install sentence-transformers torch numpy

# 基本功能（无语义匹配，自动降级为关键词匹配）
pip install numpy
```

> 首次使用时 sentence-transformers 模型会自动下载。建议工具描述使用英文关键词以获得更好的匹配效果。
