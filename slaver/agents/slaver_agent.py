#!/usr/bin/env python
# coding=utf-8
import json
import sys
import time
from logging import getLogger
from typing import Any, Callable, Dict, List, Optional, Union

from slaver.agents.models import ChatMessage
from flag_scale.flagscale.agent.collaboration import Collaborator
from mcp import ClientSession
from rich.panel import Panel
from rich.text import Text
from slaver.tools.memory import ActionStep, AgentMemory, SceneMemory
from slaver.tools.monitoring import AgentLogger, LogLevel, Monitor

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
        self.scene = SceneMemory(collaborator)
        self.logger = AgentLogger(level=verbosity_level, log_file=log_file)
        self.monitor = Monitor(self.model, self.logger)
        self.step_callbacks = step_callbacks if step_callbacks is not None else []
        self.step_callbacks.append(self.monitor.update_metrics)
        self.last_tool_result = None  # Store the last tool execution result

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
            answer = await self.step(step)
            if answer == "final_answer":
                # Return the actual tool execution result if available, otherwise use default message
                if self.last_tool_result:
                    self.logger.log(
                        f"Task completed with result: {self.last_tool_result}",
                        level=LogLevel.INFO,
                    )
                    return self.last_tool_result
                else:
                    return "Mission accomplished"

            self.collaborator.record_agent_status(self.robot_name, answer)
            step.end_time = time.time()
            self.step_number += 1

        return "Maximum number of attempts reached, Mission not completed"

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
        # Log to file
        self.logger.log2file(f"Calling tool: '{tool_name}' with arguments: {tool_arguments}", level=LogLevel.INFO)

        observation = await self.tool_executor(tool_name, json.loads(tool_arguments))

        # Debug: Print raw observation type and content
        print(f"[DEBUG] Raw observation type: {type(observation)}", file=sys.stderr)
        print(f"[DEBUG] Raw observation: {observation}", file=sys.stderr)

        # Handle different return formats from MCP
        if hasattr(observation, 'content') and len(observation.content) > 0:
            print(f"[DEBUG] Observation content type: {type(observation.content)}", file=sys.stderr)
            print(f"[DEBUG] Observation content[0] type: {type(observation.content[0])}", file=sys.stderr)
            if hasattr(observation.content[0], 'text'):
                observation = observation.content[0].text
            else:
                observation = str(observation.content[0])
        else:
            observation = str(observation)

        # Parse state updates from tool result (format: "result_message" or tuple)
        state_updates = {}
        if isinstance(observation, str):
            # Check if observation contains state updates in JSON format
            try:
                # FastMCP tools return tuple as JSON string: ["result", {"state": "updates"}]
                parsed = json.loads(observation)
                if isinstance(parsed, list) and len(parsed) == 2:
                    observation = parsed[0]  # Result message
                    state_updates = parsed[1] if isinstance(parsed[1], dict) else {}
                    print(f"[DEBUG] Parsed state updates: {state_updates}", file=sys.stderr)
            except (json.JSONDecodeError, ValueError) as e:
                print(f"[DEBUG] Failed to parse JSON: {e}", file=sys.stderr)
                pass  # Not a JSON tuple, use as-is

        # Update robot state in Redis if there are state updates
        if state_updates:
            print(f"[DEBUG] Calling _update_robot_state with: {state_updates}", file=sys.stderr)
            await self._update_robot_state(state_updates)
        else:
            print(f"[DEBUG] No state updates found", file=sys.stderr)

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

        # Construct memory input
        memory_input = {
            "tool_name": tool_name,
            "arguments": tool_arguments,
            "result": observation,  # Use original observation for memory prediction
        }
        try:
            await self.memory_predict(memory_input)
        except Exception as e:
            print(f"[Scene Update Error] `{e}`")

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
            print(f"[State Update] Robot state updated: {state_updates}", file=sys.stderr)
        except Exception as e:
            print(f"[State Update Error] Failed to update robot state: `{e}`", file=sys.stderr)

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
                    return f"Location: {current_position} ({description})\nCoordinates: ({x}, {y}, {z})"
                else:
                    return f"Location: {current_position}\nCoordinates: ({x}, {y}, {z})"

            # Fallback: Try to get position coordinates from scene
            scene_obj = self.collaborator.read_environment(current_position)
            if scene_obj:
                scene_obj = json.loads(scene_obj) if isinstance(scene_obj, str) else scene_obj
                position_coords = scene_obj.get("position", [])
                description = scene_obj.get("description", "")

                if position_coords and len(position_coords) >= 3:
                    x, y, z = position_coords[0], position_coords[1], position_coords[2]
                    if description:
                        return f"Location: {current_position} ({description})\nCoordinates: ({x}, {y}, {z})"
                    else:
                        return f"Location: {current_position}\nCoordinates: ({x}, {y}, {z})"
                elif description:
                    return f"Location: {current_position} ({description})\nCoordinates: Not available"
                else:
                    return f"Location: {current_position}\nCoordinates: Not available"
            else:
                return f"Location: {current_position}\nCoordinates: Not found in scene"

        except Exception as e:
            print(f"[Get Position Error] `{e}`")
            return None

    async def memory_predict(self, memory_input: dict) -> str:
        """
        Use the model to predict the scene-level effect of the current tool execution.
        Possible effects: add_object, remove_object, move_object, position.
        """

        prompt = self.scene.get_action_type_prompt(memory_input)

        model_message: ChatMessage = self.model(
            task=prompt, current_status="", model_path=self.model_path
        )

        action_type = model_message.content.strip().lower()

        self.scene.apply_action(action_type, json.loads(memory_input["arguments"]))

    async def step(self, memory_step: ActionStep) -> Union[None, Any]:
        """
        Perform one step in the ReAct framework: the agent thinks, acts, and observes the result.
        Returns None if the step is not final.
        """
        self.logger.log_rule(f"Step {self.step_number}", level=LogLevel.INFO)

        # Add new step in logs
        current_status = self.collaborator.read_agent_status(self.robot_name)
        model_message: ChatMessage = self.model(
            task=self.task,
            current_status=current_status,
            model_path=self.model_path,
            tools_to_call_from=self.tools,
            stop_sequences=["Observation:"],
        )
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

        self.logger.log_markdown(
            content=log_content,
            title="Output message of the LLM:",
            level=LogLevel.DEBUG,
        )

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
