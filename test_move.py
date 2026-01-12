#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script for the move function.
This tests the new move skill with various parameters.
"""

import requests
import time

def send_task(task_description, task_list=None):
    """Send a task to the master server."""
    url = "http://localhost:5000/publish_task"

    # If task_list is provided, use it; otherwise use the single task
    if task_list is None:
        task_list = [task_description]

    task_data = {
        "task": task_list,
        "task_id": f"test_{int(time.time())}",
        "refresh": False
    }

    print(f"\n{'='*60}")
    print(f"Sending task: {task_description}")
    print(f"{'='*60}")

    try:
        response = requests.post(url, json=task_data, timeout=60)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"Response: {result}")
            return result
        else:
            print(f"Error Response: {response.text}")
            return None
    except Exception as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    print("=== Robot Movement Test Suite ===")

    # Test 1: Simple forward movement
    print("\n### Test 1: Move Forward ###")
    send_task("Move forward at 1 m/s for 2 seconds")

    time.sleep(3)

    # Test 2: Move left
    print("\n### Test 2: Move Left ###")
    send_task("Move left at 0.5 m/s for 3 seconds")

    time.sleep(3)

    # Test 3: Move backward
    print("\n### Test 3: Move Backward ###")
    send_task("Move backward at 0.8 m/s for 1.5 seconds")

    time.sleep(3)

    # Test 4: Combined task - navigate then move
    print("\n### Test 4: Navigate then Move ###")
    send_task([
        "Navigate to bedroom",
        "Move forward at 1 m/s for 2 seconds"
    ])

    time.sleep(5)

    # Test 5: Custom angle movement
    print("\n### Test 5: Move at 45 degrees ###")
    send_task("Move at 45 degrees at 0.6 m/s for 2.5 seconds")

    print("\n=== All Tests Complete ===")
    print("\nCheck the logs:")
    print("  - Slaver terminal: Should show [move] debug messages")
    print("  - Slaver log: tail -f /home/dora/RoboOs/Test/RoboOS/slaver/.log/agent.log")
    print("  - Master log: tail -f /home/dora/RoboOs/Test/RoboOS/master/.logs/master_agent.log")
