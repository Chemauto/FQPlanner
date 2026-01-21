#!/bin/bash
# MuJoCo快速测试脚本

echo "==================================="
echo "MuJoCo仿真快速测试"
echo "==================================="
echo ""

# 检查Python环境
echo "[1/3] 检查Python环境..."
python3 --version
echo ""

# 检查依赖
echo "[2/3] 检查MuJoCo依赖..."
python3 -c "import mujoco; print('✓ mujoco:', mujoco.__version__)" 2>/dev/null || echo "✗ mujoco 未安装"
python3 -c "import mujoco.viewer; print('✓ mujoco.viewer 可用')" 2>/dev/null || echo "✗ mujoco.viewer 未安装"
python3 -c "import numpy; print('✓ numpy:', numpy.__version__)" 2>/dev/null || echo "✗ numpy 未安装"
python3 -c "import scipy; print('✓ scipy:', scipy.__version__)" 2>/dev/null || echo "✗ scipy 未安装"
echo ""

# 检查文件
echo "[3/3] 检查项目文件..."
test -f controller/omni_controller.py && echo "✓ omni_controller.py" || echo "✗ omni_controller.py 缺失"
test -f controller/global_navigator.py && echo "✓ global_navigator.py" || echo "✗ global_navigator.py 缺失"
test -f model/assets/scene.xml && echo "✓ scene.xml" || echo "✗ scene.xml 缺失"
test -f test/test_mujoco.py && echo "✓ test_mujoco.py" || echo "✗ test_mujoco.py 缺失"
echo ""

# 提示安装
echo "==================================="
echo "快速测试命令:"
echo "==================================="
echo ""
echo "# 运行MuJoCo测试"
echo "python3 test/test_mujoco.py"
echo ""
echo "# 或通过RoboOS"
echo "cd /home/dora/RoboOs/RoboOS"
echo "python3 slaver/run.py"
echo ""
