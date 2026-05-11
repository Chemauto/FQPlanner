"""
机器人模块包
- base: 底盘控制模块
- example: 示例模块（模板）
"""

from .base import register_tools as register_base_tools
from .example import register_tools as register_example_tools

__all__ = [
    'register_base_tools',
    'register_example_tools',
]
