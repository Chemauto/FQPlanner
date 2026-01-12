#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Simple test script to verify navigation functionality.
This bypasses the web UI and directly sends a task to the master.
"""

import requests
import time

def send_navigation_task():
    """Send a navigation task to the master server."""
    url = "http://localhost:5000/publish_task"

    # Note: task must be a list according to the API
    task_data = {
        "task": ["先去卧室"],
        "task_id": f"test_{int(time.time())}",
        "refresh": False
    }

    print(f"Sending task: {task_data}")

    try:
        response = requests.post(url, json=task_data, timeout=30)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            print(f"Response: {response.json()}")
            return response.json()
        else:
            print(f"Error Response: {response.text}")
            return None
    except Exception as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    print("=== Simple Navigation Test ===")
    result = send_navigation_task()
    print("\n=== Test Complete ===")
    print("\nNow check the logs:")
    print("  - Slaver: tail -f /home/dora/RoboOs/Test/RoboOS/slaver/.log/agent.log")
    print("  - Master: tail -f /home/dora/RoboOs/Test/RoboOS/master/.logs/master_agent.log")
    print("\nAlso check your terminal where you ran 'python slaver/run.py'")
    print("You should see [SKILL DEBUG] messages on stderr")
