"""Viewer UI image widgets for 3DGS camera feeds."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Sequence

import numpy as np


DEFAULT_VIEWER_CAMERA_NAMES = ("overhead_cam", "head_cam", "right_arm_cam", "left_arm_cam")


@dataclass(frozen=True)
class ViewerScreenBinding:
    camera_name: str
    camera_id: int


@dataclass(frozen=True)
class WidgetLayoutSpec:
    left: int
    top: int
    width: int
    height: int


def viewer_widget_layout_specs(
    camera_names: Sequence[str],
    width: int,
    height: int,
    *,
    margin: int = 10,
    gap: int = 10,
    cols: int = 2,
) -> tuple[WidgetLayoutSpec, ...]:
    """Lay out camera feeds as viewer UI widgets, not scene geometry."""
    if width <= 0 or height <= 0:
        raise ValueError("viewer widget dimensions must be positive")
    if cols <= 0:
        raise ValueError("viewer widget column count must be positive")

    specs = []
    for index, camera_name in enumerate(camera_names):
        row = index // cols
        col = index % cols
        specs.append(
            WidgetLayoutSpec(
                left=int(margin + col * (width + gap)),
                top=int(margin + row * (height + gap)),
                width=int(width),
                height=int(height),
            )
        )
    return tuple(specs)


def _iter_model_cameras(model) -> Iterable:
    cameras = getattr(model, "cameras", None)
    return getattr(cameras, "cameras", cameras)


def camera_screen_bindings(model, camera_names: Sequence[str]) -> tuple[ViewerScreenBinding, ...]:
    available: Dict[str, int] = {}
    for index, camera in enumerate(_iter_model_cameras(model)):
        name = getattr(camera, "name", "")
        if name:
            available[name] = index

    missing = [name for name in camera_names if name not in available]
    if missing:
        raise ValueError(
            f"missing viewer camera(s): {', '.join(missing)}; available: {', '.join(sorted(available))}"
        )

    return tuple(
        ViewerScreenBinding(
            camera_name=name,
            camera_id=available[name],
        )
        for name in camera_names
    )


def _make_layout(layout_cls, spec: WidgetLayoutSpec):
    return layout_cls(left=spec.left, top=spec.top, width=spec.width, height=spec.height)


def create_viewer_screen_images(
    render,
    bindings: Sequence[ViewerScreenBinding],
    *,
    width: int,
    height: int,
    layout_cls=None,
) -> Dict[str, object]:
    if layout_cls is None:
        from motrixsim.render import Layout

        layout_cls = Layout

    images: Dict[str, object] = {}
    specs = viewer_widget_layout_specs([binding.camera_name for binding in bindings], width, height)
    for binding, spec in zip(bindings, specs):
        placeholder = np.zeros((int(height), int(width), 3), dtype=np.uint8)
        image = render.create_image(placeholder)
        render.widgets.create_image_widget(image, layout=_make_layout(layout_cls, spec))
        images[binding.camera_name] = image
    return images


def update_viewer_screen_images(
    env,
    bindings: Sequence[ViewerScreenBinding],
    images: Dict[str, object],
    *,
    width: int,
    height: int,
) -> int:
    updated = 0
    for binding in bindings:
        image = images.get(binding.camera_name)
        if image is None:
            continue
        frame = env.render_frame(
            cam_id=binding.camera_id,
            width=int(width),
            height=int(height),
            cache_background=False,
        )
        image.pixels = np.ascontiguousarray(frame)
        updated += 1
    return updated
