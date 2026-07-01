#!/usr/bin/env python3
"""
bench/extract_traces.py — 把一次跑的「真实执行轨迹」从日志里抽成可读的逐任务 transcript。

目的:做 ground-truth 归因分析。你想知道某个任务到底发生了什么(master 计划了哪些子任务、
slaver 实际发了哪些 ALFWorld 命令、每步返回什么、最后 won 没 won、LLM 总结了什么经验),
而不是只看 LLM 自己编的那条经验。

数据来源(都是已有日志,不用重跑):
  - master/.logs/master_agent.log : 任务指令、子任务计划、每个子任务的观测(Result)、won、保存的经验
  - slaver/.log/agent.log         : slaver 实际发的每条 raw_action 命令(暴露 go vs go+open+examine 的不稳定)

用法:
    # 抽某个时间窗(比如那 10 个 learn 任务 15:47:00–15:53:30):
    python bench/extract_traces.py --since 15:47:00 --until 15:53:30
    # 抽全部 / 按子串过滤:
    python bench/extract_traces.py --grep "cd in safe"
    # 抽最后 N 个任务:
    python bench/extract_traces.py --last 10

输出:bench/traces/<序号>_<任务>.md,外加一个 index.md 汇总表。
"""

from __future__ import annotations

import argparse
import os
import re
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MASTER = os.path.join(REPO, "master", ".logs", "master_agent.log")
DEFAULT_SLAVER = os.path.join(REPO, "slaver", ".log", "agent.log")

# 行首时间戳: "2026-06-17 15:48:35,206 - INFO - "
TS_RE = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),(\d+) - (\w+) - (.*)$", re.S)


def parse_records(path: str):
    """把日志按「行首带时间戳」分组成 records;续行(无时间戳)并入上一条 message。"""
    records = []
    cur = None
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = TS_RE.match(line.rstrip("\n"))
            if m:
                if cur:
                    records.append(cur)
                ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                cur = {"ts": ts, "msg": m.group(4)}
            elif cur is not None:
                cur["msg"] += "\n" + line.rstrip("\n")
    if cur:
        records.append(cur)
    return records


def load_slaver_commands(path: str):
    """返回 [(ts, 'go to drawer 1'), ...](按时间);连续重复的同一条命令折叠成一条。"""
    if not os.path.exists(path):
        return []
    cmd_re = re.compile(r"Calling tool: '([^']+)' with arguments: (\{.*\})", re.S)
    out = []
    last = None
    for r in parse_records(path):
        m = cmd_re.search(r["msg"])
        if not m:
            continue
        tool, args = m.group(1), m.group(2)
        # 从 args 里取 command 字段(raw_action),否则用 tool+args 概括
        cmd_m = re.search(r'"command"\s*:\s*"([^"]+)"', args)
        if cmd_m:
            desc = cmd_m.group(1)
        else:
            obj_m = re.search(r'"(?:obj_name|object_name|target)"\s*:\s*"([^"]+)"', args)
            desc = f"{tool}({obj_m.group(1)})" if obj_m else tool
        if (tool, desc) == last:        # 折叠重复日志(同毫秒重复写入的那种)
            continue
        last = (tool, desc)
        out.append((r["ts"], desc))
    return out


def cmds_between(cmds, start, end):
    """取 [start, end) 窗口内的 slaver 命令描述列表。"""
    return [c for (t, c) in cmds if start <= t < (end or t)]


def build_blocks(master_recs):
    """切成逐任务 block,解析出指令/子任务(含观测)/won/经验。"""
    blocks = []
    cur = None
    for r in master_recs:
        msg = r["msg"]
        mt = re.match(r"Publishing global task: (.+)", msg)
        if mt:
            if cur:
                blocks.append(cur)
            cur = {"ts": r["ts"], "task": mt.group(1).strip(), "subtasks": [],
                   "won": None, "experience": None, "end": None}
            continue
        if cur is None:
            continue
        cur["end"] = r["ts"]
        ms = re.match(r"Sending: (.+)", msg)
        if ms:
            cur["subtasks"].append({"name": ms.group(1).strip(), "ts": r["ts"],
                                    "result": None, "status": None})
            continue
        if msg.startswith("Subtask:"):
            name = msg.split("\n", 1)[0][len("Subtask:"):].strip()
            res = re.search(r"Result:\s*(.*?)\nStatus:\s*(\w+)", msg, re.S)
            for st in reversed(cur["subtasks"]):       # 回填最近一个同名子任务
                if st["name"] == name and st["result"] is None:
                    if res:
                        st["result"] = res.group(1).strip()
                        st["status"] = res.group(2).strip()
                    break
            continue
        mw = re.search(r"\[AutoLearn\] won=(True|False)", msg)
        if mw:
            cur["won"] = (mw.group(1) == "True")
            continue
        me = re.search(r"\[Experience\] Saved \w+ to ([\w.]+): (.+)", msg)
        if me:
            cur["experience"] = f"({me.group(1)}) {me.group(2).strip()}"
    if cur:
        blocks.append(cur)
    return blocks


