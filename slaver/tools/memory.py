###############################################################
# Copyright 2025 BAAI. All rights reserved.
###############################################################
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import json
from dataclasses import asdict, dataclass
from logging import getLogger
from typing import TYPE_CHECKING, Any, Dict, List, Optional, TypedDict, Union

from slaver.agents.models import ChatMessage, MessageRole
from slaver.tools.monitoring import AgentLogger, LogLevel
from slaver.tools.utils import AgentError, make_json_serializable

if TYPE_CHECKING:
    from slaver.agents.models import ChatMessage
    from slaver.tools.monitoring import AgentLogger


logger = getLogger(__name__)


class Message(TypedDict):
    role: MessageRole
    content: Union[str, List[Dict]]


@dataclass
class ToolCall:
    name: str
    arguments: Any
    id: str


@dataclass
class MemoryStep:
    def dict(self):
        return asdict(self)

    def to_messages(self) -> List[Dict[str, Any]]:
        raise NotImplementedError


@dataclass
class ActionStep(MemoryStep):
    model_input_messages: Optional[List[Message]] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    step_number: Optional[int] = None
    error: Optional[AgentError] = None
    duration: Optional[float] = None
    model_output_message: ChatMessage = None
    model_output: Optional[str] = None
    observations: Optional[str] = None
    observations_images: Optional[List[str]] = None
    action_output: Any = None

    def dict(self):
        # We overwrite the method to parse the tool_calls and action_output manually
        return {
            "model_input_messages": self.model_input_messages,
            "tool_calls": (
                [tc.dict() for tc in self.tool_calls] if self.tool_calls else []
            ),
            "start_time": self.start_time,
            "end_time": self.end_time,
            "step": self.step_number,
            "error": self.error.dict() if self.error else None,
            "duration": self.duration,
            "model_output_message": self.model_output_message,
            "model_output": self.model_output,
            "observations": self.observations,
            "action_output": make_json_serializable(self.action_output),
        }

    def to_messages(
        self, summary_mode: bool = False, show_model_input_messages: bool = False
    ) -> List[Message]:
        messages = []
        if self.model_input_messages is not None and show_model_input_messages:
            messages.append(
                Message(role=MessageRole.SYSTEM, content=self.model_input_messages)
            )
        if self.model_output is not None and not summary_mode:
            messages.append(
                Message(
                    role=MessageRole.ASSISTANT,
                    content=[{"type": "text", "text": self.model_output.strip()}],
                )
            )

        if self.observations_images:
            messages.append(
                Message(
                    role=MessageRole.USER,
                    content=[{"type": "text", "text": "Here are the observed images:"}]
                    + [
                        {
                            "type": "image",
                            "image": image,
                        }
                        for image in self.observations_images
                    ],
                )
            )
        return messages


@dataclass
class PlanningStep(MemoryStep):
    model_input_messages: List[Message]
    model_output_message_facts: ChatMessage
    facts: str
    model_output_message_plan: ChatMessage
    plan: str


@dataclass
class TaskStep(MemoryStep):
    task: str
    task_images: Optional[List[str]] = None

    def to_messages(self) -> List[Message]:
        content = f"{self.task}"
        return [Message(role=MessageRole.USER, content=content)]


class AgentMemory:
    def __init__(self):
        self.steps: List[Union[TaskStep, ActionStep, PlanningStep]] = []

    def reset(self):
        self.steps = []

    def get_succinct_steps(self) -> list[dict]:
        return [
            {
                key: value
                for key, value in step.dict().items()
                if key != "model_input_messages"
            }
            for step in self.steps
        ]

    def get_full_steps(self) -> list[dict]:
        return [step.dict() for step in self.steps]

    def replay(self, logger: AgentLogger, detailed: bool = False):
        """Prints a pretty replay of the agent's steps.

        Args:
            logger (AgentLogger): The logger to print replay logs to.
            detailed (bool, optional): If True, also displays the memory at each step. Defaults to False.
                Careful: will increase log length exponentially. Use only for debugging.
        """
        logger.console.log("Replaying the agent's steps:")
        for step in self.steps:
            if isinstance(step, TaskStep):
                logger.log_task(step.task, "", level=LogLevel.ERROR)
            elif isinstance(step, ActionStep):
                logger.log_rule(f"Step {step.step_number}", level=LogLevel.ERROR)
                if detailed:
                    logger.log_messages(step.model_input_messages)
                logger.log_markdown(
                    title="Agent output:",
                    content=step.model_output,
                    level=LogLevel.ERROR,
                )
            elif isinstance(step, PlanningStep):
                logger.log_rule("Planning step", level=LogLevel.ERROR)
                if detailed:
                    logger.log_messages(step.model_input_messages, level=LogLevel.ERROR)
                logger.log_markdown(
                    title="Agent output:",
                    content=step.facts + " " + step.plan,
                    level=LogLevel.ERROR,
                )


