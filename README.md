# RoboOS

RoboOS 是基于"大脑-小脑"分层架构的机器人操作系统，通过大语言模型实现跨形态多机器人协作。

**核心功能**
- 🧭 **模拟导航** - 场景定位与路径规划
- 🦾 **机械臂控制** - SO101机械臂关节运动
- 🌐 **远程通信** - 网络化机器人协作与抓取

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
#如果还有问题
#则用require.txt代替requirements.txt

#然后下载下面的代码，安装依赖
git clone https://github.com/FlagOpen/FlagScale 
#已经安装成功就不需要再clone了
cd FlagScale
git checkout 3fc2037f90917227bd4aebabd9d7b330523f437c
#版本提前安装好了
PYTHONPATH=./:$PYTHONPATH pip install . --verbose --no-build-isolation 

#如果两个依赖都安装好了就代表可以了，注意本地部署时vllm需要安装


注意requirements.txt，等到前面环境安装好后可以在安装
### 3. 模型配置

RoboOS 支持两种模型模式，通过修改 `master/config.yaml` 和 `slaver/config.yaml` 中的 `model_select` 字段进行切换：

#### 模式 1: 云端 API 模式

使用 **qwen-plus** 模型，通过阿里云 API 调用，无需本地部署模型。

**配置步骤：**

1. **修改配置文件** (`master/config.yaml` 和 `slaver/config.yaml`):
   ```yaml
   # 选择模型
   model_select: "qwen-plus"  # 使用云端API模式
   # model_select: "robobrain"  # 注释掉本地模式

   model_dict:
     # 云端模型配置
     cloud_model: "qwen-plus"
     cloud_type: "default"
     cloud_api_key: "sk-xxxxxxxxxxxxxxx"  # 替换为你的API Key
     cloud_server: "https://dashscope.aliyuncs.com/compatible-mode/v1/"
   ```

2. **获取 API Key**:
   - 访问 [阿里云百炼平台](https://dashscope.aliyuncs.com/)
   - 注册账号（新用户有3个月免费额度）
   - 在控制台获取 API Key
   - 将 API Key 填入配置文件的 `cloud_api_key` 字段
- ✅ 无需 GPU，普通电脑即可运行
- ✅ 配置简单，只需 API Key



#### 模式 2: 本地部署模式（高级用户）

使用 **robobrain** 模型，需要在本地部署 LLM，需要高性能 GPU。

**配置步骤：**

1. **启动本地模型服务器**:
   ```bash
   # 终端 1: 启动 vLLM 模型服务
   conda activate RoboOS
   bash Modeldeploy/start_server.sh
   ```

2. **修改配置文件** (`master/config.yaml` 和 `slaver/config.yaml`):
   ```yaml
   # 选择模型
   # model_select: "qwen-plus"  # 注释掉云端模式
   model_select: "robobrain"   # 使用本地部署模式

   model_dict:
     # 本地模型配置
     cloud_model: "robobrain"
     cloud_type: "default"
     cloud_api_key: "EMPTY"     # 本地模式无需 API Key
     cloud_server: "http://localhost:4567/v1/"  # 本地服务地址
   ```

### 4. 运行系统

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

**导航控制**
- "前往卧室" / "到客厅"
- "先去厨房，然后去卧室"

#看到坐标变化

**机械臂控制**
- "腕部弯曲关节减少30度"

#看到机械臂抬起

**抓取功能**
- "抓取" - 执行完整抓取流程
#310B相机摄像头开启

### 6. 查看日志

```bash
tail -f master/.logs/master_agent.log  # Master 日志
tail -f slaver/.log/agent.log          # Slaver 日志
```

## 场景位置

| 位置 | 坐标 |
|------|------|
| 入口 (entrance) | (0.0, 0.0, 0.0) |
| 客厅 (livingRoom) | (2.0, 3.0, 0.0) |
| 卧室 (bedroom) | (4.0, 1.0, 0.0) |
| 厨房 | (1.0, 2.0, 0.0) |

## 扩展开发

**添加新模块 (3步)**
```bash
# 1. 复制模板
cd slaver/demo_robot_local && cp module/example.py module/my_module.py

# 2. 编辑实现功能

# 3. 在 skill.py 注册
from module.my_module import register_tools as register_my_tools
```

## 文档

- [模块开发指南](MODULE_DEVELOPMENT_GUIDE.md) - 完整开发文档
- [场景配置说明](master/scene/README.md) - 位置定义与映射
- [状态管理文档](ROBOT_STATE_MANAGEMENT.md) - 位置状态追踪
