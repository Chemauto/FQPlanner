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


### 3. 运行系统

你可以手动运行系统，也可以使用部署界面。

#### 手动启动 (在3个独立的终端中)

1.  **启动 Master:**
    ```bash
    # 终端 1
    conda activate RoboOS
    python master/run.py
    ```
2.  **启动 Slaver:**
    ```bash
    # 终端 2
    conda activate RoboOS
    python slaver/run.py
    ```
3.  **启动 Web UI:**
    ```bash
    # 终端 3
    conda activate RoboOS
    python deploy/run.py
    ```

启动后，主 Web 界面将在 `http://127.0.0.1:8888` 上可用。


### 4. 发布任务

系统运行后，你可以给机器人下达任务。

- **通过 Web 界面:** 导航到 "Publish Task" 部分。
- **通过脚本:** 运行示例导航测试脚本。
  ```bash
  python test_navigation.py
  ```
  按照屏幕提示发送导航命令，例如“到垃圾桶前方”。
