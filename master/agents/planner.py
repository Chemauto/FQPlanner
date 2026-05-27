from typing import Any, Dict, Union

import yaml
from agents.prompts import MASTER_PLANNING_PLANNING
from agent.collaboration import Collaborator
from openai import AzureOpenAI, OpenAI


class GlobalTaskPlanner:
    """A tool planner to plan task into sub-tasks."""

    def __init__(
        self,
        config: Union[Dict, str] = None,
    ) -> None:
        self.collaborator = Collaborator.from_config(config["collaborator"])

        self.global_model: Any
        self.model_name: str
        self.global_model, self.model_name = self._get_model_info_from_config(
            config["model"]
        )

        self.profiling = config["profiling"]

    def _get_model_info_from_config(self, config: Dict) -> tuple:
        """Get the model info from config."""
        candidate = config["model_dict"]
        if candidate["cloud_model"] in config["model_select"]:
            if candidate["cloud_type"] == "azure":
                model_name = config["model_select"]
                model_client = AzureOpenAI(
                    azure_endpoint=candidate["azure_endpoint"],
                    azure_deployment=candidate["azure_deployment"],
                    api_version=candidate["azure_api_version"],
                    api_key=candidate["azure_api_key"],
                )
            elif candidate["cloud_type"] == "default":
                model_client = OpenAI(
                    base_url=candidate["cloud_server"],
                    api_key=candidate["cloud_api_key"],
                )
                model_name = config["model_select"]
            else:
                raise ValueError(f"Unsupported cloud type: {candidate['cloud_type']}")
            return model_client, model_name
        raise ValueError(f"Unsupported model: {config['model_select']}")

    def _init_config(self, config_path="config.yaml"):
        """Initialize configuration"""
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        return config

    def display_profiling_info(self, description: str, message: any):
        """
        Outputs profiling information if profiling is enabled.

        :param message: The content to be printed. Can be of any type.
        :param description: A brief title or description for the message.
        """
        if self.profiling:
            module_name = "master"  # Name of the current module
            print(f" [{module_name}] {description}:")
            print(message)

    def forward(self, task: str, history: list = None, experiences: str = "") -> str:
        """Get the sub-tasks from the task."""

        all_robots_name = self.collaborator.read_all_agents_name()
        all_robots_info = self.collaborator.read_all_agents_info()
        all_environments_info = self.collaborator.read_environment(name=None)

        # ===== 新增：从仿真获取真实物体坐标 =====
        try:
            import requests
            resp = requests.get("http://127.0.0.1:5001/objects", timeout=3)
            if resp.status_code == 200:
                sim_objects = resp.json()
                # 把坐标注入 scene_info
                if isinstance(all_environments_info, dict):
                    for obj_name, obj_data in sim_objects.items():
                        if obj_name in all_environments_info:
                            if isinstance(all_environments_info[obj_name], str):
                                import json
                                info = json.loads(all_environments_info[obj_name])
                            else:
                                info = all_environments_info[obj_name]
                            pos = obj_data.get("pos", [])
                            info["position"] = f"({pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f})" if pos else "unknown"
                            info["grasped"] = obj_data.get("grasped", False)
                            all_environments_info[obj_name] = info
        except Exception as e:
            print(f"[Planner] Warning: could not fetch sim object positions: {e}")
        # ===== 新增结束 =====

        content = MASTER_PLANNING_PLANNING.format(
            robot_name_list=all_robots_name,
            robot_tools_info=all_robots_info,
            task=task,
            scene_info=all_environments_info,
            experience_section=experiences
        )

        messages = self._build_messages(content, history)
        return self._call_llm(messages)

    def generate(self, prompt: str) -> str:
        """直接调用 LLM，不套任务规划模板。用于经验总结等场景。"""
        messages = [{"role": "user", "content": prompt}]
        return self._call_llm(messages)

    def _build_messages(self, content: str, history: list = None) -> list:
        """构建消息列表。"""
        messages = []
        if history:
            for msg in history:
                c = msg.get("content")
                if isinstance(c, list):
                    c = "".join(p.get("text", "") if isinstance(p, dict) else getattr(p, "text", "") for p in c)
                elif c is None:
                    c = ""
                elif not isinstance(c, str):
                    c = str(c)
                messages.append({"role": msg["role"], "content": c})
        messages.append({"role": "user", "content": content})
        return messages

    def _call_llm(self, messages: list) -> str:
        """调用 LLM 并返回文本结果。"""
        self.display_profiling_info("messages", messages)

        from datetime import datetime
        start_inference = datetime.now()
        response = self.global_model.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=0.2,
            top_p=0.9,
            max_tokens=2048,
            seed=42,
        )
        end_inference = datetime.now()

        self.display_profiling_info(
            "inference time",
            f"inference start:{start_inference} end:{end_inference} during:{end_inference-start_inference}",
        )
        self.display_profiling_info("response", response)
        self.display_profiling_info("response.usage", response.usage)

        raw = response.choices[0].message.content
        if raw is None:
            raw = ""
        elif isinstance(raw, list):
            raw = "".join(
                part.get("text", "") if isinstance(part, dict) else getattr(part, "text", "")
                for part in raw
            )
        elif not isinstance(raw, str):
            raw = str(raw)
        return raw
