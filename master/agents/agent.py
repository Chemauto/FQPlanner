import asyncio
import json
import logging
import os
import threading
from datetime import datetime
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

    def mark_done(self, task: Dict, status: str = "success"):
        task["done"] = True
        task["status"] = status  # "success" | "failure" | "exception" | "timeout"

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
        self._last_subtask_status = None  # Slaver 返回的子任务状态
        self._last_subtask_result = None  # Slaver 返回的子任务结果（含 VLM 描述）
        self._memory_dir = os.path.join(os.path.dirname(__file__), '..', 'memory')
        self._experience_file = os.path.join(self._memory_dir, 'experiences.md')
        self._skills_dir = os.path.join(self._memory_dir, 'skills')
        self._exploration_rate = self.config.get('experience', {}).get('exploration_rate', 0.8)
        self._pending_failure = None   # 等待人工录入的失败信息
        self._pending_success = None   # 等待人工决定是否录入的成功信息
        self._dispatch_token = 0       # 每次新任务自增，旧 dispatch thread 检测到变化后退出

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
        status = data.get("status")  # success/failure/none/exception/timeout

        if robot_name and subtask_handle and subtask_result:
            self.logger.info(
                f"================ Received result from {robot_name} ================"
            )
            self.logger.info(f"Subtask: {subtask_handle}\nResult: {subtask_result}\nStatus: {status}")
            if terminated:
                self.logger.warning(f"[TERMINATE] Task {task_id} terminated by judge")
                if task_id:
                    self.terminated_tasks.add(task_id)
            # 存储最后一次子任务状态和结果，供 _dispath_subtasks_async 使用
            self._last_subtask_status = status
            self._last_subtask_result = subtask_result
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
            # 即使结果不完整也要释放 busy，否则 wait_agents_free 永远不返回
            if robot_name:
                self.collaborator.update_agent_busy(robot_name, False)

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

    def _get_skill_name(self, task_desc: str) -> str:
        if isinstance(task_desc, list):
            task_desc = " ".join(str(x) for x in task_desc)
        elif not isinstance(task_desc, str):
            task_desc = str(task_desc)
        task_lower = (task_desc or "").lower()
        if any(w in task_lower for w in ['抓', 'grasp', '拿', '捡', '取']):
            return 'grasp'
        elif any(w in task_lower for w in ['放', 'place', '放置', '放到', '放在']):
            return 'place'
        elif any(w in task_lower for w in ['导航', 'navigate', '去', '移动到']):
            return 'navigate'
        else:
            return 'multi_step'

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

        # 每条新顶层任务独立规划，清空历史避免旧任务计划干扰 LLM
        self.conversation_history = []

        experiences = self._load_experiences(task=task)
        response = self.planner.forward(task, self.conversation_history, experiences)
        self.logger.info(f"Raw response from planner: {response}")
        reasoning_and_subtasks = self._extract_json(response)

        attempt = 0
        while (not self.reasoning_and_subtasks_is_right(reasoning_and_subtasks)) and (
            attempt < self.config["model"]["model_retry_planning"]
        ):
            self.logger.warning(
                f"Attempt {attempt + 1} to extract JSON failed. Retrying..."
            )
            response = self.planner.forward(task, history=None, experiences=experiences)
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
        self.current_task_desc = task if isinstance(task, str) else (task[0] if task else "")

        # 使旧 dispatch thread 失效，并重置共享状态
        self._dispatch_token += 1
        my_token = self._dispatch_token
        self._pending_failure = None
        self._pending_success = None
        for agent_name in self.collaborator.read_all_agents_name():
            self.collaborator.update_agent_busy(agent_name, False)

        threading.Thread(
            target=asyncio.run,
            args=(self._dispath_subtasks_async(task, task_id, task_queue, refresh, my_token),),
            daemon=True,
        ).start()

        return reasoning_and_subtasks

    async def _dispath_subtasks_async(
        self,
        task: str,
        task_id: str,
        task_queue: TaskQueue,
        refresh: bool,
        dispatch_token: int = 0,
    ):
        """逐个发送子任务，每个完成后检查场景变化并增量规划。"""
        robot_name = None
        task_had_failure = False  # 任一非拍照子任务失败则置 True

        def _superseded():
            """检查是否被新任务取代。"""
            return self._dispatch_token != dispatch_token

        max_verify_retries = 3
        final_verify_abnormal = False
        for _verify_round in range(max_verify_retries):
            if _verify_round > 0:
                self.logger.info(f"[Camera] 最终验证重规划第 {_verify_round} 轮，重新执行修正子任务...")

            while not task_queue.all_done():
                if _superseded():
                    self.logger.info(f"[Dispatch] Token 已过期，退出旧任务 dispatch")
                    return
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

                # 重置状态
                self._last_subtask_status = None
                self._last_subtask_result = None

                self.logger.info(f"Sending: {current['subtask']}")
                # 先标 busy 再发消息，防止机器人响应过快导致 busy flag 竞争
                self.collaborator.update_agent_busy(robot_name, True)
                self.collaborator.send(
                    f"fqplanner_to_{robot_name}", json.dumps(subtask_data)
                )
                self.collaborator.wait_agents_free([robot_name])

                if _superseded():
                    self.logger.info(f"[Dispatch] 等待期间被新任务取代，退出")
                    return

                subtask_status = self._last_subtask_status or "success"
                task_queue.mark_done(current, status=subtask_status)

                # 子任务失败/异常时，拍照诊断（但拍照任务本身失败不再触发拍照，避免死循环）
                is_camera_task = "拍照" in current["subtask"]
                if self._last_subtask_status in ("failure", "exception", "timeout") and not is_camera_task:
                    task_had_failure = True
                    self.logger.info(f"[Camera] 子任务状态={self._last_subtask_status}，拍照诊断...")
                    if self.config.get('camera', {}).get('enabled', True):
                        self._send_camera_task(
                            robot_name, task_id,
                            f"拍照诊断：刚执行'{current['subtask']}'失败（{self._last_subtask_status}），检查当前场景状态"
                        )

                    # VLM 发现异常时，让 Master LLM 决定如何调整
                    if self._last_subtask_result and "abnormal" in self._last_subtask_result:
                        self.logger.info(f"[Camera] VLM 发现异常，触发重规划...")
                        vlm_feedback = self._last_subtask_result
                        new_tasks, remove_tasks = self._incremental_replan(
                            task, task_queue, [], vlm_feedback=vlm_feedback
                        )
                        if remove_tasks:
                            task_queue.remove_pending_tasks(remove_tasks)
                            self.logger.info(f"[Camera] 移除任务: {remove_tasks}")
                        if new_tasks:
                            task_queue.append_tasks(new_tasks)
                            self.logger.info(f"[Camera] 新增任务: {[t['subtask'] for t in new_tasks]}")

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

            # 所有子任务完成后，拍照验证最终场景（仅当 dispatch 未被取代时）
            if robot_name and task_queue.all_done() and not _superseded():
                self.logger.info("[Camera] 所有子任务完成，拍照验证最终场景...")
                camera_ok = False
                if self.config.get('camera', {}).get('enabled', True):
                    self._send_camera_task(
                        robot_name, task_id,
                        f"拍照验证：原始任务'{task}'的所有子任务已完成，检查最终场景是否符合预期"
                    )
                    camera_ok = self._last_subtask_result is not None

                if not camera_ok:
                    self.logger.warning("[Camera] 最终验证拍照失败，无法确认场景状态")
                    task_had_failure = True
                elif "abnormal" in self._last_subtask_result:
                    self.logger.warning(f"[Camera] 最终验证发现异常: {self._last_subtask_result}")
                    vlm_feedback = self._last_subtask_result
                    new_tasks, remove_tasks = self._incremental_replan(
                        task, task_queue, [], vlm_feedback=vlm_feedback
                    )
                    if remove_tasks:
                        task_queue.remove_pending_tasks(remove_tasks)
                        self.logger.info(f"[Camera] 最终验证重规划-移除任务: {remove_tasks}")
                    if new_tasks:
                        task_queue.append_tasks(new_tasks)
                        self.logger.info(f"[Camera] 最终验证重规划-新增任务: {[t['subtask'] for t in new_tasks]}")
                        continue
                    # abnormal 但 LLM 未生成修正任务，标记失败
                    self.logger.warning("[Camera] 最终验证异常但未生成修正任务，标记整体失败")
                    task_had_failure = True
                    final_verify_abnormal = True
                else:
                    self.logger.info("[Camera] 最终验证通过，场景正常")
            # 验证通过或无条件重试，退出外层循环
            break
        else:
            # for 循环自然结束（达到最大重试次数）
            self.logger.warning(f"[Camera] 最终验证重规划已达到最大重试次数({max_verify_retries})，场景仍异常")
            task_had_failure = True
            final_verify_abnormal = True

        self.logger.info(f"Task_id ({task_id}) [{task}] all done.")

        if not _superseded():
            all_tasks = task_queue.tasks
            task_desc = task if isinstance(task, str) else str(task)
            completed_cnt = len(task_queue.get_completed())
            total_cnt = len(all_tasks)

            if not task_queue.all_done() or task_had_failure:
                # 整体失败
                self._pending_failure = {
                    "task_id": task_id,
                    "task_desc": task_desc,
                    "completed": completed_cnt,
                    "total": total_cnt,
                }
                self.logger.info(f"[Experience] Task failed, waiting for human input")
            else:
                # 整体成功，询问用户是否录入正向经验
                self._pending_success = {
                    "task_id": task_id,
                    "task_desc": task_desc,
                    "completed": completed_cnt,
                    "total": total_cnt,
                }
                self.logger.info(f"[Experience] Task succeeded, asking user for optional experience")

    def _send_camera_task(self, robot_name: str, task_id: str, description: str):
        """发送拍照子任务并等待完成。"""
        subtask_data = {
            "task_id": task_id,
            "task": description,
            "order": "true",
        }
        self._last_subtask_status = None
        self._last_subtask_result = None
        self.collaborator.update_agent_busy(robot_name, True)
        self.collaborator.send(
            f"fqplanner_to_{robot_name}", json.dumps(subtask_data)
        )
        self.collaborator.wait_agents_free([robot_name])
        self.logger.info(f"[Camera] 拍照完成，状态: {self._last_subtask_status}")

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
                "status": t.get("status"),  # None | "success" | "failure" | "exception" | "timeout"
            })

        failed = any(
            t["done"] and t.get("status") in ("failure", "exception", "timeout")
            for t in tasks
        )
        return {
            "active": True,
            "task_id": self.current_task_id,
            "task": self.current_task_desc,
            "all_done": q.all_done(),
            "failed": failed,
            "total": len(tasks),
            "completed": len([t for t in tasks if t["done"]]),
            "subtask_list": tasks,
        }

    def _incremental_replan(
        self, original_task: str, task_queue: TaskQueue, changes: list, vlm_feedback: str = None
    ) -> tuple:
        """增量规划：返回需要新增和移除的子任务。
        vlm_feedback: VLM 拍照诊断的反馈（可选），包含场景异常描述。
        """
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
{f"VLM 视觉反馈：{vlm_feedback}" if vlm_feedback else ""}

