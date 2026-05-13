import asyncio
import json
import logging
import os
import threading
import uuid
from typing import Dict, List, Optional
import re

import yaml
from dotenv import load_dotenv
from agents.planner import GlobalTaskPlanner
from agent.collaboration import Collaborator

# Load .env from project root
_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
load_dotenv(os.path.join(_project_root, '.env'))

# Bypass system proxy for API calls
os.environ['NO_PROXY'] = '*'


class TaskQueue:
    """Master 维护的可变任务队列，支持执行过程中增量插入新子任务。"""

    def __init__(self, subtask_list: list):
        self.tasks = []
        self._next_order = 0
        for task in subtask_list:
            order = int(task.get("subtask_order", 0))
            self._next_order = max(self._next_order, order)
            self.tasks.append({
                "order": order,
                "robot_name": task.get("robot_name"),
                "subtask": task.get("subtask"),
                "done": False,
            })

    def get_next_undone(self) -> Optional[Dict]:
        for task in self.tasks:
            if not task["done"]:
                return task
        return None

    def mark_done(self, task: Dict):
        task["done"] = True

    def append_tasks(self, new_subtasks: list):
        for task in new_subtasks:
            self._next_order += 1
            self.tasks.append({
                "order": self._next_order,
                "robot_name": task.get("robot_name"),
                "subtask": task.get("subtask"),
                "done": False,
            })

    def remove_pending_tasks(self, subtask_descriptions: list):
        """移除未完成的子任务（按描述匹配）。"""
        self.tasks = [
            t for t in self.tasks
            if t["done"] or not any(
                desc in t["subtask"] for desc in subtask_descriptions
            )
        ]

    def get_completed(self) -> List[Dict]:
        return [t for t in self.tasks if t["done"]]

    def get_remaining(self) -> List[Dict]:
        return [t for t in self.tasks if not t["done"]]

    def all_done(self) -> bool:
        return all(t["done"] for t in self.tasks)


