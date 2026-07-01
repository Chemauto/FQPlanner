"""Public semantic robot capabilities.

Master, Slaver, Deploy and Nav2 should import this module instead of importing
simulator-specific clients. Parameters here are task-level semantics only.
"""

from __future__ import annotations

from .runtime import RobotRuntime


_RUNTIME = RobotRuntime()


def get_scene():
    return _RUNTIME.get_state("scene")


def get_objects():
    return _RUNTIME.get_state("objects")


def get_fixtures():
    return _RUNTIME.get_state("fixtures")


def get_robot_state():
    return _RUNTIME.get_state("robot_state")


def get_base_status():
    return _RUNTIME.get_state("base_status")


def get_arm_status():
    return _RUNTIME.get_state("arm_status")


def get_map_data(params: dict | None = None, timeout=None):
    return _RUNTIME.get_state("map_data", params or {})


def grasp_object(object_name: str):
    return _RUNTIME.execute("grasp_object", {"object_name": object_name})


def place_object(object_name: str, target):
    return _RUNTIME.execute("place_object", {"object_name": object_name, "target": target})


def navigate_to(target, yaw=None):
    return _RUNTIME.execute("navigate_to", {"target": target, "yaw": yaw})


def move_forward(duration: float = 1.0, speed=0.5):
    return _RUNTIME.execute("move_forward", {"duration": duration, "speed": speed})


def rotate(direction: str = "left", duration: float = 1.0, speed=0.5):
    return _RUNTIME.execute(
        "rotate",
        {"direction": direction, "duration": duration, "speed": speed},
    )


def capture_image(context: str = "", camera_name: str | None = None):
    return _RUNTIME.get_state("image", {"context": context, "camera_name": camera_name})


def get_object_pos(object_name: str):
    objects = get_objects()
    if isinstance(objects, dict) and objects.get("success") is not False:
        item = objects.get(object_name)
        if isinstance(item, dict):
            return item.get("pos")
    return None


def is_object_grasped(object_name: str) -> bool:
    objects = get_objects()
    if isinstance(objects, dict) and objects.get("success") is not False:
        item = objects.get(object_name)
        if isinstance(item, dict):
            return bool(item.get("grasped", False))
    return False


def check_success() -> dict:
    """Query the backend for ground-truth task success (ALFWorld: won signal).
    Returns {"won": True/False} or {"won": None} if backend doesn't support it.
    """
    return _RUNTIME.get_state("success")


def get_scene_state() -> dict:
    """Get the current symbolic scene state (ALFWorld snapshot or MuJoCo belief)."""
    return _RUNTIME.get_state("scene_state")


def reset_env() -> dict:
    """Reset the simulation environment (ALFWorld: start a new episode, clear step counter)."""
    return _RUNTIME.get_state("reset")


def set_backend_url(url: str) -> None:
    """Compatibility helper for local development."""
    _RUNTIME.set_backend_url(url)
