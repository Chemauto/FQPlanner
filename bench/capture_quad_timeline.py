#!/usr/bin/env python3
"""bench/capture_quad_timeline.py — 采集任务的"四宫格时间线"给 deploy 网站按时间点回放。

四宫格 = 真机3相机(head + 左右腕)+ overhead 拼图,直接取 serve /camera/latest(它本就
渲染 2x2 带标签拼图 overhead/head/right_arm/left_arm)。每个时间点存一张四宫格 JPEG,
再写 timeline.json 清单。deploy/run.py 的 /api/timeline + /task_timeline/<f> 把它喂给网页。

两种模式:
  --task "put mug in sink"   走 master 全链路跑真任务,开始/任务中(每 interval)/完成各截四宫格
                             (需 master:5000 + slaver + redis + serve:5001)
  --drive                    仅用 serve 脚本化驱动一段导航+开柜做演示,逐步截四宫格
                             (只需 serve:5001;master/slaver 没起时用它出 demo 时间线)

用法:
    python bench/capture_quad_timeline.py --task "put mug in sink"
    python bench/capture_quad_timeline.py --drive
"""
from __future__ import annotations

import argparse
import json
import os
import threading
import time
import uuid
from datetime import datetime

import requests

SERVE = "http://127.0.0.1:5001"
MASTER = "http://127.0.0.1:5000"
OUT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "deploy", "task_timeline"))
CAM_LABELS = ["Top(overhead)", "Head", "Right wrist", "Left wrist"]


def _quad_bytes() -> bytes | None:
    """取一张四宫格拼图 JPEG(serve /camera/latest 默认就是 2x2 四相机)。"""
    try:
        r = requests.get(f"{SERVE}/camera/latest", timeout=60)
        if r.status_code == 200 and r.content:
            return r.content
    except Exception as e:
        print(f"  ✗ 取四宫格失败: {e}")
    return None


class Timeline:
    def __init__(self, task: str):
        os.makedirs(OUT, exist_ok=True)
        # 清掉旧帧,避免上次任务残留
        for f in os.listdir(OUT):
            if f.startswith("frame_") and f.endswith(".jpg"):
                os.remove(os.path.join(OUT, f))
        self.task = task
        self.frames = []

    def snap(self, label: str):
        """截一张四宫格,记进时间线。"""
        data = _quad_bytes()
        if not data:
            print(f"  ✗ [{label}] 无四宫格")
            return
        idx = len(self.frames)
        fname = f"frame_{idx:02d}.jpg"
        with open(os.path.join(OUT, fname), "wb") as fp:
            fp.write(data)
        self.frames.append({"file": fname, "label": label,
                            "t": round(time.time() - self._t0, 1)})
        print(f"  📸 {fname}  [{label}]  t={self.frames[-1]['t']}s")

    def start_clock(self):
        self._t0 = time.time()

    def write(self, won=None):
        manifest = {
            "task": self.task,
            "won": won,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "cameras": CAM_LABELS,
            "frames": self.frames,
        }
        with open(os.path.join(OUT, "timeline.json"), "w", encoding="utf-8") as fp:
            json.dump(manifest, fp, ensure_ascii=False, indent=2)
        print(f"\n时间线写入 {OUT}/timeline.json  ({len(self.frames)} 帧,won={won})")


def run_task_mode(task: str, floorplan: str, interval: float, timeout: float):
    """走 master 全链路跑真任务,任务中连续截四宫格。"""
    tl = Timeline(task)
    print(f"== reset_home ==")
    requests.post(f"{SERVE}/reset_home", json={"floorplan_id": floorplan}, timeout=180)
    time.sleep(2)
    tl.start_clock()
    tl.snap("开始")

    requests.post(f"{SERVE}/set_task", json={"task": task}, timeout=30)
    tid = uuid.uuid4().hex
    threading.Thread(target=lambda: requests.post(
        f"{MASTER}/publish_task", json={"task": task, "refresh": True, "task_id": tid},
        timeout=timeout), daemon=True).start()
    print(f"== 已发任务 [{tid[:8]}],轮询 + 任务中连续截四宫格 ==")

    mid, deadline = 0, time.time() + timeout
    while time.time() < deadline:
        try:
            st = requests.get(f"{MASTER}/api/task_status", timeout=15).json()
            if st.get("task_id") == tid and st.get("all_done"):
                break
        except Exception:
            pass
        mid += 1
        tl.snap(f"任务中 {mid}")
        time.sleep(interval)

    time.sleep(2)
    tl.snap("完成")
    won = None
    try:
        won = requests.get(f"{SERVE}/success", timeout=15).json().get("won")
    except Exception:
        pass
    tl.write(won=won)


