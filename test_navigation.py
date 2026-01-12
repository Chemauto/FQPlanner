#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RoboOS 导航功能测试脚本
Test script for RoboOS navigation functionality
"""

import requests
import json
import time

# Master服务地址
MASTER_URL = "http://localhost:5000/publish_task"


def send_task(task: str, refresh: bool = False):
    """
    发送任务到Master服务

    Args:
        task: 自然语言任务描述
        refresh: 是否刷新机器人记忆

    Returns:
        dict: 服务器响应
    """
    payload = {
        "task": task,
        "refresh": refresh
    }

    try:
        print(f"\n{'='*60}")
        print(f"📤 发送任务: {task}")
        print(f"{'='*60}")

        response = requests.post(MASTER_URL, json=payload, timeout=120)

        if response.status_code == 200:
            result = response.json()
            print(f"✅ 任务已成功发送")
            print(f"📋 响应数据:")
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return result
        else:
            print(f"❌ 错误: HTTP {response.status_code}")
            print(f"   {response.text}")
            return None

    except requests.exceptions.ConnectionError:
        print(f"❌ 无法连接到Master服务 ({MASTER_URL})")
        print(f"   请确保Master服务正在运行")
        return None
    except Exception as e:
        print(f"❌ 发生错误: {e}")
        return None


def check_robot_status():
    """检查机器人状态"""
    try:
        response = requests.get("http://localhost:5000/robot_status")
        if response.status_code == 200:
            robots = response.json()
            print(f"\n📊 当前机器人状态:")
            print(json.dumps(robots, indent=2, ensure_ascii=False))
            return robots
        else:
            print(f"❌ 无法获取机器人状态")
            return None
    except Exception as e:
        print(f"❌ 获取状态失败: {e}")
        return None


def check_system_status():
    """检查系统状态"""
    try:
        response = requests.get("http://localhost:5000/system_status")
        if response.status_code == 200:
            status = response.json()
            print(f"\n💻 系统资源状态:")
            print(f"   CPU负载: {status['cpu_load']}%")
            print(f"   内存使用: {status['memory_usage']}%")
            return status
        else:
            print(f"❌ 无法获取系统状态")
            return None
    except Exception as e:
        print(f"❌ 获取系统状态失败: {e}")
        return None


def test_navigation_tasks():
    """测试各种导航任务"""

    print("\n" + "="*60)
    print("🧪 RoboOS 导航功能测试")
    print("="*60)

    # 测试用例列表
    test_cases = [
        # 基础导航测试
        {
            "name": "测试1: 导航到垃圾桶",
            "task": "导航到垃圾桶",
            "delay": 5
        },
        {
            "name": "测试2: 导航到客厅",
            "task": "到客厅",
            "delay": 5
        },
        {
            "name": "测试3: 导航到厨房桌子",
            "task": "去厨房桌子",
            "delay": 5
        },
        {
            "name": "测试4: 导航到卧室",
            "task": "navigate to bedroom",
            "delay": 5
        },
        {
            "name": "测试5: 导航到入口",
            "task": "回到入口",
            "delay": 5
        },

        # 复合导航测试
        {
            "name": "测试6: 多点导航 - 垃圾桶→客厅→卧室",
            "task": "先到垃圾桶，然后去客厅，最后去卧室",
            "delay": 15
        },
        {
            "name": "测试7: 循环导航 - 访问所有桌子",
            "task": "依次访问厨房桌子、服务桌、自定义桌子",
            "delay": 15
        },

        # 相对位置测试
        {
            "name": "测试8: 相对位置描述",
            "task": "到垃圾桶前方",
            "delay": 5
        },

        # 中英文混合测试
        {
            "name": "测试9: 中英文混合",
            "task": "navigate to 垃圾桶",
            "delay": 5
        },
    ]

    # 先检查系统状态
    check_system_status()
    check_robot_status()

    # 询问是否运行所有测试
    print(f"\n📋 共有 {len(test_cases)} 个测试用例")
    choice = input("\n选择测试模式:\n  1. 运行所有测试\n  2. 选择特定测试\n  3. 自定义任务\n请输入选择 (1/2/3): ").strip()

    if choice == "1":
        # 运行所有测试
        print("\n🚀 开始运行所有测试...\n")
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n{'#'*60}")
            print(f"  {test_case['name']}")
            print(f"{'#'*60}")

            send_task(test_case['task'])
            print(f"⏳ 等待 {test_case['delay']} 秒...")
            time.sleep(test_case['delay'])

    elif choice == "2":
        # 选择特定测试
        print("\n请选择要运行的测试:")
        for i, test_case in enumerate(test_cases, 1):
            print(f"  {i}. {test_case['name']}")

        try:
            idx = int(input("\n请输入测试编号 (1-{}): ".format(len(test_cases)))) - 1
            if 0 <= idx < len(test_cases):
                test_case = test_cases[idx]
                print(f"\n{'#'*60}")
                print(f"  {test_case['name']}")
                print(f"{'#'*60}")
                send_task(test_case['task'])
                print(f"\n⏳ 等待 {test_case['delay']} 秒...")
                time.sleep(test_case['delay'])
            else:
                print("❌ 无效的测试编号")
        except ValueError:
            print("❌ 无效的输入")

    elif choice == "3":
        # 自定义任务
        print("\n" + "="*60)
        print("📝 自定义任务模式")
        print("="*60)
        print("\n💡 提示: 你可以输入以下类型的任务:")
        print("   - 简单导航: '到垃圾桶'")
        print("   - 复合导航: '先去客厅，然后去卧室'")
        print("   - 相对位置: '到厨房桌子前方'")
        print("   - 英文描述: 'navigate to livingRoom'")

        while True:
            task = input("\n📝 请输入任务 (输入 'quit' 退出): ").strip()

            if task.lower() == 'quit':
                print("\n👋 退出测试模式")
                break

            if not task:
                continue

            send_task(task)
            time.sleep(5)  # 等待任务执行

    else:
        print("❌ 无效的选择")

    # 最终状态检查
    print("\n" + "="*60)
    print("✅ 测试完成")
    print("="*60)
    check_robot_status()


def main():
    """主函数"""
    print("\n" + "="*60)
    print("🤖 RoboOS 导航功能测试脚本")
    print("="*60)

    # 检查Master服务是否运行
    print("\n🔍 检查Master服务...")
    try:
        response = requests.get("http://localhost:5000/system_status", timeout=2)
        if response.status_code == 200:
            print("✅ Master服务正在运行")
        else:
            print("⚠️  Master服务响应异常")
            return
    except:
        print("❌ 无法连接到Master服务")
        print("   请确保已按照以下步骤启动服务:")
        print("   1. cd master && python run.py")
        print("   2. cd slaver && python run.py")
        return

    # 运行测试
    test_navigation_tasks()


if __name__ == "__main__":
    main()