class GlobalAgent:
    def __init__(self, config_path="config.yaml"):
        """Initialize GlobalAgent"""
        self._init_config(config_path)
        self._init_logger(self.config["logger"])
        self.collaborator = Collaborator.from_config(self.config["collaborator"])
        self.planner = GlobalTaskPlanner(self.config)
        self.listening_robots = set()
        self.conversation_history = []
        self.max_history = 5
        self.terminated_tasks = set()
        self.pending_scene_changes = []
        self._scene_changes_lock = threading.Lock()
        self.current_task_queue: Optional[TaskQueue] = None
        self.current_task_id: Optional[str] = None
        self.current_task_desc: Optional[str] = None

        self.logger.info(f"Configuration loaded from {config_path} ...")
        self.logger.info(f"Master Configuration:\n{self.config}")

        self._init_scene(self.config["profile"])
        self._start_listener()
        self._start_scene_change_listener()

    def _init_logger(self, logger_config):
        self.logger = logging.getLogger(logger_config["master_logger_name"])
        logger_file = logger_config["master_logger_file"]
        os.makedirs(os.path.dirname(logger_file), exist_ok=True)
        file_handler = logging.FileHandler(logger_file)

        if logger_config["master_logger_level"] == "DEBUG":
            self.logger.setLevel(logging.DEBUG)
            file_handler.setLevel(logging.DEBUG)
        elif logger_config["master_logger_level"] == "INFO":
            self.logger.setLevel(logging.INFO)
            file_handler.setLevel(logging.INFO)
        elif logger_config["master_logger_level"] == "WARNING":
            self.logger.setLevel(logging.WARNING)
            file_handler.setLevel(logging.WARNING)
        elif logger_config["master_logger_level"] == "ERROR":
            self.logger.setLevel(logging.ERROR)
            file_handler.setLevel(logging.ERROR)

        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

    def _init_config(self, config_path="config.yaml"):
        with open(config_path, "r", encoding="utf-8") as f:
            raw = f.read()
        raw = re.sub(r'\$\{(\w+)\}', lambda m: os.environ.get(m.group(1), m.group(0)), raw)
        self.config = yaml.safe_load(raw)

    def _init_scene(self, scene_config):
        path = scene_config["path"]
        if not os.path.exists(path):
            self.logger.error(f"Scene config file {path} does not exist.")
            raise FileNotFoundError(f"Scene config file {path} not found.")
        with open(path, "r", encoding="utf-8") as f:
            self.scene = yaml.safe_load(f)

        scenes = self.scene.get("scene", [])
        for scene_info in scenes:
            scene_name = scene_info.pop("name", None)
            if scene_name:
                self.collaborator.record_environment(scene_name, json.dumps(scene_info))
            else:
                print("Warning: Missing 'name' in scene_info:", scene_info)

    def _handle_register(self, robot_name: Dict) -> None:
        robot_info = self.collaborator.read_agent_info(robot_name)
        if robot_name in self.listening_robots:
            return

        self.logger.info(
            f"AGENT_REGISTRATION: {robot_name} \n {json.dumps(robot_info)}"
        )

        channel_r2b = f"{robot_name}_to_FQPlanner"
        threading.Thread(
            target=lambda: self.collaborator.listen(channel_r2b, self._handle_result),
            daemon=True,
            name=channel_r2b,
        ).start()
        self.listening_robots.add(robot_name)

        self.logger.info(
            f"FQPlanner has listened to [{robot_name}] by channel [{channel_r2b}]"
        )

    def _handle_result(self, data: str):
        data = json.loads(data)

        robot_name = data.get("robot_name")
        subtask_handle = data.get("subtask_handle")
        subtask_result = data.get("subtask_result")
        terminated = data.get("terminated", False)
        task_id = data.get("task_id")

        if robot_name and subtask_handle and subtask_result:
            self.logger.info(
                f"================ Received result from {robot_name} ================"
            )
            self.logger.info(f"Subtask: {subtask_handle}\nResult: {subtask_result}")
            if terminated:
                self.logger.warning(f"[TERMINATE] Task {task_id} terminated by judge")
                if task_id:
                    self.terminated_tasks.add(task_id)
            self.logger.info(
                "===================================================================="
            )
            self.collaborator.update_agent_busy(robot_name, False)

        else:
            self.logger.warning("[WARNING] Received incomplete result data")
            self.logger.info(
                f"================ Received result from {robot_name} ================"
            )
            self.logger.info(f"Subtask: {subtask_handle}\nResult: {subtask_result}")
            self.logger.info(
                "===================================================================="
            )

    def _extract_json(self, input_string):
        if not isinstance(input_string, str):
            self.logger.warning(f"[_extract_json] received non-string input: {type(input_string)}")
            return None

        json_match = re.search(r"```json\n(.*?)\n```", input_string, flags=re.DOTALL)
        if json_match:
            json_str = json_match.group(1).strip()
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                self.logger.warning(f"Failed to parse JSON from markdown: {e}")
                return None

        try:
            return json.loads(input_string)
        except json.JSONDecodeError:
            try:
                brace_start = input_string.find("{")
                brace_end = input_string.rfind("}") + 1
                if brace_start != -1 and brace_end != 0:
                    json_str = input_string[brace_start:brace_end]
                    return json.loads(json_str)
            except json.JSONDecodeError as e:
                self.logger.warning(f"Could not parse JSON from string content: {e}")
        return None

    def _start_listener(self):
        threading.Thread(
            target=lambda: self.collaborator.listen(
                "AGENT_REGISTRATION", self._handle_register
            ),
            daemon=True,
        ).start()
        self.logger.info("Started listening for robot registrations...")

    def _start_scene_change_listener(self):
        """监听场景变化频道，实时接收 SceneDetector 推送的变化。"""
        threading.Thread(
            target=lambda: self.collaborator.listen(
                "scene_changes", self._handle_scene_change
            ),
            daemon=True,
            name="scene_changes_listener",
        ).start()
        self.logger.info("Started listening for scene changes...")

    def _handle_scene_change(self, data: str):
        """处理实时推送的场景变化，累积到 pending_scene_changes。"""
        try:
            change = json.loads(data)
            with self._scene_changes_lock:
                self.pending_scene_changes.append(change)
            self.logger.info(f"[SceneChanges] Real-time: {change}")
        except (json.JSONDecodeError, TypeError) as e:
            self.logger.warning(f"[SceneChanges] Failed to parse: {e}")

    def reasoning_and_subtasks_is_right(self, reasoning_and_subtasks: dict) -> bool:
        if not isinstance(reasoning_and_subtasks, dict):
            return False

        if "subtask_list" not in reasoning_and_subtasks:
            return False

        try:
            worker_list = {
                subtask["robot_name"]
                for subtask in reasoning_and_subtasks["subtask_list"]
                if isinstance(subtask, dict) and "robot_name" in subtask
            }

            robots_list = set(self.collaborator.read_all_agents_name())
            return worker_list.issubset(robots_list)

        except (TypeError, KeyError):
            return False

    def publish_global_task(self, task: str, refresh: bool, task_id: str) -> Dict:
        """Publish a global task to all Agents"""
        self.logger.info(f"Publishing global task: {task}")

        response = self.planner.forward(task, self.conversation_history)
        self.logger.info(f"Raw response from planner: {response}")
        reasoning_and_subtasks = self._extract_json(response)

        attempt = 0
        while (not self.reasoning_and_subtasks_is_right(reasoning_and_subtasks)) and (
            attempt < self.config["model"]["model_retry_planning"]
        ):
            self.logger.warning(
                f"Attempt {attempt + 1} to extract JSON failed. Retrying..."
            )
            response = self.planner.forward(task)
            reasoning_and_subtasks = self._extract_json(response)
            attempt += 1

        self.logger.info(f"Received reasoning and subtasks:\n{reasoning_and_subtasks}")
        subtask_list = reasoning_and_subtasks.get("subtask_list", [])

        def _ensure_str(v):
            if v is None:
                return ""
            if isinstance(v, list):
                return "".join(p.get("text", "") if isinstance(p, dict) else getattr(p, "text", "") for p in v)
            return v if isinstance(v, str) else str(v)

        self.conversation_history.append({"role": "user", "content": _ensure_str(task)})
        self.conversation_history.append({"role": "assistant", "content": _ensure_str(response)})
        if len(self.conversation_history) > self.max_history * 2:
            self.conversation_history = self.conversation_history[-self.max_history * 2:]

        task_queue = TaskQueue(subtask_list)

        task_id = task_id or str(uuid.uuid4()).replace("-", "")
        self.current_task_queue = task_queue
        self.current_task_id = task_id
        self.current_task_desc = task

        threading.Thread(
            target=asyncio.run,
            args=(self._dispath_subtasks_async(task, task_id, task_queue, refresh),),
            daemon=True,
        ).start()

        return reasoning_and_subtasks

    async def _dispath_subtasks_async(
        self,
        task: str,
        task_id: str,
        task_queue: TaskQueue,
        refresh: bool
    ):
        """逐个发送子任务，每个完成后检查场景变化并增量规划。"""
        while not task_queue.all_done():
            if task_id in self.terminated_tasks:
                self.logger.warning(f"[TERMINATE] Stopping task {task_id}")
                self.terminated_tasks.discard(task_id)
                break

            current = task_queue.get_next_undone()
            if not current:
                break

            robot_name = current["robot_name"]
            subtask_data = {
                "task_id": task_id,
                "task": current["subtask"],
                "order": "true",
            }
            if refresh:
                self.collaborator.clear_agent_status(robot_name)

            self.logger.info(f"Sending: {current['subtask']}")
            self.collaborator.send(
                f"fqplanner_to_{robot_name}", json.dumps(subtask_data)
            )
            self.collaborator.update_agent_busy(robot_name, True)
            self.collaborator.wait_agents_free([robot_name])

            task_queue.mark_done(current)

            if task_id in self.terminated_tasks:
                self.logger.warning(f"[TERMINATE] Task {task_id} terminated, stopping")
                self.terminated_tasks.discard(task_id)
                break

            # 每个子任务完成后，检查是否有场景变化需要增量规划
            with self._scene_changes_lock:
                changes = self.pending_scene_changes[:]
                self.pending_scene_changes.clear()

            if changes:
                new_tasks, remove_tasks = self._incremental_replan(task, task_queue, changes)
                if remove_tasks:
                    task_queue.remove_pending_tasks(remove_tasks)
                    self.logger.info(
                        f"[IncrementalReplan] Removed tasks: {remove_tasks}"
                    )
                if new_tasks:
                    task_queue.append_tasks(new_tasks)
                    self.logger.info(
                        f"[IncrementalReplan] Added {len(new_tasks)} new tasks: "
                        f"{[t['subtask'] for t in new_tasks]}"
                    )

        self.logger.info(f"Task_id ({task_id}) [{task}] all done.")

    def get_task_status(self) -> Dict:
        """返回当前任务的执行状态，供前端查询。"""
        if not self.current_task_queue:
            return {"active": False}

        q = self.current_task_queue
        tasks = []
        for t in q.tasks:
            tasks.append({
                "order": t["order"],
                "robot_name": t["robot_name"],
                "subtask": t["subtask"],
                "done": t["done"],
            })

        return {
            "active": True,
            "task_id": self.current_task_id,
            "task": self.current_task_desc,
            "all_done": q.all_done(),
            "total": len(tasks),
            "completed": len([t for t in tasks if t["done"]]),
            "subtask_list": tasks,
        }

    def _incremental_replan(
        self, original_task: str, task_queue: TaskQueue, changes: list
    ) -> tuple:
        """增量规划：返回需要新增和移除的子任务。"""
        changes_summary = self._summarize_changes(changes)

        # 读取当前场景状态
        all_env = self.collaborator.read_environment(None)
        scene_str = "无"
        if all_env:
            parts = []
            for key, val in all_env.items():
                if key == "robot":
                    continue
                if isinstance(val, str):
                    val = json.loads(val)
                contains = val.get("contains")
                if isinstance(contains, list):
                    desc = val.get("description", key)
                    parts.append(f"  {key}（{desc}）: {', '.join(contains) if contains else '空'}")
            scene_str = "\n".join(parts) if parts else "无"

        completed = task_queue.get_completed()
        remaining = task_queue.get_remaining()

        completed_str = "\n".join(f"  - {t['subtask']} (done)" for t in completed) or "  无"
        remaining_str = "\n".join(f"  - {t['subtask']}" for t in remaining) or "  无"

        replan_prompt = f"""原始任务：{original_task}

当前场景状态：
{scene_str}

已完成的子任务：
{completed_str}

剩余的子任务：
{remaining_str}

场景变化：{changes_summary}

请根据当前场景状态和场景变化，判断需要调整的子任务：
- 如果有新物体出现需要处理，在 new_subtasks 中添加
- 如果某个剩余子任务的目标已不存在（如物体从场景中消失），在 remove_subtasks 中列出对应的子任务描述
- 如果场景变化不需要额外操作（如机器人自己抓取导致的移除），两个列表都为空

输出格式：
{{
    "reasoning": "判断理由",
    "new_subtasks": [
        {{"robot_name": "FQrobot", "subtask": "xxx"}}
    ],
    "remove_subtasks": [
        "要移除的子任务描述"
    ]
}}
不需要操作时，两个列表都为空列表。"""

        try:
            response = self.planner.forward(replan_prompt, self.conversation_history)
            self.logger.info(f"[IncrementalReplan] LLM response: {response}")

            result = self._extract_json(response)
            if result:
                new = result.get("new_subtasks") or []
                remove = result.get("remove_subtasks") or []
                return new, remove
        except Exception as e:
            self.logger.error(f"[IncrementalReplan] Error: {e}")

        return [], []

    def _summarize_changes(self, changes: list) -> str:
        """将场景变化列表格式化为自然语言摘要。"""
        summary_parts = []
        for change in changes:
            loc = change.get("location", "未知位置")
            added = change.get("added", [])
            removed = change.get("removed", [])
            parts = []
            if added:
                parts.append(f"新增了 {', '.join(added)}")
            if removed:
                parts.append(f"移除了 {', '.join(removed)}")
            if parts:
                summary_parts.append(f"{loc} 中" + "，".join(parts))
        return "；".join(summary_parts) if summary_parts else "无变化"