def run_drive_mode(floorplan: str):
    """仅用 serve 脚本化驱动:reset → 逐个工作点导航 → 开一个柜,每步截四宫格。做 demo 时间线。"""
    tl = Timeline("演示:导航一圈 + 开柜(仅 serve 驱动)")
    print("== reset_home ==")
    requests.post(f"{SERVE}/reset_home", json={"floorplan_id": floorplan}, timeout=180)
    time.sleep(2)
    tl.start_clock()
    tl.snap("开始(reset 后)")

    # 逐个工作点导航,每到一处截四宫格(四相机随底盘/机械臂一起变)
    waypoints = [
        ("导航到 counter", 1.725, -1.125, -90),
        ("导航到 stove", 3.725, -1.125, -90),
        ("导航到 sink", 3.125, -1.525, 90),
    ]
    for label, x, y, yaw in waypoints:
        print(f"== {label} ==")
        try:
            requests.post(f"{SERVE}/nav", json={"x": x, "y": y, "target_yaw": yaw}, timeout=180)
        except Exception as e:
            print(f"  nav 异常: {e}")
        tl.snap(label)

    # 开一个高柜(先导航过去,否则机器人还停在上一个工作点,机身相机拍不到门开的画面;
    # 只有俯视 Top 能勉强看到,Head/腕相机会拍到无关方向)
    try:
        conts = requests.get(f"{SERVE}/containers", timeout=30).json().get("containers") or []
        if conts:
            cname = next((c["name"] for c in conts if "cab_1" in c["name"]), conts[0]["name"])
            cpos = next(c["pos"] for c in conts if c["name"] == cname)
            print(f"== 导航到 {cname} 附近 ==")
            # 柜子在 y≈-0.2 的墙上,机器人站在 y=-1.125 面朝 +y(yaw=90)才能让 head_cam 对准柜门
            # (用分割渲染验证过:yaw=-90 时 head_cam 对着相反方向的远墙,看不到任何柜子)
            requests.post(f"{SERVE}/nav", json={"x": cpos[0], "y": -1.125, "target_yaw": 90}, timeout=180)
            tl.snap(f"导航到 {cname} 附近")
            print(f"== 开柜 {cname} ==")
            requests.post(f"{SERVE}/open_container", json={"container": cname}, timeout=60)
            tl.snap(f"开柜 {cname}")
    except Exception as e:
        print(f"  开柜异常: {e}")

    tl.write(won=None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default=None, help="走 master 全链路的任务文字")
    ap.add_argument("--drive", action="store_true", help="仅 serve 脚本化演示(不需要 master)")
    ap.add_argument("--floorplan", default="1")
    ap.add_argument("--interval", type=float, default=8.0, help="任务中每隔几秒截一帧")
    ap.add_argument("--timeout", type=float, default=300.0)
    args = ap.parse_args()

    # preflight serve
    try:
        requests.get(f"{SERVE}/success", timeout=5)
    except Exception as e:
        print(f"✗ serve ({SERVE}) 不可达: {e}  先 cd serve && python main.py --no-viewer")
        return 2

    if args.drive or not args.task:
        if not args.drive and not args.task:
            print("(未给 --task,默认走 --drive 演示模式)")
        run_drive_mode(args.floorplan)
    else:
        run_task_mode(args.task, args.floorplan, args.interval, args.timeout)
    print("完成。deploy 网站『四宫格任务回放』卡片按时间点查看。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
