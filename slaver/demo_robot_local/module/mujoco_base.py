"""
MuJoCo仿真底盘控制模块 (MuJoCo Simulation Base Control Module)

负责在MuJoCo仿真环境中控制三全向轮底盘的运动。

工具函数:
    - navigate_to_target: 通过位置名称导航（支持中英文）
    - move_base_test: 测试底盘移动（前进、后退、左移、右移、旋转）

辅助函数:
    - load_location_config: 从profile.yaml加载位置配置
    - get_location_coordinates: 获取位置坐标
    - get_model_path: 获取模型路径
"""

import sys
import os
import time
import yaml
import threading
import traceback
import json

# 导入MuJoCo和控制器
try:
    import mujoco
    import mujoco.viewer
    MUJOCO_AVAILABLE = True
except ImportError as e:
    print(f"[mujoco_base] 警告: 未安装MuJoCo: {e}", file=sys.stderr)
    MUJOCO_AVAILABLE = False

# 导入LOCATION_MAP
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../master/scene')))
try:
    import LOCATION_MAP
except ImportError:
    print("[mujoco_base] 警告: 无法导入LOCATION_MAP", file=sys.stderr)

# 全局 Xvfb 进程管理（用于重用同一个 Xvfb 实例）
# 注意：由于 MuJoCo OpenGL 上下文缓存问题，现在每次都强制清理重建
_GLOBAL_XVFB_PROCESS = None
_GLOBAL_XVFB_DISPLAY = None
_GLOBAL_XVFB_LOCK = threading.Lock()

# 导入控制器
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../TestMujoco/controller')))
if MUJOCO_AVAILABLE:
    try:
        from omni_controller import OmniWheelController
        from global_navigator import GlobalNavigator
        CONTROLLER_AVAILABLE = True
    except ImportError as e:
        print(f"[mujoco_base] 警告: 无法导入控制器: {e}", file=sys.stderr)
        CONTROLLER_AVAILABLE = False
else:
    CONTROLLER_AVAILABLE = False


# ============================================================================
# 辅助函数
# ============================================================================

def get_model_path():
    """获取MuJoCo模型文件路径"""
    script_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../TestMujoco'))
    return os.path.join(script_dir, 'model/assets/scene.xml')


