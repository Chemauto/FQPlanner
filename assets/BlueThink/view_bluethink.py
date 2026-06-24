#!/usr/bin/env python3
"""BlueThink MuJoCo model viewer."""

import mujoco
import mujoco.viewer
import time
import sys

def main():
    model = mujoco.MjModel.from_xml_path('bluethink.xml')
    data = mujoco.MjData(model)

    print(f"BlueThink Model Loaded:")
    print(f"  Bodies: {model.nbody}, Joints: {model.njnt}, Actuators: {model.nu}")
    print(f"\nJoints:")
    for i in range(model.njnt):
        name = model.joint(i).name
        lo, hi = model.jnt_range[i]
        print(f"  [{i:2d}] {name:40s} range=[{lo:+.3f}, {hi:+.3f}]")

    print(f"\nActuators:")
    for i in range(model.nu):
        name = model.actuator(i).name
        print(f"  [{i:2d}] {name}")

    print(f"\nCameras:")
    for i in range(model.ncam):
        name = model.camera(i).name
        print(f"  [{i:2d}] {name}")

    print("\nLaunching viewer...")
    print("  Left-drag: rotate | Right-drag: pan | Scroll: zoom")
    print("  Space: pause | Backspace: reset | Ctrl: drag joints")

    viewer = mujoco.viewer.launch_passive(model, data)

    try:
        while viewer.is_running():
            mujoco.mj_step(model, data)
            viewer.sync()
            time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    finally:
        viewer.close()

if __name__ == "__main__":
    main()
