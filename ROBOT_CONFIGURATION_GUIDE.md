# 机器人配置与导航功能指南

## 1. 概述

本文档旨在指导您配置和运行一个专注于**自然语言导航**功能的简化版RoboOS项目。

最终目标是：您可以通过输入简单的中文或英文指令（例如“去厨房”、“navigate to trashCan”），让机器人在模拟环境中移动到指定位置。

为此，我们已经对项目进行了以下核心精简：
- **技能简化**: `slaver/demo_robot_local/skill.py` 文件现在只包含 `navigate_to_target`（导航到目标）这一个核心技能，移除了抓取、放置等无关功能。
- **配置优化**: 调整了 `master/config.yaml` 的配置文件路径，使其更具可移植性。

---

## 2. 配置模拟环境：场景与位置

机器人所有可导航的目标点都在 `master/scene/profile.yaml` 文件中定义。您可以修改此文件来添加、删除或编辑场景中的位置。

### 2.1 文件结构解析

每个位置都是一个独立的条目，包含以下关键信息：

```yaml
scene:
  - name: kitchenTable         # 位置的英文名称 (重要：这是指令识别的关键)
    type: table                 # 位置类型 (例如：table, container, location)
    position: [1.0, 2.0, 0.0]   # 在模拟环境中的坐标 [x, y, z]
    description: "厨房桌子"       # 位置的中文描述 (方便理解)

  - name: livingRoom
    type: location
    position: [2.0, 3.0, 0.0]
    description: "客厅"
```

### 2.2 如何添加一个新位置？

假设您想添加一个“阳台” (balcony)。

1.  打开 `master/scene/profile.yaml` 文件。
2.  在 `scene:` 列表下，添加一个新的条目：

    ```yaml
    - name: balcony              # 英文名
      type: location             # 类型
      position: [5.0, 5.0, 0.0]  # 自定义坐标
      description: "阳台"        # 中文描述
    ```

3.  保存文件。**无需重启 Master 或 Slaver 服务**，系统会自动重载场景信息。

现在，您就可以通过“去阳台”或“navigate to balcony”来命令机器人移动了。

---

## 3. 核心技能：`skill.py` 解析

机器人的所有能力都定义在 `slaver/demo_robot_local/skill.py` 文件中。现在它包含两种移动相关的技能。

### 技能1: `navigate_to_target` (导航到目标)
用于移动到场景中预定义的、有名称的地标。
```python
@mcp.tool()
async def navigate_to_target(target: str) -> tuple[str, dict]:
    """
    Navigate to a predefined target location. This is for moving to known landmarks.
    Args:
        target: The name of the navigation destination (eg., "kitchenTable", "trashCan").
    """
    # ... (实现细节)
```

### 技能2: `move` (精确移动)
用于执行基于方向、速度和时间的精确相对移动。
```python
@mcp.tool()
async def move(direction: float, speed: float, duration: float) -> tuple[str, dict]:
    """
    Move the robot in a specific direction for a certain duration. This is for precise, relative movements.
    Args:
        direction: The direction of movement in degrees (0-360), where 0 is forward.
        speed: The speed of movement in meters per second.
        duration: The duration of the movement in seconds.
    """
    # ... (实现细节)
```
-   **`@mcp.tool()`**: 这个装饰器将函数注册为一个可被 Master 远程调用的“技能”。
-   **参数**: LLM 会从您的自然语言指令中解析出这些参数（如 `target`, `direction`, `speed`, `duration`）。

---

## 4. 运行与测试

请按照 `README.md` 中的指示，通过手动或Web UI的方式启动 **Master**、**Slaver** 和 **Deploy** 服务。

**重要提示**: 由于您更改了 `skill.py`，请务必**重启 Slaver 服务**以加载新的 `move` 技能。

系统完全启动后，推荐使用根目录下的 `test_navigation.py` 脚本来测试导航功能。

### 4.1 使用测试脚本

1.  在项目根目录下打开一个新的终端。
2.  确保您的 Conda 环境 (`RoboOS`) 已激活。
3.  运行测试脚本：
    ```bash
    python test_navigation.py
    ```
4.  脚本启动后，会首先检查 Master 服务是否在线，然后提供三种测试模式供您选择。

### 4.2 测试模式详解

#### 模式1: 运行所有测试
-   **描述**: 此模式会自动执行脚本中预设的9个测试用例，涵盖了基础导航、多点导航、相对位置和中英文混合等多种场景。
-   **使用场景**: 适合初次运行时进行全面的功能验证。

#### 模式2: 选择特定测试
-   **描述**: 脚本会列出所有可用的测试用例，您可以输入编号来运行单个特定的测试。
-   **使用场景**: 当您只想测试某个特定功能（例如多点导航）时使用。

#### 模式3: 自定义任务 (推荐)
-   **描述**: 这是一个交互模式，您可以自由输入任何自然语言导航指令。输入 `'quit'` 可退出。
-   **使用场景**: 最灵活的测试方式，适合进行自由探索和调试。

### 4.3 测试指令示例

在**模式3**下，您可以尝试输入以下指令：

-   **基础导航 (使用 `navigate_to_target`)**:
    -   `到垃圾桶`
    -   `去客厅`
    -   `navigate to bedroom`

-   **精确移动控制 (使用 `move`)**:
    -   `让机器人向前移动1米` (LLM需要推断速度和时间)
    -   `让机器人向右转90度` (LLM需要推断这是一个旋转动作)
    -   `让机器人沿着正前方偏60度的方向以1米每秒的速度走2秒`

-   **多点导航 (复合任务)**:
    -   `先到垃圾桶，然后去客厅，最后去卧室`

### 4.4 如何观察执行结果

-   **测试脚本终端**: 会实时显示任务发送的状态以及从 Master Agent 返回的`任务分解结果` (JSON格式)。
-   **Slaver 终端**: 当 Slaver 成功执行技能后，会打印出类似 `Navigation to bedroom has been successfully performed.` 或 `Moved 2.00 meters at a 60.0 degree angle.` 的消息。
-   **Master 终端**: 您可以观察到 Master 接收任务、进行任务规划的详细日志。

**注意**: 如果您在 Slaver 终端没有看到技能执行的 `print` 输出，请检查 `slaver/run.py` 的配置。默认情况下，详细日志可能被重定向到了 `slaver/.log/agent.log` 文件中。您可以通过 `tail -f slaver/.log/agent.log` 命令来实时查看。

---

## 5. 总结

通过以上步骤，您已经拥有一个专注于导航功能的机器人模拟环境。您可以自由地在 `profile.yaml` 中定义您的虚拟世界，并通过 `test_navigation.py` 脚本用自然语言指挥机器人探索。