class SceneMemory:
    def __init__(self, collaborator):
        self.collaborator = collaborator
        # Build Chinese→English name mapping from scene data in Redis
        self._name_map = {}  # description → key (e.g. "厨房桌子" → "kitchenTable")
        self._build_name_map()

    def _build_name_map(self):
        """Build mapping from Chinese description to English key for all scene objects."""
        try:
            # read_environment(None) returns all environment data
            all_env = self.collaborator.read_environment(None)
            if all_env:
                for key, value in all_env.items():
                    if key == "robot":
                        continue
                    if isinstance(value, str):
                        value = json.loads(value)
                    desc = value.get("description", "")
                    if desc:
                        self._name_map[desc] = key
        except Exception as e:
            print(f"[SceneMemory] Failed to build name map: {e}")

    def _resolve_position(self, position: str) -> str:
        """Convert Chinese position name to English key if needed."""
        if position in self._name_map:
            return self._name_map[position]
        return position

    def add_object(self, target: str):
        robot_info = self.collaborator.read_environment("robot")
        if not robot_info:
            print("[Error] robot_info not found")
            return

        position = robot_info.get("position")
        holding = robot_info.get("holding")

        if holding != target:
            print(f"[Warning] Robot is not holding '{target}', but holding '{holding}'")
            return

        # Convert Chinese position name to English key
        redis_key = self._resolve_position(position)
        scene_obj = self.collaborator.read_environment(redis_key)
        if not scene_obj:
            print(f"[Error] Scene object at position '{position}' not found")
            return

        contains = scene_obj.get("contains", [])
        if target not in contains:
            contains.append(target)
        scene_obj["contains"] = contains

        robot_info["holding"] = None

        self.collaborator.record_environment("robot", json.dumps(robot_info))
        self.collaborator.record_environment(redis_key, json.dumps(scene_obj))

    def remove_object(self, target: str):
        robot_info = self.collaborator.read_environment("robot")
        if not robot_info:
            print("[Error] robot_info not found")
            return

        position = robot_info.get("position")

        # Convert Chinese position name to English key
        redis_key = self._resolve_position(position)
        scene_obj = self.collaborator.read_environment(redis_key)
        if not scene_obj:
            print(f"[Error] Scene object at position '{position}' (key: {redis_key}) not found")
            return

        contains = scene_obj.get("contains", [])
        if target not in contains:
            print(f"[Warning] Object '{target}' not found in '{position}'")
            return

        contains.remove(target)
        scene_obj["contains"] = contains
        robot_info["holding"] = target

        self.collaborator.record_environment("robot", json.dumps(robot_info))
        self.collaborator.record_environment(redis_key, json.dumps(scene_obj))

    def move_to(self, target: str, coordinates: list = None):
        robot_info = self.collaborator.read_environment("robot")
        if not robot_info:
            print("[Error] robot_info not found")
            return

        # 更新位置名称
        robot_info["position"] = target

        # 使用提供的坐标，或者从场景数据获取
        if coordinates and len(coordinates) >= 3:
            robot_info["coordinates"] = coordinates
        else:
            # 从场景数据获取目标坐标
            redis_key = self._resolve_position(target)
            scene_obj = self.collaborator.read_environment(redis_key)
            if scene_obj:
                if isinstance(scene_obj, str):
                    scene_obj = json.loads(scene_obj)
                coords = scene_obj.get("position", [])
                if coords and len(coords) >= 3:
                    robot_info["coordinates"] = coords

        success = self.collaborator.record_environment("robot", json.dumps(robot_info))
        if not success:
            print(f"[Error] Failed to update robot position to '{target}'")

    def apply_action(self, action_type: str, args: dict, coordinates: list = None):
        """
        Apply scene update based on action_type: 'add_object', 'remove_object', or 'position'
        """
        print(f"[Scene Update] Applying `{action_type}` with args {args}")
        try:
            # Accept multiple key names for flexibility (object, object_name, target)
            target = args.get("object") or args.get("object_name") or args.get("target")

            if "remove_object" in action_type:
                if target:
                    self.remove_object(target)
                else:
                    print(f"[Scene Update] Missing object key for remove_object, args: {args}")

            elif "add_object" in action_type:
                if target:
                    self.add_object(target)
                else:
                    print(f"[Scene Update] Missing object key for add_object, args: {args}")

            elif "position" in action_type:
                if target:
                    self.move_to(target, coordinates)
                else:
                    print(f"[Scene Update] Missing target key for position, args: {args}")

            else:
                print(f"[Scene Update] Unknown action `{action_type}`")
        except Exception as e:
            print(f"[Scene Update] Error applying action `{action_type}`: {e}")

    @staticmethod
    def get_action_type_prompt(memory_input: Dict) -> str:
        return f"""
You are a robot task planner responsible for updating a symbolic scene memory.

Each tool the robot calls has a side effect on the world, which can be one of the following **scene-level action types**:

- `add_object`: An object that was previously not in the environment (e.g., held by the robot) is placed back into the environment, like placing an apple into a basket.
- `remove_object`: An object is taken out of the environment (e.g., from a table) and held by the robot, such as grasping or picking up something.
- `position`: The environment is not changed; the robot itself may move (e.g., navigation), but no object is added, removed, or moved.

---

Given the following tool execution, predict what scene-level action type this tool represents.

Tool name: {memory_input['tool_name']}
Arguments: {json.dumps(memory_input['arguments'], ensure_ascii=False)}
Result: {memory_input['result']}

---

Answer strictly with one of the following:
[add_object, remove_object, position]

Answer with only one action type from the list above. Do not include any explanation.
"""


__all__ = ["AgentMemory", "SceneMemory"]

