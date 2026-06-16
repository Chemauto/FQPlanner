import unittest

import numpy as np

from serve_3dgs.backend.viewer_screens import (
    DEFAULT_VIEWER_CAMERA_NAMES,
    camera_screen_bindings,
    create_viewer_screen_images,
    update_viewer_screen_images,
    viewer_widget_layout_specs,
)


class _Camera:
    def __init__(self, name):
        self.name = name


class _Cameras:
    def __init__(self, names):
        self.cameras = [_Camera(name) for name in names]


class _Model:
    def __init__(self, names):
        self.cameras = _Cameras(names)


class _Texture:
    pixels = None


class _Render:
    def __init__(self):
        self.created_images = []
        self.widgets = _Widgets()

    def create_image(self, pixels):
        image = _Texture()
        image.pixels = pixels
        self.created_images.append(image)
        return image


class _Widgets:
    def __init__(self):
        self.created = []

    def create_image_widget(self, image, layout):
        self.created.append((image, layout))
        return object()


class _Env:
    def __init__(self):
        self.calls = []

    def render_frame(self, cam_id, width, height, cache_background=False):
        self.calls.append((cam_id, width, height, cache_background))
        return np.full((height, width, 3), cam_id, dtype=np.uint8)


class ViewerScreensTest(unittest.TestCase):
    def test_default_camera_names_are_the_four_expected_views(self):
        self.assertEqual(
            DEFAULT_VIEWER_CAMERA_NAMES,
            ("overhead_cam", "head_cam", "right_arm_cam", "left_arm_cam"),
        )

    def test_viewer_widget_layout_specs_make_four_independent_overlay_panels(self):
        specs = viewer_widget_layout_specs(DEFAULT_VIEWER_CAMERA_NAMES, width=320, height=240)

        self.assertEqual(len(specs), 4)
        self.assertEqual([(s.left, s.top, s.width, s.height) for s in specs], [
            (10, 10, 320, 240),
            (340, 10, 320, 240),
            (10, 260, 320, 240),
            (340, 260, 320, 240),
        ])

    def test_camera_screen_bindings_follow_requested_camera_order(self):
        model = _Model(["overhead_cam", "right_arm_cam", "left_arm_cam", "head_cam"])

        bindings = camera_screen_bindings(model, DEFAULT_VIEWER_CAMERA_NAMES)

        self.assertEqual([b.camera_id for b in bindings], [0, 3, 1, 2])

    def test_create_viewer_screen_images_uses_render_widgets_not_scene_geometry(self):
        model = _Model(["overhead_cam", "right_arm_cam", "left_arm_cam", "head_cam"])
        bindings = camera_screen_bindings(model, DEFAULT_VIEWER_CAMERA_NAMES)
        render = _Render()

        images = create_viewer_screen_images(render, bindings, width=4, height=3)

        self.assertEqual(len(images), 4)
        self.assertEqual(len(render.created_images), 4)
        self.assertEqual(len(render.widgets.created), 4)
        for binding in bindings:
            self.assertEqual(images[binding.camera_name].pixels.shape, (3, 4, 3))

    def test_update_viewer_screen_images_renders_each_camera_without_bg_cache(self):
        model = _Model(["overhead_cam", "right_arm_cam", "left_arm_cam", "head_cam"])
        bindings = camera_screen_bindings(model, DEFAULT_VIEWER_CAMERA_NAMES)
        images = {binding.camera_name: _Texture() for binding in bindings}
        env = _Env()

        update_viewer_screen_images(env, bindings, images, width=4, height=3)

        self.assertEqual(env.calls, [
            (0, 4, 3, False),
            (3, 4, 3, False),
            (1, 4, 3, False),
            (2, 4, 3, False),
        ])
        for binding in bindings:
            self.assertTrue(images[binding.camera_name].pixels.flags["C_CONTIGUOUS"])
            self.assertEqual(images[binding.camera_name].pixels.shape, (3, 4, 3))
            self.assertEqual(int(images[binding.camera_name].pixels[0, 0, 0]), binding.camera_id)


if __name__ == "__main__":
    unittest.main()
