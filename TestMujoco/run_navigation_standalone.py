#!/usr/bin/env python3
"""
独立MuJoCo导航脚本 - 在单独进程中运行以避免OpenGL上下文问题

这个脚本独立处理MuJoCo仿真、导航控制和视频录制。

使用方式:
    python3 run_navigation_standalone.py (参数通过stdin传递JSON)

输入格式(JSON):
    {
        "location": "bedroom",
        "x": 1.5,
        "y": 0.0,
        "z": 0.0,
        "yaw": 0.0,
        "timeout": 30,
        "video_dir": "/path/to/video"
    }
"""

import sys
import os
import json
import subprocess
import time
import glob
import shutil
from pathlib import Path

# 添加路径
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / 'controller'))

import mujoco
import numpy as np
from PIL import Image

# 导入控制器
from controller.global_navigator import GlobalNavigator
from controller.omni_controller import OmniWheelController

# 位置映射
LOCATION_MAP = {
    "入口": "entrance",
    "entrance": "entrance",
    "客厅": "living_room",
    "living_room": "living_room",
    "厨房": "kitchen",
    "kitchen": "kitchen",
    "卧室": "bedroom",
    "bedroom": "bedroom",
    "卫生间": "bathroom",
    "bathroom": "bathroom",
    "书房": "study",
    "study": "study"
}

# 位置坐标 (x, y, z, yaw)
LOCATION_COORDS = {
    "entrance": (0.0, 0.0, 0.0, 0.0),
    "living_room": (1.5, 1.0, 0.0, np.pi/4),
    "kitchen": (1.5, -1.0, 0.0, -np.pi/4),
    "bedroom": (-1.0, 1.5, 0.0, np.pi/2),
    "bathroom": (-1.5, -1.5, 0.0, -np.pi/2),
    "study": (0.5, 2.0, 0.0, 0.0)
}


