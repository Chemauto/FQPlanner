# RoboOS 模块使用与开发指南

## 目录结构

```
slaver/demo_robot_local/
├── skill.py              # 统一入口
├── module/               # 功能模块
│   ├── base.py           # 底盘控制
│   ├── arm.py            # 机械臂控制
│   ├── grasp.py          # 抓取控制
│   ├── real_base.py      # 麦轮底盘控制
│   ├── mujoco_base.py    # MuJoCo仿真控制 ⭐ NEW
│   └── example.py        # 示例模板
└── config.yaml           # 配置文件

TestMujoco/               # MuJoCo仿真测试 ⭐ NEW
├── controller/           # 控制器
│   ├── omni_controller.py      # 运动学控制器
│   └── global_navigator.py     # 全局导航控制器
├── model/                # MuJoCo模型文件
└── test/                 # 测试脚本
    └── test_mujoco.py          # 仿真测试程序

master/scene/
├── profile.yaml          # 场景配置
└── LOCATION_MAP.py       # 位置映射
```

---

## 现有模块

### 1. base.py - 底盘控制模块

**功能:**
- `navigate_to_target(target)` - 导航到目标位置
- `move(direction, speed, duration)` - 参数化移动

**指令示例:**
```
"前往卧室" / "到客厅" / "导航到入口"
"向前移动1米" / "向右移动2秒"
```

**支持位置:**
| 名称 | 坐标 [x,y,z] | 说明 |
|------|-------------|------|
| entrance | [0.0, 0.0, 0.0] | 入口 |
| livingRoom | [2.0, 3.0, 0.0] | 客厅 |
| bedroom | [4.0, 1.0, 0.0] | 卧室 |
| kitchenTable | [1.0, 2.0, 0.0] | 厨房桌子 |
| customTable | [2.0, 1.0, 0.0] | 自定义桌子 |
| servingTable | [3.0, 2.0, 0.0] | 服务桌 |
| basket | [1.5, 1.5, 0.5] | 篮子 |
| trashCan | [4.0, 3.0, 0.0] | 垃圾桶 |

### 2. arm.py - 机械臂控制模块

**功能:**
- `move_joint_relative(joint_name, angle)` - 相对角度移动
- `move_joint_absolute(joint_name, angle)` - 绝对角度移动
- `get_joint_position(joint_name)` - 获取关节位置
- `get_all_joint_positions()` - 获取所有关节位置

**关节列表:**
- `shoulder_pan` - 肩部旋转
- `shoulder_lift` - 肩部升降
- `elbow_flex` - 肘部弯曲
- `wrist_flex` - 腕部弯曲
- `wrist_roll` - 腕部旋转
- `gripper` - 夹爪 (0-100, 0=张开, 100=闭合)

**指令示例:**
```
"机械臂复位" / "复位到零点"
"腕部向上转10度" / "肘部弯曲20度"
"夹爪闭合到50" / "张开夹爪"
```

### 3. grasp.py - 抓取控制模块

**功能:**
- `grasp_object()` - 执行完整抓取流程
- `check_grasp_status()` - 检查模块状态

**指令示例:**
```
"抓取" / "执行抓取"
```

**工作原理:**
- 通过Socket连接到开发板
- 开发板执行视觉识别和抓取
- 返回抓取结果

### 4. real_base.py - 麦轮底盘控制模块

**功能:**
- `move_base(direction, speed, duration)` - 方向控制移动
- `stop_base()` - 立即停止
- `navigate_to_location(target)` - 导航到位置
- `check_base_status()` - 检查状态

**支持方向:**
- `forward/前` - 向前
- `backward/后` - 向后
- `left/左` - 向左横移
- `right/右` - 向右横移
- `forward_left/左前` - 左前斜向
- `forward_right/右前` - 右前斜向
- `backward_left/左后` - 左后斜向
- `backward_right/右后` - 右后斜向
- `rotate_cw/顺时针` - 顺时针旋转
- `rotate_ccw/逆时针` - 逆时针旋转

**指令示例:**
```
"向前移动" / "向左移动3秒" / "逆时针旋转"
"去卧室" / "导航到客厅"
"停止" / "立即停止"
```

**导航示例 (速度 0.2 m/s):**
```
"去卧室" → 向右4米(20秒) + 向前1米(5秒) = 25秒
"去客厅" → 向右2米(10秒) + 向前3米(15秒) = 25秒
```

### 5. mujoco_base.py - MuJoCo仿真控制模块 ⭐ NEW

**功能:**
- `test_mujoco_viewer(mode)` - 启动MuJoCo仿真界面并测试运动学
- `navigate_to_target(x, y, yaw)` - 使用PID全局导航移动到目标位置
- `move_base_velocity(vx, vy, omega, duration)` - 按速度分量控制运动
- `stop_base()` - 立即停止
- `check_base_status()` - 检查状态

**测试模式:**
- `mode="1"` - 前进测试
- `mode="2"` - 后退测试
- `mode="3"` - 左移测试
- `mode="4"` - 右移测试
- `mode="5"` - 原地旋转测试

