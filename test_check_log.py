#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Quick test to verify logging is working.
"""

import requests
import time
import subprocess
from datetime import datetime

def check_log_file():
    """Check the last modification time and size of the log file."""
    result = subprocess.run(
        ["stat", "-c", "%Y %s", "/home/dora/RoboOs/Test/RoboOS/slaver/.log/agent.log"],
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        modify_time, size = result.stdout.strip().split()
        print(f"Log file size: {int(size) / 1024:.2f} KB")
        print(f"Last modified: {datetime.fromtimestamp(int(modify_time))}")
        return int(modify_time)
    return None

def send_task(task):
    """Send a task to the master server."""
    url = "http://localhost:5000/publish_task"
    task_data = {
        "task": [task],
        "task_id": f"log_test_{int(time.time())}",
        "refresh": False
    }

    print(f"\nSending task: {task}")
    try:
        response = requests.post(url, json=task_data, timeout=30)
        if response.status_code == 200:
            print(f"✓ Task sent successfully")
            return True
        else:
            print(f"✗ Error: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def wait_for_log_update(start_time, timeout=10):
    """Wait for the log file to be updated."""
    print(f"Waiting for log file to update...")
    for i in range(timeout):
        time.sleep(1)
        current_time = check_log_file()
        if current_time and current_time > start_time:
            print(f"✓ Log file updated at {datetime.fromtimestamp(current_time)}")
            return True
        print(f"  Waiting... ({i+1}/{timeout})")
    print("✗ Log file was not updated")
    return False

if __name__ == "__main__":
    print("=" * 60)
    print("Log File Verification Test")
    print("=" * 60)

    # Check initial state
    print("\n1. Checking initial log file state:")
    start_time = check_log_file()

    # Send a test task
    print("\n2. Sending a test task:")
    if send_task("Navigate to bedroom"):
        # Wait for log update
        print("\n3. Checking for log updates:")
        if wait_for_log_update(start_time):
            print("\n4. Showing latest log entries:")
            print("-" * 60)
            result = subprocess.run(
                ["tail", "-10", "/home/dora/RoboOs/Test/RoboOS/slaver/.log/agent.log"],
                capture_output=True,
                text=True
            )
            print(result.stdout)
            print("-" * 60)
            print("\n✓ Test PASSED: Logging is working!")
        else:
            print("\n✗ Test FAILED: Log file was not updated")
            print("\nPossible reasons:")
            print("  - Slaver service is not running")
            print("  - Slaver service needs to be restarted to load new code")
            print("  - Log file path is incorrect")
    else:
        print("\n✗ Test FAILED: Could not send task")
        print("  Make sure Master service is running on port 5000")
