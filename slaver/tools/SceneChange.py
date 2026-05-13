"""
场景变化模拟模块 - 模拟真实场景中物体的随机增减

后台线程每 2 秒检测一次：
  random > 0.96  → 触发场景变化（约 5% 概率）
  只改变 kitchenTable 的 contains 列表：
    10% 概率：随机移除一个已有物体
    90% 概率：从候选列表中随机增加一个新物体

⚠️ 这是模拟模块，部署到真实机器人时注释掉即可。
"""

import json
import random
import sys
import threading
import time
from typing import Optional

POSSIBLE_NEW_OBJECTS = ["Strawberry", "Grape", "Watermelon", "Pineapple", "Mango"]
TARGET_LOCATION = "kitchenTable"
CHECK_INTERVAL = 2
TRIGGER_THRESHOLD = 0.97


class SceneChanger:
    """后台线程，定期随机修改 Redis 中 kitchenTable 的物体列表。"""

    def __init__(self, collaborator, interval: int = CHECK_INTERVAL):
        self.collaborator = collaborator
        self.interval = interval
        self._shutdown_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._initialized = False  # 等场景初始化后才开始

    def start(self):
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="scene_changer",
        )
        self._thread.start()
        print(
            f"[SceneChanger] Simulation started, interval={self.interval}s",
            file=sys.stderr,
        )

    def stop(self):
        self._shutdown_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        print("[SceneChanger] Stopped", file=sys.stderr)

    def _run_loop(self):
        while not self._shutdown_event.is_set():
            try:
                # 等待场景初始化（Redis 中存在 kitchenTable 且有 contains 字段）
                if not self._initialized:
                    scene_data = self.collaborator.read_environment(TARGET_LOCATION)
                    if scene_data:
                        if isinstance(scene_data, str):
                            scene_data = json.loads(scene_data)
                        if isinstance(scene_data.get("contains"), list):
                            self._initialized = True
                    self._shutdown_event.wait(self.interval)
                    continue

                if random.random() > TRIGGER_THRESHOLD:
                    self._apply_random_change()
            except Exception as e:
                print(f"[SceneChanger] Error: {e}", file=sys.stderr)

            self._shutdown_event.wait(self.interval)

    def _apply_random_change(self):
        scene_data = self.collaborator.read_environment(TARGET_LOCATION)
        if not scene_data:
            return

        if isinstance(scene_data, str):
            scene_data = json.loads(scene_data)

        contains = scene_data.get("contains", [])
        if not isinstance(contains, list):
            return

        if random.random() < 0.1:
            # 10%: 移除一个随机物体（排除原始物体，只移除模拟新增的）
            simulated_objects = [o for o in contains if o in POSSIBLE_NEW_OBJECTS]
            if not simulated_objects:
                return
            obj = random.choice(simulated_objects)
            contains.remove(obj)
            action = "remove"
        else:
            # 90%: 增加一个随机新物体（不重复添加）
            obj = random.choice(POSSIBLE_NEW_OBJECTS)
            if obj in contains:
                return
            contains.append(obj)
            action = "add"

        scene_data["contains"] = contains
        self.collaborator.record_environment(
            TARGET_LOCATION, json.dumps(scene_data)
        )

        print(
            f"[SceneChanger] {'移除' if action == 'remove' else '新增'} "
            f"{obj} @ {TARGET_LOCATION} | 当前物体: {contains}",
            file=sys.stderr,
        )
