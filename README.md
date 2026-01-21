# RoboOS

RoboOS 是基于"大脑-小脑"分层架构的机器人操作系统，通过大语言模型实现跨形态多机器人协作。

**核心功能**
- 🧭 **模拟导航** - 场景定位与路径规划
- 🦾 **机械臂控制** - SO101机械臂关节运动
- 🌐 **远程通信** - 网络化机器人协作与抓取
- 🤖 **麦轮底盘** - 三全向轮底盘的Socket远程控制与位置追踪

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


## 📁 项目结构

```
RoboOS/
├── master/                  # Master节点（任务规划）
│   ├── scene/              # 场景配置文件
│   │   ├── profile.yaml    # 位置和物体坐标定义
│   │   ├── LOCATION_MAP.py # 中文名称到英文名称映射
│   │   └── README.md       # 场景配置说明
│   └── run.py              # Master启动脚本
│
├── slaver/                 # Slaver节点（任务执行）
│   ├── demo_robot_local/   # 本地机器人模拟
│   │   └── module/         # 功能模块
│   │       ├── base.py           # 模拟底盘导航
│   │       ├── arm.py            # SO101机械臂控制
│   │       ├── grasp.py          # 抓取功能
│   │       ├── real_base.py      # 麦轮底盘远程控制
│   │       ├── mujoco_base.py    # MuJoCo仿真控制 ⭐ NEW
│   │       └── example.py        # 示例模块
│   └── run.py              # Slaver启动脚本
│
├── TestMujoco/             # MuJoCo仿真测试 ⭐
│   ├── controller/         # 控制器
│   │   ├── omni_controller.py    # 运动学控制器（三轮全向轮）
│   │   └── global_navigator.py   # 全局导航控制器（PID）
│   ├── model/              # MuJoCo模型文件
│   │   └── assets/
│   │       └── scene.xml        # 机器人场景模型
│   ├── run_navigation_standalone.py  # 独立导航脚本
│   ├── video/              # 录制的导航视频
│   └── README.md           # 详细文档
│
├── TestRealBase/           # 麦轮底盘测试项目
│   ├── RealBase/           # 底盘控制核心库
│   │   ├── motor_controller.py  # 底盘运动控制
│   │   └── test_motor.py        # 单元测试
│   ├── base_server.py      # 开发板服务器程序
│   └── README.md           # 项目说明
│
├── NAVIGATION_GUIDE.md     # 麦轮底盘导航使用指南
├── REALBASE_REDIS_UPDATE.md  # Redis位置追踪说明
├── MODULE_GUIDE.md         # 模块开发指南
├── grasp_server.py         # 抓取服务器
├── test_robot.py           # 机器人测试脚本
└── requirements.txt        # Python依赖
```

---


## 📚 更多文档

- [模块开发指南](MODULE_GUIDE.md) - 如何添加新的功能模块
- [场景配置说明](master/scene/README.md) - 如何修改场景和位置
- [麦轮底盘导航指南](NAVIGATION_GUIDE.md) - 麦轮底盘详细使用说明
- [TestRealBase项目](TestRealBase/README.md) - 底盘硬件控制详情