def run_navigation(params):
    """
    在独立进程中运行导航

    参数:
        params: dict包含 location, x, y, z, yaw, timeout, video_dir, start_position, start_yaw

    返回:
        dict包含结果状态和视频路径
    """
    location = params['location']
    x = params['x']
    y = params['y']
    z = params['z']
    yaw = params['yaw']
    timeout = params['timeout']
    video_dir = params['video_dir']

    # 获取起始位置（如果提供）
    start_position = params.get('start_position', [0.0, 0.0, 0.0])
    start_yaw = params.get('start_yaw', 0.0)

    # 创建视频目录
    os.makedirs(video_dir, exist_ok=True)

    # 设置Xvfb显示
    display = ':100'
    frame_dir = '/tmp/mujoco_frames_temp'

    xvfb = None

    try:
        # 杀死任何现有的Xvfb进程
        subprocess.run(['pkill', '-9', 'Xvfb'],
                      stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL)

        # 清理socket文件
        time.sleep(0.2)
        for f in glob.glob('/tmp/.X11-unix/X*'):
            try:
                os.remove(f)
            except:
                pass
        for f in glob.glob('/tmp/.X*-lock'):
            try:
                os.remove(f)
            except:
                pass

        time.sleep(0.3)

        # 启动新的Xvfb
        xvfb = subprocess.Popen([
            'Xvfb', display,
            '-screen', '0', '1024x768x24',
            '-ac', '+render', '-nolisten', 'tcp'
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        os.environ['DISPLAY'] = display
        time.sleep(1.0)

        # 创建帧目录
        os.makedirs(frame_dir, exist_ok=True)

        # 加载MuJoCo模型
        model_path = os.path.join(os.path.dirname(__file__), 'model', 'assets', 'scene.xml')
        model = mujoco.MjModel.from_xml_path(model_path)
        data = mujoco.MjData(model)

        # 设置机器人到起始位置
        robot_body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, 'base_plate_layer_1_link')

        # 设置位置（qpos[0:3]）和四元数（qpos[3:7]，默认朝向）
        data.qpos[0:3] = start_position
        data.qpos[3:7] = [1.0, 0.0, 0.0, 0.0]  # 单位四元数，朝向x轴正向

        # 清零速度
        data.qvel[0:6] = 0.0

        print(f"[独立进程] 设置起始位置: {start_position}", file=sys.stderr)

        # 预热仿真（让机器人位置稳定）
        for i in range(200):
            mujoco.mj_step(model, data)
            if i == 100:
                # 中间再次确认位置
                current_pos = data.qpos[0:3].copy()
                print(f"[独立进程] 预热中位置: {current_pos}", file=sys.stderr)

        # 创建导航器和控制器
        navigator = GlobalNavigator(model, data)
        omni_controller = OmniWheelController(model, data)

        # 设置目标
        navigator.set_target(x, y, z, yaw)

        # 设置相机（俯视视角，固定看向原点，保持所有视频坐标系一致）
        camera = mujoco.MjvCamera()
        mujoco.mjv_defaultCamera(camera)
        camera.distance = 2.5
        camera.elevation = 89  # 俯视
        camera.azimuth = 0
        # 固定看向原点，所有视频使用相同坐标系
        camera.lookat = [0.0, 0.0, 0.0]

        # 设置渲染器
        renderer = mujoco.Renderer(model, height=480, width=640)

        # 仿真循环
        dt = model.opt.timestep
        start_time = time.time()
        step_count = 0
        frame_count = 0
        reached = False
        final_pos = None
        final_yaw = None

        print(f"[独立进程] 开始导航到 {location}...", file=sys.stderr)

        while time.time() - start_time < timeout:
            # 更新导航器
            vx_robot, vy_robot, omega = navigator.update(dt)

            # 使用OmniWheelController应用控制
            omni_controller.set_velocity_raw(vx_robot, vy_robot, omega)
            omni_controller.apply_control()

            # 步进仿真
            mujoco.mj_step(model, data)
            step_count += 1

            # 每10步捕获一帧
            if step_count % 10 == 0:
                renderer.update_scene(data, camera=camera)
                pixels = renderer.render()
                img = Image.fromarray(pixels)
                frame_path = os.path.join(frame_dir, f'frame_{frame_count:04d}.png')
                img.save(frame_path)
                frame_count += 1

            # 检查是否到达
            if navigator.is_target_reached():
                reached = True
                final_pos, final_yaw = navigator.get_robot_state()
                print(f"[独立进程] 在第{step_count}步到达目标!", file=sys.stderr)
                break

        # 如果未到达则获取最终状态
        if final_pos is None:
            final_pos, final_yaw = navigator.get_robot_state()

        # 生成视频
        timestamp = int(time.time())
        if reached:
            video_filename = f'navigate_{location}_{timestamp}.mp4'
        else:
            video_filename = f'navigate_{location}_timeout_{timestamp}.mp4'

        video_path = os.path.join(video_dir, video_filename)

        if frame_count > 0:
            # 使用ffmpeg创建视频
            result = subprocess.run([
                'ffmpeg', '-y',
                '-framerate', '30',
                '-i', os.path.join(frame_dir, 'frame_%04d.png'),
                '-c:v', 'libx264',
                '-preset', 'fast',
                '-pix_fmt', 'yuv420p',
                video_path
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            if result.returncode == 0:
                print(f"[独立进程] 视频已保存: {video_path}", file=sys.stderr)
            else:
                print(f"[独立进程] FFmpeg失败", file=sys.stderr)
                video_path = None
        else:
            print(f"[独立进程] 未捕获帧", file=sys.stderr)
            video_path = None

        # 清理
        renderer.close()

        # 终止Xvfb
        xvfb.terminate()
        xvfb.wait(timeout=2)
        if xvfb.poll() is None:
            xvfb.kill()
            xvfb.wait()

        # 清理帧目录
        shutil.rmtree(frame_dir, ignore_errors=True)

        # 返回结果
        result = {
            'success': True,
            'reached': reached,
            'video_path': video_path,
            'final_position': final_pos.tolist(),
            'final_yaw': float(final_yaw),
            'steps': step_count,
            'location': location
        }

        return result

    except Exception as e:
        print(f"[独立进程] 错误: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)

        # 尝试清理
        try:
            if xvfb is not None:
                xvfb.terminate()
                xvfb.wait(timeout=1)
        except:
            pass

        return {
            'success': False,
            'error': str(e),
            'location': location
        }


def main():
    """主入口 - 从stdin读取参数"""
    if len(sys.argv) > 1:
        # 通过命令行传递参数
        params = json.loads(sys.argv[1])
    else:
        # 从stdin读取
        line = sys.stdin.readline()
        params = json.loads(line)

    result = run_navigation(params)

    # 输出结果为JSON
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
