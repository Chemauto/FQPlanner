"""
RoboOS 机器人模块包 (Robot Module Package)

此包包含所有机器人功能模块：
- base: 底盘控制模块
- arm: 机械臂控制模块
- grasp: 抓取控制模块
- example: 示例模块（模板）

说明：
- 此 __init__.py 文件主要用于 IDE 自动补全和代码提示
- 在 skill.py 中添加新模块时，可以直接导入，无需修改此文件
- 例如：from module.camera import register_tools as register_camera_tools
"""

# 导入核心模块
from .base import register_tools as register_base_tools
from .arm import register_tools as register_arm_tools, cleanup_arm, initialize_arm
from .grasp import register_tools as register_grasp_tools
from .example import register_tools as register_example_tools

# 可选：如果需要完整的 __all__ 导出列表，可以手动添加新模块
# 但实际上 skill.py 可以直接导入新模块，不需要在这里声明
__all__ = [
    'register_base_tools',
    'register_arm_tools',
    'cleanup_arm',
    'initialize_arm',
    'register_grasp_tools',
    'register_example_tools',
    # 添加新模块时，可以在这里添加，也可以在 skill.py 中直接导入
    # 'register_camera_tools',  # 示例：新增相机模块
]