def load_location_config():
    """从 profile.yaml 加载位置配置"""
    try:
        profile_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../master/scene/profile.yaml'))
        with open(profile_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        locations = {}
        if 'scene' in config:
            for item in config['scene']:
                if 'position' in item:
                    locations[item['name']] = {
                        'position': item['position'],
                        'description': item.get('description', '')
                    }

        return locations
    except Exception as e:
        print(f"[mujoco_base] 加载配置失败: {e}", file=sys.stderr)
        return {}


def get_location_coordinates(target: str):
    """获取目标位置的坐标

    Args:
        target: 目标位置名称（支持中英文）

    Returns:
        (成功标志, 位置信息字典)
    """
    locations = load_location_config()
    target_en = LOCATION_MAP.LOCATION_MAP.get(target, target)

    if target_en in locations:
        return True, {
            'name': target_en,
            'position': locations[target_en]['position'],
            'description': locations[target_en]['description']
        }

    return False, {'error': f'未找到位置: {target}'}


def cleanup_base():
    """清理MuJoCo仿真环境"""
    print("[mujoco_base] 清理完成", file=sys.stderr)


def initialize_base():
    """初始化MuJoCo仿真环境"""
    print("[mujoco_base] 初始化完成", file=sys.stderr)
    return True


# ============================================================================
# 注册工具函数
# ============================================================================

def register_tools(mcp):
    """注册MuJoCo仿真相关的工具函数到MCP服务器"""

    @mcp.tool()
    async def navigate_to_target(target: str) -> str:
        """导航到目标位置 (Navigate to target location).

        使用PID全局导航控制器，在MuJoCo仿真中精确控制底盘移动到目标位置。
        支持中英文位置名称，会自动从profile.yaml读取坐标。

        工作原理：
            1. 从profile.yaml读取目标位置坐标
            2. 使用LOCATION_MAP进行中英文映射
            3. 调用独立进程进行导航和视频录制
            4. 底盘执行运动直到到达目标

        Args:
            target: 目标位置名称，支持中英文
                   可用位置：卧室, 客厅, 入口, 厨房, 卫生间, 书房
                   或英文：bedroom, living_room, entrance, kitchen, bathroom, study

        Returns:
            导航结果消息（JSON数组格式：[消息, 状态更新]）

        Examples:
            navigate_to_target(target="卧室")
            navigate_to_target(target="bedroom")

        Notes:
            - 位置精度：5cm
            - 在独立进程中运行，避免OpenGL上下文冲突
            - 自动录制视频并保存到 TestMujoco/video 目录
        """
        if not MUJOCO_AVAILABLE:
            return json.dumps(["❌ MuJoCo未安装", {}], ensure_ascii=False)

        # 获取目标位置坐标
        success, location_info = get_location_coordinates(target)

        if not success:
            error_msg = location_info.get('error', '未知错误')
            return json.dumps([f"❌ {error_msg}", {}], ensure_ascii=False)

        target_pos = location_info['position']
        x, y, z = target_pos

        print(f"[mujoco_base] 导航到: {location_info['description']} ({x}, {y}, {z})", file=sys.stderr)

        # 准备调用独立脚本的参数
        import subprocess
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../TestMujoco/run_navigation_standalone.py'))
        video_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../TestMujoco/video'))

        params = {
            'location': location_info['name'],
            'x': float(x),
            'y': float(y),
            'z': float(z),
            'yaw': None,  # 不控制姿态
            'timeout': 30,
            'video_dir': video_dir
        }

        try:
            # 调用独立脚本
            print(f"[mujoco_base] 调用独立脚本: {script_path}", file=sys.stderr)
            result = subprocess.run(
                ['python3', script_path, json.dumps(params)],
                capture_output=True,
                text=True,
                timeout=60  # 超时设置为60秒，留足够时间给导航+视频生成
            )

            if result.returncode != 0:
                error_msg = f"独立脚本执行失败:\n{result.stderr}"
                print(f"[mujoco_base] {error_msg}", file=sys.stderr)
                return json.dumps([f"❌ {error_msg}", {}], ensure_ascii=False)

            # 解析结果
            try:
                nav_result = json.loads(result.stdout.strip())
            except json.JSONDecodeError as e:
                error_msg = f"解析独立脚本结果失败: {e}\n原始输出: {result.stdout}"
                print(f"[mujoco_base] {error_msg}", file=sys.stderr)
                return json.dumps([f"❌ {error_msg}", {}], ensure_ascii=False)

            # 构建返回消息
            if nav_result.get('success'):
                if nav_result.get('reached'):
                    # 成功到达
                    if nav_result.get('video_path'):
                        file_size = os.path.getsize(nav_result['video_path']) / (1024 * 1024) if os.path.exists(nav_result['video_path']) else 0
                        result_msg = f"✅ 已到达 {location_info['description']} ({target}) - 用时 {nav_result.get('steps', 0) * 0.002:.1f}秒\n📹 视频已保存: {nav_result['video_path']} ({file_size:.1f}MB)"
                    else:
                        result_msg = f"✅ 已到达 {location_info['description']} ({target}) - 用时 {nav_result.get('steps', 0) * 0.002:.1f}秒\n⚠️ 视频生成失败"

                    # 状态更新
                    state_updates = {
                        "position": location_info['name'],
                        "coordinates": [float(x), float(y), float(z)]
                    }

                    return json.dumps([result_msg, state_updates], ensure_ascii=False)
                else:
                    # 超时未到达
                    if nav_result.get('video_path'):
                        file_size = os.path.getsize(nav_result['video_path']) / (1024 * 1024) if os.path.exists(nav_result['video_path']) else 0
                        timeout_msg = f"❌ 导航超时 - 最后位置: {nav_result.get('final_position', [])[:2]}\n📹 视频已保存: {nav_result['video_path']} ({file_size:.1f}MB)"
                    else:
                        timeout_msg = f"❌ 导航超时 - 最后位置: {nav_result.get('final_position', [])[:2]}"

                    return json.dumps([timeout_msg, {}], ensure_ascii=False)
            else:
                # 独立脚本报告错误
                error_msg = f"导航失败: {nav_result.get('error', '未知错误')}"
                return json.dumps([f"❌ {error_msg}", {}], ensure_ascii=False)

        except subprocess.TimeoutExpired:
            error_msg = "独立脚本执行超时（60秒）"
            print(f"[mujoco_base] {error_msg}", file=sys.stderr)
            return json.dumps([f"❌ {error_msg}", {}], ensure_ascii=False)
        except Exception as e:
            error_msg = f"导航失败: {str(e)}"
            print(f"[mujoco_base] {error_msg}", file=sys.stderr)
            print(f"[mujoco_base] {traceback.format_exc()}", file=sys.stderr)
            return json.dumps([f"❌ {error_msg}", {}], ensure_ascii=False)

    @mcp.tool()
    async def move_base_test(test_mode: str = "auto") -> str:
        """测试底盘移动 (Test base movement).

        在MuJoCo仿真环境中测试三麦克纳姆轮底盘的基本移动功能。
        会打开仿真界面并执行移动测试。

        Args:
            test_mode: 测试模式
                      "auto" - 自动演示所有移动（默认）
                      "1" - 前进测试
                      "2" - 后退测试
                      "3" - 左移测试
                      "4" - 右移测试
                      "5" - 旋转测试

        Returns:
            测试结果消息

        Examples:
            move_base_test(test_mode="auto")  # 自动演示
            move_base_test(test_mode="1")    # 前进测试

        Notes:
            - 会打开MuJoCo仿真界面
            - 每个测试持续2秒
        """
        if not MUJOCO_AVAILABLE:
            return "❌ MuJoCo未安装"
        if not CONTROLLER_AVAILABLE:
            return "❌ 控制器模块不可用"

        # 加载模型
        try:
            model_path = get_model_path()
            print(f"[mujoco_base] 加载模型: {model_path}", file=sys.stderr)
            model = mujoco.MjModel.from_xml_path(model_path)
            data = mujoco.MjData(model)
            controller = OmniWheelController(model, data)
        except Exception as e:
            return f"❌ 初始化失败: {str(e)}"

        # 定义测试动作
        test_actions = {
            "1": ("前进", 0.3, 1, 0, 0),
            "2": ("后退", 0.3, -1, 0, 0),
            "3": ("左移", 0.3, 0, 1, 0),
            "4": ("右移", 0.3, 0, -1, 0),
            "5": ("旋转", 0.0, 0, 0, 0.5),
        }

        result_summary = []
        duration = 2.0  # 每个测试2秒

        try:
            # 尝试创建渲染器（用于视频录制）
            renderer = None
            frames_dir = None
            video_enabled = False
            xvfb_process = None
            original_display = os.environ.get('DISPLAY')

            # 声明全局变量
            global _GLOBAL_XVFB_PROCESS, _GLOBAL_XVFB_DISPLAY

            try:
                import tempfile
                import subprocess
                from PIL import Image
                import signal

                # 检查是否需要启动 Xvfb（无头环境）
                display = os.environ.get('DISPLAY')
                if display is None:
                    with _GLOBAL_XVFB_LOCK:
                        print("[mujoco_base] 检测到无头环境，启动 Xvfb 虚拟显示...", file=sys.stderr)

                        # 强制清理所有 Xvfb 和 socket 文件
                        try:
                            # 杀掉所有 Xvfb 进程
                            result = subprocess.run(['pgrep', 'Xvfb'], capture_output=True, text=True)
                            if result.returncode == 0:
                                pids = result.stdout.strip().split('\n')
                                for pid in pids:
                                    if pid:
                                        try:
                                            os.kill(int(pid), signal.SIGKILL)
                                        except (ProcessLookupError, ValueError):
                                            pass

                            # 清理所有 X server socket 文件
                            import glob
                            socket_files = glob.glob('/tmp/.X11-unix/X*')
                            for socket_file in socket_files:
                                try:
                                    os.remove(socket_file)
                                except (FileNotFoundError, PermissionError):
                                    pass

                            # 清理锁文件
                            lock_files = glob.glob('/tmp/.X*-lock')
                            for lock_file in lock_files:
                                try:
                                    os.remove(lock_file)
                                except (FileNotFoundError, PermissionError):
                                    pass

                            time.sleep(0.5)  # 等待清理完成
                        except Exception as e:
                            print(f"[mujoco_base] 清理警告: {e}", file=sys.stderr)

                        # 重置全局变量
                        _GLOBAL_XVFB_PROCESS = None
                        _GLOBAL_XVFB_DISPLAY = None

                        # 启动新的 Xvfb（固定 display 号）
                        display_str = ':99'
                        xvfb_process = subprocess.Popen([
                            'Xvfb', display_str, '-screen', '0', '1024x768x24'
                        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        os.environ['DISPLAY'] = display_str
                        time.sleep(0.8)  # 等待 Xvfb 完全启动

                        # 保存到全局变量
                        _GLOBAL_XVFB_PROCESS = xvfb_process
                        _GLOBAL_XVFB_DISPLAY = display_str
                        print(f"[mujoco_base] Xvfb 已启动 (DISPLAY={display_str}, PID={xvfb_process.pid})", file=sys.stderr)

                frames_dir = tempfile.mkdtemp(prefix=f"mujoco_test_{test_mode}_")

                # 创建俯视相机
                camera = mujoco.MjvCamera()
                mujoco.mjv_defaultCamera(camera)
                # 设置俯视视角：相机在高度2.5m处，向下看
                camera.distance = 2.5
                camera.elevation = 89  # 接近90度，俯视
                camera.azimuth = 0    # 朝向x轴正向
                camera.lookat = [0, 0, 0]  # 看向原点

                renderer = mujoco.Renderer(model, height=480, width=640)
                video_enabled = True
                print("[mujoco_base] 使用俯视视角录制视频...", file=sys.stderr)
                print(f"[mujoco_base] 使用无GUI模式测试: {test_mode} (将录制视频)", file=sys.stderr)
                print(f"[mujoco_base] 帧图像保存到: {frames_dir}", file=sys.stderr)
            except Exception as e:
                print(f"[mujoco_base] 无法创建渲染器: {e}", file=sys.stderr)
                print(f"[mujoco_base] 使用无GUI模式测试: {test_mode} (无视频录制)", file=sys.stderr)
                video_enabled = False
                # 清理 Xvfb（如果启动了）
                if xvfb_process is not None:
                    xvfb_process.terminate()
                    xvfb_process.wait()
                    xvfb_process = None
                # 恢复原始 DISPLAY
                if original_display is not None:
                    os.environ['DISPLAY'] = original_display
                elif 'DISPLAY' in os.environ:
                    del os.environ['DISPLAY']

            # 先运行几步仿真来初始化机器人状态
            print("[mujoco_base] 初始化机器人状态...", file=sys.stderr)
            for _ in range(100):
                mujoco.mj_step(model, data)

            frame_count = 0
            step_count = 0

            if test_mode == "auto":
                # 自动演示所有模式
                for mode_id, (name, speed, vx, vy, omega) in test_actions.items():
                    print(f"[mujoco_base] 执行: {name}", file=sys.stderr)

                    start_time = time.time()
                    start_pos = controller.get_robot_position().copy()

                    # 运行仿真并录制
                    while time.time() - start_time < duration:
                        controller.set_velocity(speed, vx, vy, omega)
                        controller.apply_control()
                        mujoco.mj_step(model, data)

                        # 每10步保存一帧（仅当视频启用时）
                        if video_enabled and step_count % 10 == 0:
                            renderer.update_scene(data, camera=camera)
                            pixels = renderer.render()
                            frame_path = os.path.join(frames_dir, f"frame_{frame_count:05d}.png")
                            img = Image.fromarray(pixels)
                            img.save(frame_path)
                            frame_count += 1
                        step_count += 1

                    end_pos = controller.get_robot_position()
                    displacement = end_pos - start_pos
                    result_summary.append(f"{name}: 位移=[{displacement[0]:.3f}, {displacement[1]:.3f}]")

                    # 短暂停顿（继续录制）
                    for _ in range(30):
                        controller.stop()
                        controller.apply_control()
                        mujoco.mj_step(model, data)
                        if video_enabled and step_count % 10 == 0:
                            renderer.update_scene(data, camera=camera)
                            pixels = renderer.render()
                            frame_path = os.path.join(frames_dir, f"frame_{frame_count:05d}.png")
                            img = Image.fromarray(pixels)
                            img.save(frame_path)
                            frame_count += 1
                        step_count += 1

                # 关闭渲染器（如果存在）
                if renderer is not None:
                    renderer.close()

                # 根据是否启用视频生成不同的消息
                if video_enabled:
                    # 使用ffmpeg将图像转换为视频
                    video_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../TestMujoco/video'))
                    os.makedirs(video_dir, exist_ok=True)
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    video_path = os.path.join(video_dir, f"test_{test_mode}_{timestamp}.mp4")

                    print(f"[mujoco_base] 正在生成视频: {video_path}", file=sys.stderr)

                    # 使用ffmpeg转换
                    try:
                        subprocess.run([
                            'ffmpeg', '-y', '-framerate', '30',
                            '-i', os.path.join(frames_dir, 'frame_%05d.png'),
                            '-c:v', 'libx264', '-preset', 'fast',
                            '-pix_fmt', 'yuv420p', video_path
                        ], check=True, capture_output=True)

                        file_size = os.path.getsize(video_path) / (1024 * 1024)  # MB
                        result_msg = "✅ 自动演示完成\n" + "\n".join(result_summary) + f"\n📹 视频已保存: {video_path} ({file_size:.1f}MB)"
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        result_msg = "✅ 自动演示完成\n" + "\n".join(result_summary) + f"\n⚠️ 视频生成失败（ffmpeg未安装），帧图像保存在: {frames_dir}"

                    # 清理临时文件
                    import shutil
                    shutil.rmtree(frames_dir, ignore_errors=True)
                else:
                    result_msg = "✅ 自动演示完成\n" + "\n".join(result_summary) + "\n(无视频录制 - 无头环境)"

                # 清理 Xvfb（如果启动了）- 强制清理
                if xvfb_process is not None:
                    xvfb_process.terminate()
                    xvfb_process.wait()
                    print("[mujoco_base] Xvfb 已关闭", file=sys.stderr)
                    # 清理全局变量
                    _GLOBAL_XVFB_PROCESS = None
                    _GLOBAL_XVFB_DISPLAY = None
                # 恢复原始 DISPLAY
                if original_display is not None:
                    os.environ['DISPLAY'] = original_display
                elif 'DISPLAY' in os.environ:
                    del os.environ['DISPLAY']

            elif test_mode in test_actions:
                # 单个测试
                name, speed, vx, vy, omega = test_actions[test_mode]
                print(f"[mujoco_base] 执行: {name}", file=sys.stderr)

                start_pos = controller.get_robot_position().copy()
                start_time = time.time()

                # 运行仿真并录制
                while time.time() - start_time < duration:
                    controller.set_velocity(speed, vx, vy, omega)
                    controller.apply_control()
                    mujoco.mj_step(model, data)

                    # 每10步保存一帧（仅当视频启用时）
                    if video_enabled and step_count % 10 == 0:
                        renderer.update_scene(data, camera=camera)
                        pixels = renderer.render()
                        frame_path = os.path.join(frames_dir, f"frame_{frame_count:05d}.png")
                        img = Image.fromarray(pixels)
                        img.save(frame_path)
                        frame_count += 1
                    step_count += 1

                controller.stop()
                controller.apply_control()

                end_pos = controller.get_robot_position()
                displacement = end_pos - start_pos

                # 关闭渲染器（如果存在）
                if renderer is not None:
                    renderer.close()

                # 根据是否启用视频生成不同的消息
                if video_enabled:
                    # 使用ffmpeg将图像转换为视频
                    video_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../TestMujoco/video'))
                    os.makedirs(video_dir, exist_ok=True)
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    video_path = os.path.join(video_dir, f"test_{test_mode}_{timestamp}.mp4")

                    print(f"[mujoco_base] 正在生成视频: {video_path}", file=sys.stderr)

                    # 使用ffmpeg转换
                    try:
                        subprocess.run([
                            'ffmpeg', '-y', '-framerate', '30',
                            '-i', os.path.join(frames_dir, 'frame_%05d.png'),
                            '-c:v', 'libx264', '-preset', 'fast',
                            '-pix_fmt', 'yuv420p', video_path
                        ], check=True, capture_output=True)

                        file_size = os.path.getsize(video_path) / (1024 * 1024)  # MB
                        result_msg = f"✅ {name}测试完成\n起始位置: {start_pos[:2]}\n结束位置: {end_pos[:2]}\n位移: {displacement[:2]}\n📹 视频已保存: {video_path} ({file_size:.1f}MB)"
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        result_msg = f"✅ {name}测试完成\n起始位置: {start_pos[:2]}\n结束位置: {end_pos[:2]}\n位移: {displacement[:2]}\n⚠️ 视频生成失败（ffmpeg未安装），帧图像保存在: {frames_dir}"

                    # 清理临时文件
                    import shutil
                    shutil.rmtree(frames_dir, ignore_errors=True)
                else:
                    result_msg = f"✅ {name}测试完成\n起始位置: {start_pos[:2]}\n结束位置: {end_pos[:2]}\n位移: {displacement[:2]}\n(无视频录制 - 无头环境)"

                # 清理 Xvfb（如果启动了）- 强制清理
                if xvfb_process is not None:
                    xvfb_process.terminate()
                    xvfb_process.wait()
                    print("[mujoco_base] Xvfb 已关闭", file=sys.stderr)
                    # 清理全局变量
                    _GLOBAL_XVFB_PROCESS = None
                    _GLOBAL_XVFB_DISPLAY = None
                # 恢复原始 DISPLAY
                if original_display is not None:
                    os.environ['DISPLAY'] = original_display
                elif 'DISPLAY' in os.environ:
                    del os.environ['DISPLAY']
            else:
                if renderer is not None:
                    renderer.close()
                if frames_dir is not None:
                    import shutil
                    shutil.rmtree(frames_dir, ignore_errors=True)
                if xvfb_process is not None:
                    xvfb_process.terminate()
                    xvfb_process.wait()
                    # 清理全局变量
                    _GLOBAL_XVFB_PROCESS = None
                    _GLOBAL_XVFB_DISPLAY = None
                # 恢复原始 DISPLAY
                if original_display is not None:
                    os.environ['DISPLAY'] = original_display
                elif 'DISPLAY' in os.environ:
                    del os.environ['DISPLAY']
                result_msg = f"❌ 无效的测试模式: {test_mode}"

            return result_msg

        except Exception as e:
            error_msg = f"❌ 测试失败: {str(e)}\n{traceback.format_exc()}"
            print(f"[mujoco_base] {error_msg}", file=sys.stderr)
            return error_msg

    print("[mujoco_base.py] MuJoCo仿真模块已注册 (2个工具函数)", file=sys.stderr)
