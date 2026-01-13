"""
RoboOS 机器人技能统一入口 (Robot Skills Entry Point)

这是 RoboOS 机器人系统的主入口文件，负责：
1. 初始化 MCP 服务器
2. 导入并注册所有功能模块
3. 管理信号处理和资源清理

模块列表：
    - base.py: 底盘控制模块（导航、移动）
    - arm.py: 机械臂控制模块（关节运动、复位）
    - grasp.py: 抓取控制模块（通过开发板抓取物体）
    - example.py: 示例模块（添加新功能的参考模板）

添加新功能：
    1. 创建新的模块文件（参考 example.py）
    2. 在下面导入模块的 register_tools 函数
    3. 在 main() 函数中调用 register_tools(mcp)
"""

import sys
import os
import signal
import atexit
from mcp.server.fastmcp import FastMCP

# ==============================================================================
# 1. 导入各功能模块的注册函数
# ==============================================================================
from base import register_tools as register_base_tools
from arm import register_tools as register_arm_tools, cleanup_arm, initialize_arm
from grasp import register_tools as register_grasp_tools
from example import register_tools as register_example_tools

# ==============================================================================
# 2. 全局变量和初始化
# ==============================================================================

# Initialize FastMCP server
mcp = FastMCP("robots")


def signal_handler(signum, frame):
    """信号处理器 - 处理Ctrl+C等信号"""
    print(f"\n[skill.py] 收到信号 {signum}，正在清理资源...", file=sys.stderr)
    cleanup_arm()
    sys.exit(0)


# 注册退出处理函数
atexit.register(cleanup_arm)
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# ==============================================================================
# 3. 注册所有模块的工具函数
# ==============================================================================

def register_all_modules():
    """
    注册所有功能模块到 MCP 服务器

    在这里添加新模块的注册调用：
        module_name.register_tools(mcp)
    """
    print("=" * 60, file=sys.stderr)
    print("[skill.py] 开始注册机器人技能模块...", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    # 注册底盘控制模块
    register_base_tools(mcp)

    # 注册机械臂控制模块
    register_arm_tools(mcp)

    # 注册抓取控制模块
    register_grasp_tools(mcp)

    # 注册示例模块（可选，实际使用时可以注释掉）
    # register_example_tools(mcp)

    # 在这里添加新模块的注册，例如：
    # from camera import register_tools as register_camera_tools
    # register_camera_tools(mcp)

    # from sensor import register_tools as register_sensor_tools
    # register_sensor_tools(mcp)

    print("=" * 60, file=sys.stderr)
    print("[skill.py] ✓ 所有模块注册完成", file=sys.stderr)
    print("=" * 60, file=sys.stderr)


# ==============================================================================
# 4. 主函数
# ==============================================================================

if __name__ == "__main__":
    # 显示启动信息
    print("\n" + "=" * 60, file=sys.stderr)
    print("[skill.py] RoboOS 机器人技能服务器启动中...", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    print(f"[skill.py] 工作目录: {os.getcwd()}", file=sys.stderr)
    print(f"[skill.py] Python版本: {sys.version}", file=sys.stderr)
    print("=" * 60 + "\n", file=sys.stderr)

    # 注册所有模块
    register_all_modules()

    # 显示服务器信息
    print("\n[skill.py] MCP 服务器准备就绪，等待工具调用...", file=sys.stderr)
    print("[skill.py] 按 Ctrl+C 停止服务器\n", file=sys.stderr)

    # 启动 MCP 服务器
    try:
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
        print("\n[skill.py] 服务器已停止", file=sys.stderr)
    except Exception as e:
        print(f"\n[skill.py] ✗ 服务器错误: {e}", file=sys.stderr)
        sys.exit(1)
