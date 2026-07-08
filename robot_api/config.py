"""Configuration for the unified robot API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "robot_api" / "config.yaml"
DEFAULT_URL = "http://127.0.0.1:5001"
DEFAULT_TIMEOUT = 120


@dataclass(frozen=True)
class BackendConfig:
    name: str
    enabled: bool
    provide_state: bool
    accept_action: bool
    required: bool
    url: str = ""
    timeout: float = DEFAULT_TIMEOUT
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class RobotApiConfig:
    backends: list[BackendConfig]

    @property
    def server_url(self) -> str:
        for backend in self.backends:
            if backend.enabled and backend.url:
                return backend.url
        return DEFAULT_URL

    @property
    def timeout(self) -> float:
        for backend in self.backends:
            if backend.enabled:
                return backend.timeout
        return DEFAULT_TIMEOUT

    @property
    def backend(self) -> str:
        for backend in self.backends:
            if backend.enabled:
                return backend.name
        return "mujoco"

    def state_backends(self) -> list[BackendConfig]:
        return [b for b in self.backends if b.enabled and b.provide_state]

    def action_backends(self) -> list[BackendConfig]:
        return [b for b in self.backends if b.enabled and b.accept_action]


def _as_bool(value, default=False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        if yaml is not None:
            with path.open("r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return _read_simple_yaml(path)
    except Exception:
        return {}


def _read_simple_yaml(path: Path) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split(" #", 1)[0].rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        text = line.strip()
        if ":" not in text:
            continue
        key, value = text.split(":", 1)
        key = key.strip().strip("\"'")
        value = value.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if not value:
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _parse_scalar(value)
    return root


def _parse_scalar(value: str):
    value = value.strip().strip("\"'")
    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        if lowered.startswith("0x"):
            return int(lowered, 16)
        if any(ch in value for ch in (".", "e", "E")):
            return float(value)
        return int(value)
    except ValueError:
        return value


def _default_backends() -> dict[str, dict[str, Any]]:
    return {
        "mujoco": {
            "enabled": 1,
            "provide_state": 1,
            "accept_action": 1,
            "required": 1,
            "url": DEFAULT_URL,
            "timeout": DEFAULT_TIMEOUT,
        }
    }


def load_robot_api_config() -> RobotApiConfig:
    data = _read_yaml(CONFIG_PATH)
    backends_cfg = data.get("backends") or _default_backends()

    env_url = os.getenv("ROBOT_API_URL")
    env_timeout = os.getenv("ROBOT_API_TIMEOUT")
    backends: list[BackendConfig] = []

    for name, raw in backends_cfg.items():
        raw = raw or {}
        url = str(raw.get("url") or "").rstrip("/")
        if name == "mujoco" and env_url:
            url = env_url.rstrip("/")
        timeout = float(env_timeout or raw.get("timeout") or DEFAULT_TIMEOUT)
        backends.append(
            BackendConfig(
                name=str(name),
                enabled=_as_bool(raw.get("enabled"), default=False),
                provide_state=_as_bool(raw.get("provide_state"), default=False),
                accept_action=_as_bool(raw.get("accept_action"), default=False),
                required=_as_bool(raw.get("required"), default=False),
                url=url,
                timeout=timeout,
                raw=raw,
            )
        )

    if not backends:
        return RobotApiConfig(
            backends=[
                BackendConfig(
                    name="mujoco",
                    enabled=True,
                    provide_state=True,
                    accept_action=True,
                    required=True,
                    url=DEFAULT_URL,
                    timeout=DEFAULT_TIMEOUT,
                    raw={},
                )
            ]
        )
    return RobotApiConfig(backends=backends)
