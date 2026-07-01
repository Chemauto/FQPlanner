#!/usr/bin/env python3
"""
bench/run_curve.py — 经验学习曲线 driver(ALFWorld 后端)

回答的问题:机器人「总结经验」的功能,会不会随着学到的任务越来越多,
逐步提升任务成功率(success rate / ALFRED 的 won 信号)?

产出两条曲线(X = 已学习的训练任务数):
  - sr_heldout : 在 valid_unseen 留出集上、只读冻结经验测得的 SR —— 真·泛化(头条指标)
  - sr_sameset : 在「训练用过的同一批任务」子集上测得的 SR —— 含背答案成分的上界 / sanity check

每个 checkpoint 的评测都是「冻结」的:评测任务跑完后把经验库还原,
保证 N 个评测任务看到的是同一份经验快照 E_k,自己产生的经验不会泄漏给后面的评测任务。
只有「学习相」(走 train 流的那一段)才真正把经验写进 master/memory/skills/。

依赖:requests。前置服务见 bench/README.md(redis + master:5000 + slaver + serve_alfworld:5301)。
关键:跑之前把 master/config.yaml 的 experience.exploration_rate 调低(如 0.1),否则经验基本被忽略,曲线是平的。
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
import uuid
from datetime import datetime

import requests

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SKILLS_DIR = os.path.join(REPO_ROOT, "master", "memory", "skills")


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


# ───────────────────────── 经验库快照 / 还原(冻结评测用) ─────────────────────────

def snapshot_skills(skills_dir: str) -> dict[str, str]:
    """把经验库所有 .md 读进内存。评测前调用。"""
    snap: dict[str, str] = {}
    if os.path.isdir(skills_dir):
        for fn in os.listdir(skills_dir):
            if fn.endswith(".md"):
                with open(os.path.join(skills_dir, fn), encoding="utf-8") as f:
                    snap[fn] = f.read()
    return snap


def restore_skills(skills_dir: str, snap: dict[str, str]) -> None:
    """把经验库还原到快照状态:删掉评测期间新建的 .md、重写快照内容。"""
    os.makedirs(skills_dir, exist_ok=True)
    for fn in os.listdir(skills_dir):
        if fn.endswith(".md") and fn not in snap:
            os.remove(os.path.join(skills_dir, fn))
    for fn, content in snap.items():
        with open(os.path.join(skills_dir, fn), "w", encoding="utf-8") as f:
            f.write(content)


def backup_and_clear_skills(skills_dir: str) -> str:
    """把现有经验库备份到带时间戳的目录后清空 .md → 真·零经验基线(非破坏,可恢复)。
    同时清空 location_memory.json（与 skills/ 同级），确保两套记忆一并重置。
    """
    import shutil
    os.makedirs(skills_dir, exist_ok=True)
    backup = f"{skills_dir.rstrip('/').rstrip(os.sep)}_backup_{datetime.now():%Y%m%d_%H%M%S}"
    shutil.copytree(skills_dir, backup)
    for fn in os.listdir(skills_dir):
        if fn.endswith(".md"):
            os.remove(os.path.join(skills_dir, fn))
    # location_memory.json 与 skills/ 同级
    loc_file = os.path.join(os.path.dirname(skills_dir), "location_memory.json")
    if os.path.exists(loc_file):
        shutil.copy2(loc_file, backup)          # 一并备份
        os.remove(loc_file)                     # 清空
    return backup


# ───────────────────────────────── 单个任务执行 ─────────────────────────────────

class Driver:
    def __init__(self, args):
        self.master = args.master.rstrip("/")
        self.backend = args.backend.rstrip("/")
        self.seed = args.seed
        self.poll = args.poll
        self.task_timeout = args.task_timeout
        self.skills_dir = args.skills_dir

    def backend_reset_to(self, split: str, index: int) -> str:
        """确定性载入 (split, index) 指定的那个 game,返回任务文本。"""
        r = requests.post(
            f"{self.backend}/reset",
            json={"split": split, "index": index, "seed": self.seed},
            timeout=120,
        )
        r.raise_for_status()
        return (r.json().get("result") or {}).get("task", "") or ""

    def backend_won(self) -> bool:
        """读后端内置成功裁判(ALFWorld won = ALFRED success)。"""
        r = requests.get(f"{self.backend}/success", timeout=30)
        r.raise_for_status()
        return bool(r.json().get("won"))

    def run_one_task(self, split: str, index: int) -> bool:
        """载入指定 game → 发给 master → 轮询到结束 → 读 won。任何异常都记为失败。"""
        try:
            task_text = self.backend_reset_to(split, index)
        except Exception as e:
            log(f"  ! reset_to({split},{index}) 失败: {e}")
            return False
        if not task_text:
            log(f"  ! {split}[{index}] 没解析出任务文本,记为失败")
            return False

        tid = uuid.uuid4().hex
        try:
            # publish_task 同步规划后台执行;POST 返回时 current_task_id 已置为 tid
            pr = requests.post(
                f"{self.master}/publish_task",
                json={"task": task_text, "refresh": True, "task_id": tid},
                timeout=self.task_timeout,
            )
            if pr.status_code != 200:
                log(f"  ! publish 失败({pr.status_code}),记为失败: {pr.text[:160]}")
                return False
        except Exception as e:
            log(f"  ! publish 异常,记为失败: {e}")
            return False

        # 轮询直到「这个 task_id 的任务 all_done」或超时
        deadline = time.time() + self.task_timeout
        while time.time() < deadline:
            try:
                st = requests.get(f"{self.master}/api/task_status", timeout=15).json()
            except Exception:
                time.sleep(self.poll)
                continue
            if st.get("task_id") == tid and st.get("all_done"):
                break
            time.sleep(self.poll)
        else:
            log(f"  ! task {tid[:8]} 超时({self.task_timeout}s),记为失败")
            # 发下一个任务时 master 会用 _dispatch_token 作废这个 stale dispatch

        try:
            return self.backend_won()
        except Exception as e:
            log(f"  ! 读 won 失败,记为失败: {e}")
            return False

    # ───────────────────────────── 评测相 / 学习相 ─────────────────────────────

    def eval_split(self, split: str, n: int, label: str) -> float:
        """冻结评测:每个任务跑完后还原经验库,保证整批看到同一份经验快照。"""
        wins = 0
        for i in range(n):
            snap = snapshot_skills(self.skills_dir)
            won = self.run_one_task(split, i)
            restore_skills(self.skills_dir, snap)  # 丢弃本任务写入 → 真冻结
            wins += int(won)
            log(f"  [{label}] {i + 1}/{n}  {split}[{i}]  won={won}  累计SR={wins / (i + 1):.3f}")
        return wins / n if n else 0.0

    def learn_chunk(self, split: str, start: int, count: int) -> None:
        """学习相:走 train 流,auto_learn 把经验写进 skills/(不还原)。"""
        for i in range(start, start + count):
            won = self.run_one_task(split, i)
            log(f"  [learn] {split}[{i}]  won={won}  (经验已写入)")


# ───────────────────────────────────── 主流程 ─────────────────────────────────────

def preflight(d: Driver, args) -> None:
    """跑之前确认两个服务在线、split 够大。"""
    try:
        requests.get(f"{d.master}/api/task_status", timeout=10)
    except Exception as e:
        sys.exit(f"✗ master 不可达 ({d.master}): {e}\n  先起 redis + master + slaver。")
    # exploration_rate 太高 = 经验被大量忽略,曲线会平 → 直接拦掉这个最致命的坑
    try:
        er = requests.get(f"{d.master}/api/exploration_rate", timeout=10).json().get("exploration_rate")
    except Exception:
        er = None
    if er is None:
        log("⚠ 读不到 master 的 exploration_rate(老版本 master?);请确认起 master 前已 export EXPLORATION_RATE=0.1")
    elif er > args.max_exploration:
        sys.exit(f"✗ master exploration_rate={er} > {args.max_exploration}:经验会被大量忽略,曲线会是平的。\n"
                 f"  起 master 前 `export EXPLORATION_RATE=0.1`,或改 master/config.yaml 后重启。")
    else:
        log(f"✓ exploration_rate={er}(≤ {args.max_exploration})")
    for split, need in [(args.train_split, max(args.n_train, args.n_sameset)),
                        (args.eval_split, args.n_eval)]:
        try:
            info = requests.get(f"{d.backend}/dataset_info", params={"split": split}, timeout=60).json()
        except Exception as e:
            sys.exit(f"✗ 后端 {d.backend} 不可达或 /dataset_info 出错: {e}")
        size = info.get("size", 0)
        if size < need:
            sys.exit(f"✗ split '{split}' 只有 {size} 个 game,但需要 {need} 个。调小对应 --n-* 参数。")
        # 后端 env 在首个 /reset 前已被 main.py 急切构造,其 seed 决定 index→game 映射。
        # 若与 driver --seed 不一致,固定任务集就不固定 —— 直接拦掉这个静默陷阱。
        backend_seed = info.get("seed")
        if backend_seed is not None and int(backend_seed) != int(args.seed):
            sys.exit(f"✗ seed 不一致:后端={backend_seed} vs driver --seed={args.seed}。\n"
                     f"  用 `python serve_alfworld/main.py --game {args.seed}` 起后端,或设 ALFWORLD_SEED={args.seed}。")
        log(f"✓ split '{split}': {size} games(需要 {need}),seed={backend_seed}")


def main():
    p = argparse.ArgumentParser(description="ALFWorld 经验学习曲线 driver")
    p.add_argument("--master", default="http://127.0.0.1:5000")
    p.add_argument("--backend", default="http://127.0.0.1:5301")
    p.add_argument("--skills-dir", default=DEFAULT_SKILLS_DIR,
                   help="经验库目录(冻结评测会快照/还原它)")
    p.add_argument("--train-split", default="train")
    p.add_argument("--eval-split", default="eval_out_of_distribution",
                   help="留出测试集(valid_unseen)")
    p.add_argument("--seed", type=int, default=int(os.environ.get("ALFWORLD_SEED", 0)),
                   help="固定 game 排序 → 可复现固定任务集;默认取环境变量 ALFWORLD_SEED(否则 0)")
    p.add_argument("--n-train", type=int, default=None, help="训练流总任务数")
    p.add_argument("--chunk", type=int, default=None, help="每个 checkpoint 之间学习多少个新任务")
    p.add_argument("--n-eval", type=int, default=None, help="每次留出评测的任务数")
    p.add_argument("--n-sameset", type=int, default=None, help="每次同集(上界)评测的任务数")
    p.add_argument("--poll", type=float, default=2.0, help="轮询 task_status 的间隔秒")
    p.add_argument("--task-timeout", type=float, default=300.0, help="单任务最长等待秒")
    p.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                 "curve_results.csv"))
    p.add_argument("--smoke", action="store_true",
                   help="烟雾预设:小 N 跑通全链路(n_train=10,chunk=10,n_eval=8,n_sameset=8)")
    p.add_argument("--resume", action="store_true",
                   help="从已有 CSV 最后一个 checkpoint 之后继续(沿用当前经验库)")
    p.add_argument("--reset-experience", action="store_true",
                   help="开跑前备份并清空经验库 → 真·零经验基线(与 --resume 互斥)")
    p.add_argument("--max-exploration", type=float, default=0.3,
                   help="master exploration_rate 高于此值则拒跑(防止忘了调低、白跑出平曲线)")
    p.add_argument("--dry-run", action="store_true", help="只打印计划与总任务数,不连服务")
    p.add_argument("--yes", action="store_true", help="跳过开跑前确认")
    args = p.parse_args()

    if args.resume and args.reset_experience:
        sys.exit("✗ --resume 与 --reset-experience 互斥。")
    # --smoke 只填没显式给的 N(显式参数永远优先)
    base = (dict(n_train=10, chunk=10, n_eval=8, n_sameset=8) if args.smoke
            else dict(n_train=20, chunk=10, n_eval=15, n_sameset=15))
    for key, val in base.items():
        if getattr(args, key) is None:
            setattr(args, key, val)

    n_checkpoints = args.n_train // args.chunk + 1  # 含 checkpoint 0(基线)
    eval_runs = n_checkpoints * (args.n_eval + args.n_sameset)
    total_runs = args.n_train + eval_runs

    log("=" * 64)
    log(f"训练流: {args.train_split}  n_train={args.n_train}  chunk={args.chunk}")
    log(f"留出集: {args.eval_split}  n_eval={args.n_eval}   同集: n_sameset={args.n_sameset}")
    log(f"checkpoints={n_checkpoints}(含基线)  seed={args.seed}")
    log(f"总任务执行次数 ≈ {total_runs}  (学习 {args.n_train} + 评测 {eval_runs})")
    log(f"  每次执行 = 一整轮 LLM 规划+slaver 执行;请据此估算 token/时间")
    log(f"输出 CSV: {args.out}")
    log("=" * 64)

    if args.dry_run:
        log("dry-run:不连服务,退出。")
        return
    if not args.yes:
        if input("开跑?(y/N) ").strip().lower() not in ("y", "yes"):
            log("已取消。")
            return

    d = Driver(args)
    preflight(d, args)

    # 真·零经验基线:把现有经验库备份后清空
    if args.reset_experience:
        backup = backup_and_clear_skills(args.skills_dir)
        log(f"已备份经验库 → {backup} 并清空,从零经验开始")

    # CSV 增量写,崩了也保住已有结果
    fieldnames = ["checkpoint", "trained_tasks", "sr_heldout", "sr_sameset",
                  "n_eval", "n_sameset", "timestamp"]
    start_trained, start_k, resumed = 0, 0, False
    if args.resume and os.path.exists(args.out):
        with open(args.out, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if rows:
            start_k = int(rows[-1]["checkpoint"])
            start_trained = int(rows[-1]["trained_tasks"])
            resumed = True
            log(f"resume:接续 CSV,最后 checkpoint={start_k} 已学={start_trained};"
                f"经验库沿用当前 skills/(假定它反映了这 {start_trained} 个任务的学习)")
    if not resumed:
        with open(args.out, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=fieldnames).writeheader()

    def record(k: int, trained: int) -> None:
        log(f"── checkpoint {k}:已学 {trained} 个任务 → 冻结评测 ──")
        sr_held = d.eval_split(args.eval_split, args.n_eval, "heldout")
        sr_same = d.eval_split(args.train_split, args.n_sameset, "sameset")
        row = {"checkpoint": k, "trained_tasks": trained,
               "sr_heldout": f"{sr_held:.4f}", "sr_sameset": f"{sr_same:.4f}",
               "n_eval": args.n_eval, "n_sameset": args.n_sameset,
               "timestamp": datetime.now().isoformat(timespec="seconds")}
        with open(args.out, "a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=fieldnames).writerow(row)
        log(f"✓ checkpoint {k}: SR_heldout={sr_held:.3f}  SR_sameset={sr_same:.3f}")

    trained, k = start_trained, start_k
    if not resumed:
        record(0, trained)  # 基线:还没学任何东西(trained=0)
    while trained < args.n_train:
        count = min(args.chunk, args.n_train - trained)
        log(f"── 学习相:train[{trained}:{trained + count}] (写经验) ──")
        d.learn_chunk(args.train_split, trained, count)
        trained += count
        k += 1
        record(k, trained)

    log(f"完成。CSV → {args.out}")
    log(f"画图: python bench/plot_curve.py --csv {args.out}")


if __name__ == "__main__":
    main()
