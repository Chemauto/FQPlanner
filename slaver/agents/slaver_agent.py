#!/usr/bin/env python
# coding=utf-8
import json
import sys
import time
from logging import getLogger
from typing import Any, Callable, Dict, List, Optional, Union

from slaver.agents.models import ChatMessage
from agent.collaboration import Collaborator
from mcp import ClientSession
from rich.panel import Panel
from rich.text import Text
from slaver.tools.memory import ActionStep, AgentMemory
from slaver.tools.monitoring import AgentLogger, LogLevel, Monitor
import os

# 添加项目根目录到 sys.path，以便导入 serve 模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


class TaskTerminatedException(Exception):
    """Raised when the judge decides to terminate the entire task."""
    pass

logger = getLogger(__name__)


class MultiStepAgent:
    """
    Agent class that solves the given task step by step, using the ReAct framework:
    While the objective is not reached, the agent will perform a cycle of action (given by the LLM) and observation (obtained from the environment).

    Args:
        tools (`list[Tool]`): [`Tool`]s that the agent can use.
        max_steps (`int`, default `20`): Maximum number of steps the agent can take to solve the task.
        verbosity_level (`LogLevel`, default `LogLevel.INFO`): Level of verbosity of the agent's logs.
        step_callbacks (`list[Callable]`, *optional*): Callbacks that will be called at each step.
    """

    def __init__(
        self,
        tools: List[Dict[str, str]],
        model: Callable[[List[Dict[str, str]]], ChatMessage],
        model_path: str,
        collaborator: Collaborator,
        tool_executor: ClientSession,
        robot_name: str,
        max_steps: int = 20,
        verbosity_level: LogLevel = LogLevel.INFO,
        step_callbacks: Optional[List[Callable]] = None,
        log_file: Optional[str] = None,
    ):
        self.tools = tools
        self.model = model
        self.model_path = model_path
        self.collaborator = collaborator
        self.robot_name = robot_name
        self.tool_executor = tool_executor
        self.max_steps = max_steps
        self.step_number = 0
        self.state = {}
        self.memory = AgentMemory()
        self.logger = AgentLogger(level=verbosity_level, log_file=log_file)
        self.monitor = Monitor(self.model, self.logger)
        self.step_callbacks = step_callbacks if step_callbacks is not None else []
        self.step_callbacks.append(self.monitor.update_metrics)
        self.last_tool_result = None  # Store the last tool execution result
        self._last_status = None  # 最后一次工具执行的状态 (success/failure/none/exception/timeout)
        self._scene_context = None  # 缓存场景上下文
        self._captured_images = []  # 存储摄像头捕获的图像 (base64)

    async def run(
        self,
        task: str,
        reset: bool = True,
        images: Optional[List[str]] = None,
        max_steps: Optional[int] = None,
    ):
        """
        Run the agent for the given task.

        Args:
            task (`str`): Task to perform.
            reset (`bool`): Whether to reset the conversation or keep it going from previous run.
            images (`list[str]`, *optional*): Paths to image(s).
            max_steps (`int`, *optional*): Maximum number of steps the agent can take to solve the task. if not provided, will use the agent's default value.

        Example:
        ```py
        from smolagents import CodeAgent
        agent = CodeAgent(tools=[])
        agent.run("What is the result of 2 power 3.7384?")
        ```
        """
        max_steps = max_steps or self.max_steps
        self.task = task

        if reset:
            self.memory.reset()
            self.step_number = 1
            self._scene_context = None
            self._last_status = None

        self.logger.log_task(
            content=self.task.strip(),
            subtitle=f"{type(self.model).__name__} - {(self.model.model_id if hasattr(self.model, 'model_id') else '')}",
            level=LogLevel.INFO,
            title=self.name if hasattr(self, "name") else None,
        )

        while self.step_number <= max_steps:
            step_start_time = time.time()
            step = ActionStep(
                step_number=self.step_number,
                start_time=step_start_time,
                observations_images=images,
            )
            try:
                answer = await self.step(step)
            except TaskTerminatedException as e:
                self.logger.log(str(e), level=LogLevel.INFO)
                return str(e), True  # (result, terminated)

            if answer == "final_answer":
                # Return the actual tool execution result if available, otherwise use default message
                if self.last_tool_result:
                    self.logger.log(
                        f"Task completed with result: {self.last_tool_result}",
                        level=LogLevel.INFO,
                    )
                    return self.last_tool_result, False
                else:
                    return "Mission accomplished", False

            self.collaborator.record_agent_status(self.robot_name, answer)
            step.end_time = time.time()
            self.step_number += 1

        return "Maximum number of attempts reached, Mission not completed", False

    def step(self) -> Optional[Any]:
        """To be implemented in children classes. Should return either None if the step is not final."""
        raise NotImplementedError


