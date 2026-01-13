# RoboOS

RoboOS是一个基于“大脑-小脑”分层架构的机器人操作系统，通过大语言模型实现跨形态多机器人协作。

## 快速入门

### 1. 环境要求

- Python 3.10+
- Conda

### 2. 安装

```bash
# 克隆仓库
git clone https://github.com/Chemauto/RoboOS.git
cd RoboOS

# 创建 Conda 环境并安装依赖
conda create -n RoboOS python=3.10
conda activate RoboOS
pip install -r requirements.txt
#如果出现问题的话就先注释掉有问题的项目，或者先将pytorch版本改成2.5.1，
#如果是50系显卡建议安装2.9.0以上的
#然后下载下面的代码，安装依赖
git clone https://github.com/FlagOpen/FlagScale 
#已经安装就不需要再clone了
cd FlagScale
git checkout 3fc2037f90917227bd4aebabd9d7b330523f437c
#版本提前安装好了
PYTHONPATH=./:$PYTHONPATH pip install . --verbose --no-build-isolation 


### 3. 运行系统

你可以手动运行系统，也可以使用部署界面。


#### 手动启动 (在3个独立的终端中)
1.启动模型
    # 终端 1
    conda activate RoboOS
    bash Modeldeploy/start_server.sh

2.  **启动 Master:**
    ```bash
    # 终端 2
    conda activate RoboOS
    python master/run.py
    ```
3.  **启动 Slaver:**
    ```bash
    # 终端 3
    conda activate RoboOS
    python slaver/run.py
    ```
4.  **启动 Web UI:**
    ```bash
    # 终端 4
    conda activate RoboOS
    python deploy/run.py
    ```

启动后，主 Web 界面将在 `http://127.0.0.1:8888` 上可用。
也就是可以点击这个web UI界面，在里面进行输入


### 4. 发布任务

**通过 Web 界面** (http://127.0.0.1:8888): 导航到 "Publish Task" 部分

**通过测试脚本:**
```bash
python test_robot.py
```
支持选择模块/测试模式/自定义任务

### 5. 任务示例

**底盘控制:**
- "前往卧室" / "到客厅"
- "先去厨房，然后去卧室"

**机械臂控制:**
- "机械臂复位"
- "腕部向上转动10度"
- "夹爪闭合到50"

### 6. 查看日志

```bash
tail -f master/.logs/master_agent.log  # Master 日志
tail -f slaver/.log/agent.log          # Slaver 日志
```

## 场景位置

| 位置 | 坐标 |
|------|------|
| entrance (入口) | (0.0, 0.0, 0.0) |
| livingRoom (客厅) | (2.0, 3.0, 0.0) |
| bedroom (卧室) | (4.0, 1.0, 0.0) |
| kitchenTable | (1.0, 2.0, 0.0) |
| trashCan (垃圾桶) | (4.0, 3.0, 0.0) |

## 扩展开发

**添加新模块 (3步):**
```bash
# 1. 复制模板
cd slaver/demo_robot_local && cp example.py my_module.py

# 2. 编辑 my_module.py 实现功能

# 3. 在 skill.py 注册
from my_module import register_tools as register_my_tools
```

## 文档

- [MODULE_DEVELOPMENT_GUIDE.md](MODULE_DEVELOPMENT_GUIDE.md) - 完整开发指南
- [slaver/demo_robot_local/README_MODULES.md](slaver/demo_robot_local/README_MODULES.md) - 详细模块文档
