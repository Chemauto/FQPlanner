# 场景信息动态获取方案

## 当前问题

目前 `profile.yaml` 硬编码了所有场景物体信息（桌子、容器、小物体），存在以下问题：

1. **数据重复**：OmniGibson 场景本身已有这些物体，profile.yaml 只是复制了一份
2. **数据不一致**：如果场景物体位置变化（如被移动），profile.yaml 不会更新
3. **维护困难**：每次场景变化都需要重新运行 `get_scene_data.py`

## 目标架构

```
LLM 规划任务
    ↓
查询 /objects API → 获取实时场景物体
    ↓
结合 profile.yaml（只有固定位置）
    ↓
生成任务计划
```

## 修改方案

### 1. 简化 profile.yaml

**文件**: `master/scene/profile.yaml` 和 `serve/profile.yaml`

只保留 LLM 需要但场景没有的信息：

```yaml
scene:
  # 固定位置（场景中没有这些物体，只是虚拟坐标）
  - name: livingRoom
    type: location
    position: [0.0, 0.0, 0.0]
    description: 客厅

  - name: bedroom
    type: location
    position: [-2.0, 2.0, 0.0]
    description: 卧室

  - name: kitchen
    type: location
    position: [2.0, 0.0, 0.0]
    description: 厨房

  - name: bathroom
    type: location
    position: [2.0, 2.0, 0.0]
    description: 浴室

  - name: entrance
    type: location
    position: [0.0, -2.0, 0.0]
    description: 入口
```

### 2. Master 启动时动态获取场景信息

**文件**: `master/agents/agent.py` 或 `master/run.py`

```python
import requests

def get_scene_objects(server_url="http://127.0.0.1:5001"):
    """从 OmniGibson 服务器动态获取场景物体"""
    try:
        resp = requests.get(f"{server_url}/objects", timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"[Master] 获取场景物体失败: {e}")
    return None

def build_scene_context():
    """构建 LLM 场景上下文"""
    # 1. 获取固定位置
    with open("master/scene/profile.yaml") as f:
        profile = yaml.safe_load(f)

    # 2. 动态获取场景物体
    objects = get_scene_objects()

    # 3. 组合成 LLM 需要的格式
    context = "## 当前场景\n\n"

    if objects:
        context += "### 可操作物体\n"
        for obj in objects.get("objects", []):
            context += f"- {obj['name']} ({obj['category']}) @ {obj['position']}\n"

        context += "\n### 家具\n"
        for obj in objects.get("furniture", []):
            context += f"- {obj['name']} ({obj['category']}) @ {obj['position']}\n"

    context += "\n### 固定位置\n"
    for loc in profile.get("scene", []):
        if loc.get("type") == "location":
            context += f"- {loc['name']}: {loc['description']} @ {loc['position']}\n"

    return context
```

### 3. 修改 Slaver 工具调用

**文件**: `slaver/robot/module/omnigibson_client.py`

工具调用时，物体名称直接传给 OmniGibson 服务器，服务器负责查找。不需要预先知道所有物体。

### 4. 可选：保留 get_scene_data.py

保留 `get_scene_data.py` 用于调试和离线分析，但不用于运行时。

## 需要修改的文件

| 文件 | 修改内容 |
|------|----------|
| `master/scene/profile.yaml` | 删除桌子、容器、小物体，只保留固定位置 |
| `serve/profile.yaml` | 同上 |
| `master/agents/agent.py` | 添加动态获取场景物体的逻辑 |
| `master/agents/planner.py` | 修改 prompt，告诉 LLM 场景信息是动态获取的 |
| `get_scene_data.py` | 保留，但标注仅用于调试 |

## 优势

1. **数据一致性**：LLM 总是获取最新场景状态
2. **减少维护**：不需要手动更新 profile.yaml
3. **更灵活**：场景物体变化时自动适应

## 风险

1. **启动延迟**：Master 启动时需要等待 OmniGibson 服务器就绪
2. **网络依赖**：如果 OmniGibson 服务器不可用，LLM 无法获取场景信息
3. **API 变化**：OmniGibson 服务器 API 变化可能影响 Master

## 实施步骤

1. [ ] 简化 profile.yaml，只保留固定位置
2. [ ] 在 Master 中添加 `/objects` API 调用逻辑
3. [ ] 修改 LLM prompt，使用动态获取的场景信息
4. [ ] 测试：启动系统，验证 LLM 能正确获取场景信息
5. [ ] 更新文档