def render(idx, b, slaver_cmds):
    lines = [f"# [{idx}] {b['task']}", ""]
    won = b["won"]
    lines.append(f"- 结果(won): **{won}**" + (" ✅" if won else " ❌" if won is False else " (未知)"))
    lines.append(f"- 开始: {b['ts']:%H:%M:%S}   子任务数: {len(b['subtasks'])}")
    lines.append(f"- LLM 总结的经验: {b['experience'] or '(无)'}")
    lines.append("\n## 逐子任务(master 计划 → slaver 实际命令 → 观测)\n")
    for i, st in enumerate(b["subtasks"]):
        nxt = b["subtasks"][i + 1]["ts"] if i + 1 < len(b["subtasks"]) else b["end"]
        cmds = cmds_between(slaver_cmds, st["ts"], nxt)
        flag = {"success": "✓", "navigated": "→", "failure": "✗",
                "exception": "✗", "timeout": "✗"}.get(st["status"], "?")
        lines.append(f"### {flag} 子任务 {i + 1}: {st['name']}  [{st['status']}]")
        lines.append(f"- slaver 实际命令: {' | '.join(cmds) if cmds else '(日志无对应命令)'}")
        lines.append(f"- 观测(Result): {st['result'] or '(无)'}")
        lines.append("")
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--master-log", default=DEFAULT_MASTER)
    p.add_argument("--slaver-log", default=DEFAULT_SLAVER)
    p.add_argument("--since", default=None, help="HH:MM:SS,只要开始时间 >= 它的任务")
    p.add_argument("--until", default=None, help="HH:MM:SS,只要开始时间 <= 它的任务")
    p.add_argument("--grep", default=None, help="只要任务指令含该子串")
    p.add_argument("--last", type=int, default=None, help="只取最后 N 个任务")
    p.add_argument("--out-dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "traces"))
    args = p.parse_args()

    print(f"解析 master 日志: {args.master_log}")
    blocks = build_blocks(parse_records(args.master_log))
    print(f"  共 {len(blocks)} 个任务 block")
    print(f"解析 slaver 日志(折叠重复): {args.slaver_log}")
    slaver_cmds = load_slaver_commands(args.slaver_log)
    print(f"  共 {len(slaver_cmds)} 条去重命令")

    def tod(b):  # time-of-day 比较
        return b["ts"].strftime("%H:%M:%S")
    sel = blocks
    if args.since:
        sel = [b for b in sel if tod(b) >= args.since]
    if args.until:
        sel = [b for b in sel if tod(b) <= args.until]
    if args.grep:
        sel = [b for b in sel if args.grep.lower() in b["task"].lower()]
    if args.last:
        sel = sel[-args.last:]

    os.makedirs(args.out_dir, exist_ok=True)
    index = ["# 轨迹索引\n", "| # | 任务 | won | 子任务 | LLM经验 |", "|---|---|---|---|---|"]
    for i, b in enumerate(sel, 1):
        md = render(i, b, slaver_cmds)
        safe = re.sub(r"[^\w]+", "_", b["task"]).strip("_")[:40]
        fn = os.path.join(args.out_dir, f"{i:02d}_{safe}.md")
        with open(fn, "w", encoding="utf-8") as f:
            f.write(md)
        won = "✅" if b["won"] else ("❌" if b["won"] is False else "?")
        index.append(f"| {i} | {b['task']} | {won} | {len(b['subtasks'])} | {(b['experience'] or '')[:50]} |")
    with open(os.path.join(args.out_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(index) + "\n")

    print(f"\n✓ 写出 {len(sel)} 个 transcript → {args.out_dir}/")
    print(f"  先看 {args.out_dir}/index.md")


if __name__ == "__main__":
    main()