class ToolCallingAgent(MultiStepAgent):
    """
    This agent uses JSON-like tool calls, using method `model.get_tool_call` to leverage the LLM engine's tool calling capabilities.

    Args:
        tools (`list[Tool]`): [`Tool`]s that the agent can use.
        prompt_templates ([`~agents.PromptTemplates`], *optional*): Prompt templates.
        planning_interval (`int`, *optional*): Interval at which the agent will run a planning step.
        **kwargs: Additional keyword arguments.
    """

    def __init__(
        self,
        tools: List[Dict[str, str]],
        model: Callable[[List[Dict[str, str]]], ChatMessage],
        model_path: str,
        collaborator: Collaborator,
        robot_name: str,
        **kwargs,
    ):
        self.tool_call = []
        super().__init__(
            tools=tools,
            model=model,
            model_path=model_path,
            collaborator=collaborator,
            robot_name=robot_name,
            **kwargs,
        )

    async def _execute_tool_call(
        self, tool_name: str, tool_arguments: dict, memory_step: ActionStep
    ) -> Union[str, None]:

        self.logger.log(
            Panel(
                Text(f"Calling tool: '{tool_name}' with arguments: {tool_arguments}")
            ),
            level=LogLevel.INFO,
        )
        self.logger.log2file(f"Calling tool: '{tool_name}' with arguments: {tool_arguments}", level=LogLevel.INFO)

        observation = await self.tool_executor(tool_name, json.loads(tool_arguments))

        # [调试] 取消注释以查看原始 MCP 返回值
        # print(f"[DEBUG] Raw observation type: {type(observation)}", file=sys.stderr)
        # print(f"[DEBUG] Raw observation: {observation}", file=sys.stderr)

        # Handle different return formats from MCP
        if hasattr(observation, 'content') and len(observation.content) > 0:
            # print(f"[DEBUG] Observation content type: {type(observation.content)}", file=sys.stderr)
            # print(f"[DEBUG] Observation content[0] type: {type(observation.content[0])}", file=sys.stderr)
            if hasattr(observation.content[0], 'text'):
                observation = observation.content[0].text
            else:
                observation = str(observation.content[0])
        else:
            observation = str(observation)

        # Parse state updates from tool result (format: "result_message" or tuple)
        state_updates = {}
        tool_status = None
        if isinstance(observation, str):
            # Check if observation contains state updates in JSON format
            try:
                # FastMCP tools return tuple as JSON string: ["result", {"state": "updates"}]
                parsed = json.loads(observation)
                if isinstance(parsed, list) and len(parsed) == 2:
                    observation = parsed[0]  # Result message
                    state_updates = parsed[1] if isinstance(parsed[1], dict) else {}
                    tool_status = state_updates.pop("_status", None)
            except (json.JSONDecodeError, ValueError) as e:
                pass  # Not a JSON tuple, use as-is

        # 完成类状态（success/none）：直接停止
        if tool_status in ("success", "none"):
            self._last_status = tool_status
            self.last_tool_result = observation
            # 更新机器人状态
            if state_updates:
                if "_image" in state_updates:
                    self._captured_images.append(state_updates.pop("_image"))
                await self._update_robot_state(state_updates)
            return "final_answer"

        # 错误类状态（failure/exception/timeout）：直接返回给 Master，由 Master LLM + VLM 综合判断
        is_failed = tool_status in ("failure", "exception", "timeout") or (
            isinstance(observation, str) and (
                "失败" in observation or "failed" in observation.lower()
                or "不在场景中" in observation or "已经抓取" in observation
                or "没有抓取" in observation or "无法" in observation
            )
        )

        if is_failed:
            self._last_status = tool_status or "failure"
            self.last_tool_result = observation
            print(f"[Slaver] 工具执行失败: {tool_name}, 状态: {self._last_status}, 交由 Master 决策", file=sys.stderr)
            return observation

        # 正常成功路径：设置 _last_status
        if tool_status:
            self._last_status = tool_status
        elif self._last_status is None:
            self._last_status = "success"

        # Update robot state in Redis if there are state updates
        if state_updates:
            if "_image" in state_updates:
                self._captured_images.append(state_updates.pop("_image"))
            # print(f"[DEBUG] Calling _update_robot_state with: {state_updates}", file=sys.stderr)
            await self._update_robot_state(state_updates)
        # else:
        #     print(f"[DEBUG] No state updates found", file=sys.stderr)

        # Attach current position information to the observation
        position_info = await self._get_current_position_info()
        if position_info:
            enhanced_observation = f"{observation}\n\n[Current Position]\n{position_info}"
        else:
            enhanced_observation = observation

        # Store the last tool execution result with position info
        self.last_tool_result = enhanced_observation

        # Log success message
        success_message = f"Tool '{tool_name}' has been successfully performed"
        self.logger.log2file(success_message, level=LogLevel.INFO)

        self.logger.log(
            f"Observations: {enhanced_observation.replace('[', '|')}",  # escape potential rich-tag-like components
            level=LogLevel.INFO,
        )
        # Log to file
        self.logger.log2file(f"Observations: {enhanced_observation}", level=LogLevel.INFO)

        return enhanced_observation

    async def _update_robot_state(self, state_updates: dict):
        """
        Update robot state in Redis with the provided state updates.

        Args:
            state_updates: Dictionary containing state updates (e.g., {"position": "bedroom", "coordinates": [4.0, 1.0, 0.0]})
        """
        try:
            # Read current robot state
            robot_info = self.collaborator.read_environment("robot")
            if robot_info:
                robot_state = json.loads(robot_info) if isinstance(robot_info, str) else robot_info
            else:
                robot_state = {"position": "entrance", "coordinates": [0.0, 0.0, 0.0], "holding": None, "status": "idle"}

            # Update with new state
            robot_state.update(state_updates)

            # Write back to Redis
            self.collaborator.record_environment("robot", json.dumps(robot_state))
            # print(f"[State Update] Robot state updated: {state_updates}", file=sys.stderr)
        except Exception as e:
            # print(f"[State Update Error] Failed to update robot state: `{e}`", file=sys.stderr)
            pass

    async def _get_current_position_info(self) -> str:
        """
        Get current robot position information from collaborator.

        Returns:
            A formatted string with current position details, or None if unavailable.
        """
        try:
            # Read robot info from collaborator
            robot_info = self.collaborator.read_environment("robot")
            if not robot_info:
                return None

            robot_info = json.loads(robot_info) if isinstance(robot_info, str) else robot_info
            current_position = robot_info.get("position")

            if not current_position:
                return "Position: Unknown"

            # Read holding state
            holding = robot_info.get("holding")
            holding_line = f"\nHolding: {holding}" if holding else ""

            # First, try to get coordinates from robot state (if set by navigation)
            robot_coordinates = robot_info.get("coordinates")
            if robot_coordinates and len(robot_coordinates) >= 3:
                x, y, z = robot_coordinates[0], robot_coordinates[1], robot_coordinates[2]

                # Try to get description from scene
                scene_obj = self.collaborator.read_environment(current_position)
                description = ""
                if scene_obj:
                    scene_obj = json.loads(scene_obj) if isinstance(scene_obj, str) else scene_obj
                    description = scene_obj.get("description", "")

                if description:
                    return f"[Current Robot Position]\nLocation: {current_position} ({description})\nCoordinates: ({x}, {y}, {z}){holding_line}"
                else:
                    return f"[Current Robot Position]\nLocation: {current_position}\nCoordinates: ({x}, {y}, {z}){holding_line}"

            # Fallback: Try to get position coordinates from scene
            scene_obj = self.collaborator.read_environment(current_position)
            if scene_obj:
                scene_obj = json.loads(scene_obj) if isinstance(scene_obj, str) else scene_obj
                position_coords = scene_obj.get("position", [])
                description = scene_obj.get("description", "")

                if position_coords and len(position_coords) >= 3:
                    x, y, z = position_coords[0], position_coords[1], position_coords[2]
                    if description:
                        return f"[Current Robot Position]\nLocation: {current_position} ({description})\nCoordinates: ({x}, {y}, {z}){holding_line}"
                    else:
                        return f"[Current Robot Position]\nLocation: {current_position}\nCoordinates: ({x}, {y}, {z}){holding_line}"
                elif description:
                    return f"[Current Robot Position]\nLocation: {current_position} ({description})\nCoordinates: Not available{holding_line}"
                else:
                    return f"[Current Robot Position]\nLocation: {current_position}\nCoordinates: Not available{holding_line}"
            else:
                return f"[Current Robot Position]\nLocation: {current_position}\nCoordinates: Not found in scene{holding_line}"

        except Exception as e:
            # print(f"[Get Position Error] `{e}`")
            return None

    async def _get_enhanced_task_with_context(self) -> str:
        """
        增强任务描述，添加场景信息（物体、家具、机器人位置），帮助 LLM 做出更好的决策。
        场景信息在第一次调用时查询，后续复用缓存。
        """
        if self._scene_context is None:
            self._scene_context = self._build_scene_context()

        parts = []
        if self._scene_context:
            parts.append(self._scene_context)

        parts.append(f"Task: {self.task}")
        return "\n\n".join(parts)

    def _build_scene_context(self) -> str:
        """查询仿真后端，构建场景上下文文字"""
        try:
            from serve.sim import get_scene
            scene = get_scene()
            if not scene or "error" in scene:
                return None
        except Exception as e:
            print(f"[SceneContext] 查询场景失败: {e}", file=sys.stderr)
            return None

        lines = ["## Current Scene"]

        # 家具
        fixtures = scene.get("fixtures", {})
        if fixtures:
            lines.append("\nFixtures:")
            for name, info in fixtures.items():
                pos = info.get("pos", [])
                size = info.get("size", [])
                ftype = info.get("type", "")
                # 计算表面高度 = 中心z + 半高
                if len(pos) >= 3 and len(size) >= 3:
                    surface_z = pos[2] + size[2] / 2
                    lines.append(
                        f"- {name} ({ftype}): pos [{pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}], "
                        f"size [{size[0]:.2f}, {size[1]:.2f}, {size[2]:.2f}], "
                        f"surface_z={surface_z:.2f}"
                    )
                else:
                    lines.append(f"- {name} ({ftype})")

        # 物体
        objects = scene.get("objects", {})
        if objects:
            lines.append("\nObjects:")
            for name, info in objects.items():
                pos = info.get("pos", [])
                grasped = info.get("grasped", False)
                status = "grasped" if grasped else "free"
                lines.append(f"- {name}: [{pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}] ({status})")

        # 机器人
        robot = scene.get("robot", {})
        if robot:
            bp = robot.get("base_pos", [])
            ep = robot.get("ee_pos", [])
            yaw = robot.get("yaw", 0)
            lines.append("\nRobot:")
            lines.append(f"- base: [{bp[0]:.2f}, {bp[1]:.2f}, {bp[2]:.2f}], yaw={yaw:.1f}")
            lines.append(f"- end-effector: [{ep[0]:.2f}, {ep[1]:.2f}, {ep[2]:.2f}]")

        return "\n".join(lines)

    async def step(self, memory_step: ActionStep) -> Union[None, Any]:
        """
        Perform one step in the ReAct framework: the agent thinks, acts, and observes the result.
        Returns None if the step is not final.
        """
        self.logger.log_rule(f"Step {self.step_number}", level=LogLevel.INFO)

        # Add new step in logs
        current_status = self.collaborator.read_agent_status(self.robot_name)

        # 增强任务描述：添加当前位置和场景信息
        enhanced_task = await self._get_enhanced_task_with_context()

        model_message: ChatMessage = self.model(
            task=enhanced_task,
            current_status=current_status,
            model_path=self.model_path,
            tools_to_call_from=self.tools,
            stop_sequences=["Observation:"],
            images=self._captured_images if self._captured_images else None,
        )
        self._captured_images = []
        memory_step.model_output_message = model_message

        # Prepare log content - avoid logging full API response object
        if model_message.content:
            log_content = model_message.content
        elif model_message.tool_calls:
            # For tool_calls, log only the tool call info, not the full API response
            tool_call_info = []
            for tc in model_message.tool_calls:
                tool_call_info.append({
                    "name": tc.function.name,
                    "arguments": tc.function.arguments
                })
            log_content = json.dumps(tool_call_info, ensure_ascii=False)
        else:
            log_content = str(model_message.raw)

        # [调试] 取消注释以查看 LLM 完整输出（含 reasoning_content）
        # self.logger.log_markdown(
        #     content=log_content,
        #     title="Output message of the LLM:",
        #     level=LogLevel.DEBUG,
        # )

        # Initialize tool_name and tool_arguments
        tool_name = None
        tool_arguments = None

        # Check if model returned native tool_calls format
        if model_message.tool_calls:
            tool_call = model_message.tool_calls[0]
            tool_name = tool_call.function.name
            tool_arguments = tool_call.function.arguments
        else:
            # Try to parse tool call from JSON content (fallback for models that return JSON)
            if model_message.content:
                try:
                    parsed_content = json.loads(model_message.content)
                    if isinstance(parsed_content, dict) and "name" in parsed_content:
                        tool_name = parsed_content.get("name")
                        tool_arguments = json.dumps(parsed_content.get("arguments", {}))
                except (json.JSONDecodeError, TypeError):
                    pass  # Content is not valid JSON, continue

        # If no tool call found, return final_answer
        if not tool_name:
            return "final_answer"

        current_call = {"tool_name": tool_name, "tool_arguments": tool_arguments}

        if self.tool_call and self.tool_call[-1] == current_call:
            return "final_answer"
        else:
            self.tool_call.append(current_call)

        return await self._execute_tool_call(tool_name, tool_arguments, memory_step)
    
