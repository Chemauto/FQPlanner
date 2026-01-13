#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RoboOS 机器人功能统一测试脚本
Universal test script for RoboOS robot functionality

支持测试所有模块：底盘、机械臂等
Supports testing all modules: base, arm, etc.
"""

import requests
import json
import time

# Master服务地址
MASTER_URL = "http://localhost:5000/publish_task"


# ============================================================================
# 测试用例定义
# ============================================================================

TEST_CASES = {
    "base": [
        # 底盘控制模块测试
        {
            "name": "导航到卧室",
            "task": "前往卧室",
            "delay": 5
        },
        {
            "name": "导航到客厅",
            "task": "到客厅",
            "delay": 5
        },
        {
            "name": "导航到厨房桌子",
            "task": "去厨房桌子",
            "delay": 5
        },
        {
            "name": "导航到入口",
            "task": "回到入口",
            "delay": 5
        },
        {
            "name": "导航到垃圾桶",
            "task": "导航到垃圾桶",
            "delay": 5
        },
        {
            "name": "多点导航 - 厨房→客厅→卧室",
            "task": "先去厨房桌子，然后到客厅，最后去卧室",
            "delay": 15
        },
        {
            "name": "循环导航 - 访问所有桌子",
            "task": "依次访问厨房桌子、服务桌、自定义桌子",
            "delay": 15
        },
    ],
    "arm": [
        # 机械臂控制模块测试
        {
            "name": "机械臂复位",
            "task": "机械臂复位到零点",
            "delay": 8
        },
        {
            "name": "相对角度移动 - 腕部",
            "task": "腕部向上转动10度",
            "delay": 5
        },
        {
            "name": "绝对角度移动 - 夹爪",
            "task": "夹爪移动到50的位置",
            "delay": 5
        },
        {
            "name": "获取关节位置",
            "task": "获取所有关节的位置",
            "delay": 3
        },
        {
            "name": "复合动作",
            "task": "先将机械臂复位，然后腕部转动15度，最后夹爪闭合到30",
            "delay": 12
        },
    ],
    "all": []  # 动态生成
}

# 动态生成 "all" 类别的测试用例
TEST_CASES["all"] = TEST_CASES["base"] + TEST_CASES["arm"]


# ============================================================================
# 核心功能函数
# ============================================================================

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


# ============================================================================
# 测试执行函数
# ============================================================================

def run_all_tests(module: str):
    """运行所有测试用例"""
    test_cases = TEST_CASES.get(module, [])

    if not test_cases:
        print(f"❌ 模块 '{module}' 没有测试用例")
        return

    print(f"\n🚀 开始运行 {len(test_cases)} 个测试用例...\n")

    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{'#'*60}")
        print(f"  测试 {i}/{len(test_cases)}: {test_case['name']}")
        print(f"{'#'*60}")

        send_task(test_case['task'])
        print(f"⏳ 等待 {test_case['delay']} 秒...")
        time.sleep(test_case['delay'])


def run_specific_test(module: str):
    """运行特定测试用例"""
    test_cases = TEST_CASES.get(module, [])

    if not test_cases:
        print(f"❌ 模块 '{module}' 没有测试用例")
        return

    print("\n请选择要运行的测试:")
    for i, test_case in enumerate(test_cases, 1):
        print(f"  {i}. {test_case['name']}")

    try:
        idx = int(input(f"\n请输入测试编号 (1-{len(test_cases)}): ")) - 1
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


def run_custom_test():
    """自定义任务测试"""
    print("\n" + "="*60)
    print("📝 自定义任务模式")
    print("="*60)
    print("\n💡 提示: 你可以输入以下类型的任务:")
    print("   - 导航: '前往卧室', '到客厅'")
    print("   - 机械臂: '机械臂复位', '腕部转动10度'")
    print("   - 复合: '先去卧室，然后机械臂复位'")
    print("   - 输入 'quit' 退出")

    while True:
        task = input("\n📝 请输入任务: ").strip()

        if task.lower() == 'quit':
            print("\n👋 退出测试模式")
            break

        if not task:
            continue

        send_task(task)
        time.sleep(5)  # 等待任务执行


def select_module():
    """选择测试模块"""
    print("\n请选择测试模块:")
    print("  1. 底盘控制模块 (base) - 7个测试用例")
    print("  2. 机械臂控制模块 (arm) - 5个测试用例")
    print("  3. 所有模块 (all) - 12个测试用例")

    choice_map = {
        "1": "base",
        "2": "arm",
        "3": "all"
    }

    while True:
        choice = input("\n请输入选择 (1/2/3): ").strip()
        if choice in choice_map:
            return choice_map[choice]
        print("❌ 无效的选择，请重新输入")


def select_test_mode(module: str):
    """选择测试模式"""
    test_cases = TEST_CASES.get(module, [])
    print(f"\n📋 '{module}' 模块共有 {len(test_cases)} 个测试用例")
    print("\n选择测试模式:")
    print("  1. 运行所有测试")
    print("  2. 选择特定测试")
    print("  3. 自定义任务")

    while True:
        choice = input("\n请输入选择 (1/2/3): ").strip()
        if choice == "1":
            run_all_tests(module)
            break
        elif choice == "2":
            run_specific_test(module)
            break
        elif choice == "3":
            run_custom_test()
            break
        else:
            print("❌ 无效的选择，请重新输入")


# ============================================================================
# 主函数
# ============================================================================

def main():
    """主函数"""
    print("\n" + "="*60)
    print("🤖 RoboOS 机器人功能统一测试脚本")
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
    except Exception:
        print("❌ 无法连接到Master服务")
        print("\n请确保已按照以下步骤启动服务:")
        print("   1. 启动模型: bash Modeldeploy/start_server.sh")
        print("   2. 启动Master: python master/run.py")
        print("   3. 启动Slaver: python slaver/run.py")
        return

    # 先检查系统状态
    check_system_status()
    check_robot_status()

    # 选择模块
    module = select_module()

    # 选择测试模式并执行
    select_test_mode(module)

    # 最终状态检查
    print("\n" + "="*60)
    print("✅ 测试完成")
    print("="*60)
    check_robot_status()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 测试已中断")
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