**指令示例:**
```
"打开MuJoCo仿真测试前进" / "测试运动学"
"导航到位置0.5,0.3" / "移动到坐标0.5米0.3米"
"以速度0.2向前移动2秒" / "向左移动1.5秒"
"检查仿真状态"
```

**导航示例:**
```python
# 自动导航到目标点，使用PID控制
navigate_to_target(x=0.5, y=0.3, yaw=None)  # 只控制位置
navigate_to_target(x=0.5, y=0.3, yaw=1.57)  # 位置+姿态(90度)
```

**测试脚本:**
```bash
# 运行MuJoCo仿真测试
cd /home/dora/RoboOs/RoboOS/TestMujoco
python test/test_mujoco.py
```

**依赖:**
- `mujoco` - 物理仿真引擎
- `mujoco-viewer` - 仿真查看器
- `numpy` - 数值计算
- `scipy` - 坐标变换

**安装:**
```bash
pip install mujoco mujoco-viewer numpy scipy
```

### 6. example.py - 示例模板

用于参考开发新模块。

---

## 添加新模块

### 步骤 1: 创建模块文件

```bash
cd slaver/demo_robot_local/module
cp example.py my_module.py
```

### 步骤 2: 编辑模块

```python
"""我的模块"""

import sys

def register_tools(mcp):
    """注册工具函数"""
    
    @mcp.tool()
    async def my_function(param: str) -> str:
        """函数功能说明
        
        Args:
            param: 参数说明
            
        Returns:
            执行结果
        """
        print(f"[my_function] 参数: {param}", file=sys.stderr)
        result = f"执行完成: {param}"
        return result
    
    print("[my_module.py] 模块已注册", file=sys.stderr)
```

### 步骤 3: 注册到 skill.py

编辑 `skill.py`:

```python
# 导入部分
from module.my_module import register_tools as register_my_module_tools

# register_all_modules() 函数中
def register_all_modules():
    # ...现有模块...
    register_my_module_tools(mcp)  # 添加这行
```

### 步骤 4: 重启服务

```bash
# 按 Ctrl+C 停止 slaver
# 重新启动
python slaver/run.py
```

查看日志确认:
```
[my_module.py] 模块已注册
[skill.py] ✓ 所有模块注册完成
```

---

## 开发规范

### 函数签名

```python
@mcp.tool()
async def function_name(param: type = default) -> str:
    """函数文档字符串"""
    result = "结果"
    return result
```

### 日志输出

```python
print(f"[module_name.function_name] 日志信息", file=sys.stderr)
```

### 错误处理

```python
try:
    result = perform_operation()
    return result
except Exception as e:
    error_msg = f"操作失败: {e}"
    print(f"[module_name] {error_msg}", file=sys.stderr)
    return error_msg
```

---

## 场景配置

### 修改位置

**1. 编辑 `master/scene/profile.yaml`:**

```yaml
scene:
  - name: balcony
    type: location
    position: [5.0, 2.0, 0.0]
    description: "阳台"
```

**2. 编辑 `master/scene/LOCATION_MAP.py`:**

```python
LOCATION_MAP = {
    "阳台": "balcony",
}
```

**3. 重启 Master 和 Slaver**

---

## 坐标系统

- **x轴**: 左右方向（右为正）
- **y轴**: 前后方向（前为正）
- **z轴**: 垂直方向（通常为0）

例如从入口 [0,0,0] 到卧室 [4,1,0]:
- 向右移动 4 米
- 向前移动 1 米

---

## 测试方法

### 1. Web UI

访问 `http://localhost:7860`，输入自然语言指令。

### 2. 测试脚本

```bash
python test_robot.py
```

### 3. API 测试

```python
import requests
response = requests.post(
    "http://localhost:5000/publish_task",
    json={"task": "前往卧室", "refresh": False}
)
```

### 4. 查看日志

```bash
tail -f slaver/.log/agent.log
```

---

## 常见问题

**Q: 模块没有生效?**
- 确认在 `skill.py` 中导入并注册
- 重启 Slaver 服务
- 查看日志确认模块已注册

**Q: 如何调试?**
- 在函数中添加 `print()` 到 `sys.stderr`
- 查看 Slaver 日志
- 使用测试脚本验证

**Q: 如何添加配置?**
```python
import yaml
with open('config.yaml') as f:
    config = yaml.safe_load(f)
```

---

## 模块快速参考

| 模块 | 功能 | 主要指令 |
|------|------|---------|
| base.py | 底盘导航 | "前往卧室" |
| arm.py | 机械臂控制 | "腕部向上转10度" |
| grasp.py | 抓取控制 | "抓取" |
| real_base.py | 麦轮底盘 | "向前移动" / "去卧室" |

---

## 相关文件

- 场景配置: `master/scene/README.md`
- 测试脚本: `test_robot.py`
- 示例模块: `module/example.py`
- 导航文档: `NAVIGATION_GUIDE.md`
