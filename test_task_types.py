#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script to verify task type understanding.
This tests various task descriptions to ensure the LLM correctly identifies tool usage.
"""

import requests
import time

def send_task(task_description):
    """Send a task to the master server."""
    url = "http://localhost:5000/publish_task"
    task_data = {
        "task": [task_description],
        "task_id": f"test_{int(time.time())}",
        "refresh": False
    }

    print(f"\n{'='*60}")
    print(f"Task: {task_description}")
    print(f"{'='*60}")

    try:
        response = requests.post(url, json=task_data, timeout=60)
        if response.status_code == 200:
            result = response.json()
            print(f"✓ Task sent successfully")
            return result
        else:
            print(f"✗ Error: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"✗ Error: {e}")
        return None

if __name__ == "__main__":
    print("="*60)
    print("Task Type Understanding Test")
    print("="*60)
    print("\nThis test verifies that the LLM correctly:")
    print("1. Identifies navigation tasks (navigate_to_target)")
    print("2. Identifies movement tasks (move with parameters)")
    print("3. Handles various phrasings (go to, move from, navigate to)")

    # Test 1: Standard navigate
    print("\n### Test 1: Standard navigate ###")
    send_task("Navigate to bedroom")

    time.sleep(3)

    # Test 2: "Go to" phrasing
    print("\n### Test 2: 'Go to' phrasing ###")
    send_task("Go to kitchen")

    time.sleep(3)

    # Test 3: "Move from X to Y" phrasing (the problematic one)
    print("\n### Test 3: 'Move from X to Y' phrasing ###")
    send_task("Move from living room to bedroom")

    time.sleep(3)

    # Test 4: Movement with parameters
    print("\n### Test 4: Movement with parameters ###")
    send_task("Move forward at 1 m/s for 2 seconds")

    time.sleep(3)

    # Test 5: Complex multi-step
    print("\n### Test 5: Multi-location navigation ###")
    send_task([
        "Go to trash can",
        "Move from trash can to living room",
        "Navigate to bedroom"
    ])

    time.sleep(8)

    print("\n" + "="*60)
    print("Test Complete!")
    print("="*60)
    print("\nCheck the results:")
    print("  - Master log: tail -50 /home/dora/RoboOs/Test/RoboOS/master/.logs/master_agent.log")
    print("  - Slaver log: tail -50 /home/dora/RoboOs/Test/RoboOS/slaver/.log/agent.log")
    print("\nExpected behavior:")
    print("  - All navigation tasks should call 'navigate_to_target'")
    print("  - Movement with parameters should call 'move'")
    print("  - 'Move from X to Y' should be treated as navigation")
