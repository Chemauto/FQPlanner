#!/usr/bin/env python3
"""bench/capture_task.py — 跑一个具体任务,存开始/任务中(连续帧)/完成的相机截图。

viewer 和截图在 macOS 同进程抢 GL 会崩,所以这里走 headless(--no-viewer)+ 截图;
截图本身就是画面,连起来就是任务全程。每个时刻存 overhead(全景)+head(机器人视角)两张。

前置:serve(:5001 headless) + master(:5000) + slaver + redis 都在跑。
用法:
    python bench/capture_task.py --task "put mug in sink"
    python bench/capture_task.py --task "put cup in stove" --cams overhead_cam,head_cam
"""
import argparse, base64, os, threading, time, uuid
import requests

SERVE = "http://127.0.0.1:5001"
MASTER = "http://127.0.0.1:5000"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "task_frames")


def shot(tag, cams):
    """存一组相机截图,文件名 <tag>_<cam>.jpg。"""
    for cam in cams:
        try:
            r = requests.post(f"{SERVE}/screenshot", json={"camera_name": cam}, timeout=60).json()
            img = r.get("image")
            if img:
                path = os.path.join(OUT, f"{tag}_{cam}.jpg")
                with open(path, "wb") as f:
                    f.write(base64.b64decode(img))
                print(f"  📸 {os.path.basename(path)}")
            else:
                print(f"  ✗ {cam} 无图: {r.get('result')}")
        except Exception as e:
            print(f"  ✗ {cam} 截图失败: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", default="put mug in sink")
    ap.add_argument("--floorplan", default="1")
    ap.add_argument("--cams", default="overhead_cam,head_cam")
    ap.add_argument("--interval", type=float, default=8.0, help="任务中每隔几秒截一帧")
    ap.add_argument("--timeout", type=float, default=300.0)
    args = ap.parse_args()
    cams = [c.strip() for c in args.cams.split(",") if c.strip()]
    os.makedirs(OUT, exist_ok=True)

    print(f"任务: {args.task}  相机: {cams}  输出: {OUT}/")
    print("== reset_home ==")
    requests.post(f"{SERVE}/reset_home", json={"floorplan_id": args.floorplan}, timeout=120)
    time.sleep(2)
    print("== 截图: 开始(00_start) ==")
    shot("00_start", cams)

    # 后台线程发任务(不阻塞主线程截图)
    requests.post(f"{SERVE}/set_task", json={"task": args.task}, timeout=30)
    tid = uuid.uuid4().hex
    threading.Thread(
        target=lambda: requests.post(
            f"{MASTER}/publish_task",
            json={"task": args.task, "refresh": True, "task_id": tid},
            timeout=args.timeout),
        daemon=True).start()
    print(f"== 已发任务 [{tid[:8]}],轮询 + 任务中连续截图 ==")

    mid, deadline = 0, time.time() + args.timeout
    while time.time() < deadline:
        try:
            st = requests.get(f"{MASTER}/api/task_status", timeout=15).json()
            if st.get("task_id") == tid and st.get("all_done"):
                break
        except Exception:
            pass
        mid += 1
        print(f"== 截图: 任务中 50_mid{mid:02d} ==")
        shot(f"50_mid{mid:02d}", cams)
        time.sleep(args.interval)

    time.sleep(2)
    print("== 截图: 完成(99_end) ==")
    shot("99_end", cams)
    won = requests.get(f"{SERVE}/success", timeout=15).json().get("won")
    print(f"\n任务 won={won}  共存 {mid + 2} 个时刻 × {len(cams)} 相机 → {OUT}/")
    print("时间线: 00_start(开始) → 50_midNN(任务中连续帧) → 99_end(完成)")


if __name__ == "__main__":
    main()