请根据当前场景状态和场景变化，判断需要调整的子任务：
- 如果有新物体出现需要处理，在 new_subtasks 中添加
- 如果某个剩余子任务的目标已不存在（如物体从场景中消失），在 remove_subtasks 中列出对应的子任务描述
- 如果场景变化不需要额外操作（如机器人自己抓取导致的移除），两个列表都为空
- 如果 VLM 视觉反馈显示场景异常（如物体掉落、位置不对），在 new_subtasks 中添加修正子任务

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

    def _load_experiences(self, task: str = "") -> str:
        os.makedirs(self._skills_dir, exist_ok=True)
        skill_name = self._get_skill_name(task or self.current_task_desc or "")

        parts = []
        skill_file = os.path.join(self._skills_dir, f'{skill_name}.md')
        if os.path.exists(skill_file):
            with open(skill_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            if content:
                parts.append(f"### {skill_name} 专项经验\n{content}")

        if skill_name != 'multi_step':
            multi_file = os.path.join(self._skills_dir, 'multi_step.md')
            if os.path.exists(multi_file):
                with open(multi_file, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                if content:
                    parts.append(f"### 复合任务经验\n{content}")

        if not parts:
            return ""

        exploration_hint = ""
        if self._exploration_rate > 0:
            explore_pct = int(self._exploration_rate * 100)
            refer_pct = 100 - explore_pct
            exploration_hint = f"\n> 参考策略：{refer_pct}% 借鉴以下经验，{explore_pct}% 自由探索新方案。"

        return f"\n\n## 过往经验（请参考）：{exploration_hint}\n" + "\n\n".join(parts)

    def classify_and_save_failure_experience(self, raw_input: str) -> dict:
        """LLM 将人工输入的失败经验归类到对应 skill 文件的避免规则中。"""
        os.makedirs(self._skills_dir, exist_ok=True)
        task_desc = (self._pending_failure or {}).get('task_desc', self.current_task_desc or '未知任务')
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        from agents.prompts import EXPERIENCE_CLASSIFY
        prompt = EXPERIENCE_CLASSIFY.format(task_desc=task_desc, raw_input=raw_input)
        try:
            response = self.planner.generate(prompt)
            result = self._extract_json(response)
            if not result:
                raise ValueError("LLM returned invalid JSON")
            skill = result.get('skill', 'multi_step')
            rule = result.get('rule', raw_input)
            if skill not in ('navigate', 'grasp', 'place', 'multi_step'):
                skill = 'multi_step'
        except Exception as e:
            self.logger.warning(f"[Experience] LLM classification failed: {e}")
            skill = self._get_skill_name(task_desc)
            rule = raw_input

        skill_file = os.path.join(self._skills_dir, f'{skill}.md')
        entry = f"\n### {date_str}\n- 任务：{task_desc}\n- 规则：{rule}\n"

        if os.path.exists(skill_file):
            with open(skill_file, 'r', encoding='utf-8') as f:
                content = f.read()
        else:
            content = f"# {skill} Skill 经验库\n\n## 避免规则\n"

        if '## 避免规则' not in content:
            content += '\n## 避免规则\n'
        pos = content.find('## 避免规则') + len('## 避免规则')
        content = content[:pos] + entry + content[pos:]

        with open(skill_file, 'w', encoding='utf-8') as f:
            f.write(content)

        self._pending_failure = None
        self.logger.info(f"[Experience] Saved failure rule to {skill}.md: {rule}")
        return {"success": True, "skill": skill, "rule": rule}

    def classify_and_save_success_experience(self, raw_input: str) -> dict:
        """LLM 将人工输入的正向经验归类到对应 skill 文件的正向经验区块中。"""
        os.makedirs(self._skills_dir, exist_ok=True)
        task_desc = (self._pending_success or {}).get('task_desc', self.current_task_desc or '未知任务')
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        from agents.prompts import EXPERIENCE_CLASSIFY_SUCCESS
        prompt = EXPERIENCE_CLASSIFY_SUCCESS.format(task_desc=task_desc, raw_input=raw_input)
        try:
            response = self.planner.generate(prompt)
            result = self._extract_json(response)
            if not result:
                raise ValueError("LLM returned invalid JSON")
            skill = result.get('skill', 'multi_step')
            tip = result.get('tip', raw_input)
            if skill not in ('navigate', 'grasp', 'place', 'multi_step'):
                skill = 'multi_step'
        except Exception as e:
            self.logger.warning(f"[Experience] LLM classification failed: {e}")
            skill = self._get_skill_name(task_desc)
            tip = raw_input

        skill_file = os.path.join(self._skills_dir, f'{skill}.md')
        entry = f"\n### {date_str}\n- 任务：{task_desc}\n- 策略：{tip}\n"

        if os.path.exists(skill_file):
            with open(skill_file, 'r', encoding='utf-8') as f:
                content = f.read()
        else:
            content = f"# {skill} Skill 经验库\n\n## 正向经验\n\n## 避免规则\n"

        section = '## 正向经验'
        if section not in content:
            content = content.replace('## 避免规则', f'{section}\n\n## 避免规则')
        pos = content.find(section) + len(section)
        content = content[:pos] + entry + content[pos:]

        with open(skill_file, 'w', encoding='utf-8') as f:
            f.write(content)

        self._pending_success = None
        self.logger.info(f"[Experience] Saved success tip to {skill}.md: {tip}")
        return {"success": True, "skill": skill, "tip": tip}

    def save_experience(self, task_id: str = "", exp_type: str = None, note: str = ""):
        """保存经验到对应 skill 文件，note 是失败原因或成功备注"""
        os.makedirs(self._skills_dir, exist_ok=True)
        if exp_type is None:
            exp_type = task_id if task_id in ("positive", "negative") else "positive"

        task_desc = self.current_task_desc or "未知任务"
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        subtask_summary = "无子任务记录"
        if self.current_task_queue:
            lines = []
            for t in self.current_task_queue.tasks:
                status = "完成" if t["done"] else "未完成"
                lines.append(f"  - {t['subtask']}（{status}）")
            subtask_summary = "\n".join(lines)

        feedback_type = "正向（方案有效）" if exp_type == "positive" else "负向（方案有问题）"
        user_note_section = f"用户备注（失败原因）：{note}" if note else ""

        from agents.prompts import EXPERIENCE_GENERATION
        prompt = EXPERIENCE_GENERATION.format(
            task=task_desc,
            subtask_summary=subtask_summary,
            feedback_type=feedback_type,
            user_note_section=user_note_section,
        )

        try:
            response = self.planner.generate(prompt)
            experience_text = response.strip()
            if experience_text.startswith("```"):
                experience_text = re.sub(r"^```\w*\n?", "", experience_text)
                experience_text = experience_text.rstrip("`").strip()
            if not experience_text:
                experience_text = note or ("此方案有效，可复用" if exp_type == "positive" else "此方案有问题，需避免")
        except Exception as e:
            self.logger.warning(f"[Experience] LLM generation failed: {e}")
            experience_text = note or ("此方案有效，可复用" if exp_type == "positive" else "此方案有问题，需避免")

        # 写入对应 skill 文件
        skill_name = self._get_skill_name(task_desc)
        skill_file = os.path.join(self._skills_dir, f'{skill_name}.md')

        if exp_type == "positive":
            section = "## 正向经验"
            entry = f"\n### {date_str} {task_desc}\n- 任务：{task_desc}\n- 教训：{experience_text}\n"
        else:
            section = "## 避免规则"
            entry = f"\n### {date_str} {task_desc}\n- 任务：{task_desc}\n- 规则：{experience_text}\n"

        if os.path.exists(skill_file):
            with open(skill_file, 'r', encoding='utf-8') as f:
                content = f.read()
        else:
            content = f"# {skill_name} Skill 经验库\n\n## 正向经验\n\n## 避免规则\n"

        section_pos = content.find(section)
        if section_pos == -1:
            content += f"\n{section}\n{entry}"
        else:
            insert_pos = section_pos + len(section)
            content = content[:insert_pos] + "\n" + entry + content[insert_pos:]

        with open(skill_file, 'w', encoding='utf-8') as f:
            f.write(content)

        self.logger.info(f"[Experience] Saved {exp_type} to {skill_name}.md: {experience_text}")
        return {"success": True, "skill": skill_name, "message": f"经验已保存到 {skill_name}.md", "experience": experience_text}

    def get_experiences(self) -> str:
        """返回经验库全文（供前端展示）。"""
        parts = []
        if os.path.exists(self._experience_file):
            with open(self._experience_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if content:
                parts.append(content)

        if os.path.isdir(self._skills_dir):
            for skill in ("navigate", "grasp", "place", "multi_step"):
                path = os.path.join(self._skills_dir, f"{skill}.md")
                if not os.path.exists(path):
                    continue
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if content:
                    parts.append(content)

        return "\n\n".join(parts)
