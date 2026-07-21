"""事后反思模块 —— demo 任务④:执行 trace → 总结误清理/漏清理/执行失败 → 生成新版 SOP。

两档(在线失败自动降级):
  结构化档(离线): 从 last_trace.json 提取事实并分类 —— 谎报成功被确认逮住 / 抓取失败重试
                  恢复 / 技能重试耗尽被跳过(漏整理) / 个人物品被挪动(误操作) → 模板化经验。
  LLM 档(在线):  事实摘要 + 既有规则 → deepseek 生成 1-3 条自然语言新经验(demo 形态)。

输出:
  · 反思报告(stdout)
  · 新版 SOP: learned_rules 追加 [v2·auto] 条目 → demo_sop_v2.yaml(不覆盖原 SOP)
"""

import json
import os
import re
import sys
import urllib.request
from datetime import date

import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))

SKILL_LABEL = {
    "clean_trash": "清理垃圾", "tidy_milk": "整理牛奶",
    "tidy_cola": "整理可乐", "tidy_penholder": "整理笔筒",
}


# ---------------- 结构化反思 ----------------

def structural_findings(trace):
    findings = []
    for s in trace.get("skills", []):
        label = SKILL_LABEL.get(s["skill"], s["skill"])
        lies = [a for a in s["attempts"] if a["exec"].get("success") and not a["verify_ok"]]
        grasp_fails = [a for a in s["attempts"]
                       if not a["exec"].get("success") and a["exec"].get("fail_stage") == "grasp"]
        if lies:
            findings.append({
                "type": "执行报告与实际不符",
                "detail": f"「{label}」执行模块报告成功,但状态确认发现未达标"
                          f"({lies[0]['verify_detail']}),重新执行后恢复",
            })
        if grasp_fails:
            recovered = s["final"] == "success"
            findings.append({
                "type": "抓取失败" + ("(重试后恢复)" if recovered else "(未恢复)"),
                "detail": f"「{label}」{grasp_fails[0]['exec'].get('fail_reason')}",
            })
        if s["final"] == "skipped_after_retries":
            findings.append({
                "type": "漏整理/漏清理",
                "detail": f"「{label}」重试 {len(s['attempts']) - 1} 次仍未达标,被跳过",
            })
    fc = trace.get("final_check", {})
    if not fc.get("protection_ok", True):
        findings.append({"type": "误操作(个人物品被挪动)",
                         "detail": "终局复核发现受保护的个人物品位置变化"})
    if not findings:
        findings.append({"type": "顺利完成", "detail": "全部技能一次通过,无异常"})
    return findings


_TEMPLATE_RULES = {
    "执行报告与实际不符": "不采信执行模块的成功报告:每个技能执行后必须重新观测并确认实际状态,未达标立即重做。",
    "抓取失败(重试后恢复)": "抓取失败(如夹爪未夹住)后重试通常有效;连续 2 次失败应跳过该物体并上报,不阻塞后续任务。",
    "漏整理/漏清理": "被跳过的技能要在任务报告中显式列出,并在下次执行前优先检查该类物体的状态与可达性。",
    "误操作(个人物品被挪动)": "执行任何技能前把个人物品列入禁动清单,终局必须复核其位置未变。",
}


def template_rules(findings):
    return [_TEMPLATE_RULES[f["type"]] for f in findings if f["type"] in _TEMPLATE_RULES]


# ---------------- LLM 反思(deepseek,失败降级) ----------------

def _api_key():
    key = os.environ.get("CLOUD_API_KEY")
    if key:
        return key
    env_path = os.path.join(_ROOT, ".env")
    if os.path.isfile(env_path):
        for line in open(env_path, encoding="utf-8"):
            m = re.match(r"\s*CLOUD_API_KEY\s*=\s*(\S+)", line)
            if m:
                return m.group(1).strip().strip('"')
    return None


def llm_rules(findings, existing_rules):
    key = _api_key()
    if not key:
        return None, "无 CLOUD_API_KEY"
    facts = "\n".join(f"- [{f['type']}] {f['detail']}" for f in findings)
    known = "\n".join(f"- {r}" for r in existing_rules)
    prompt = f"""你是机器人的「事后反思」模块。机器人刚完成一次桌面整理任务,以下是执行记录的事实摘要和既有经验规则。
请基于事实总结 1-3 条【新的】经验规则:
- 每条一句话、具体可执行、面向未来的任务执行(风格与既有规则一致)
- 不得与既有规则重复或近似
- 只基于事实,不编造未发生的情况
- 直接输出规则,每行一条,不要编号、解释或其他内容

【本次执行事实】
{facts}

【既有经验规则】
{known}"""
    req = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps({
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2, "max_tokens": 300,
        }).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            content = json.loads(r.read())["choices"][0]["message"]["content"]
        rules = [ln.strip("-• ").strip() for ln in content.strip().splitlines() if ln.strip()]
        return [r for r in rules if len(r) > 8], None
    except Exception as exc:
        return None, str(exc)


# ---------------- 新版 SOP ----------------

def write_sop_v2(sop, new_rules):
    sop2 = dict(sop)
    tag = f"[v2·auto {date.today().isoformat()}]"
    sop2["learned_rules"] = list(sop.get("learned_rules", [])) + [f"{tag} {r}" for r in new_rules]
    out = os.path.join(_HERE, "demo_sop_v2.yaml")
    with open(out, "w", encoding="utf-8") as f:
        yaml.safe_dump(sop2, f, allow_unicode=True, sort_keys=False, width=100)
    return out


def main():
    trace_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(_HERE, "last_trace.json")
    trace = json.load(open(trace_path, encoding="utf-8"))
    sop = yaml.safe_load(open(os.path.join(_HERE, "demo_sop.yaml"), encoding="utf-8"))
    existing = sop.get("learned_rules", [])

    print("=" * 62)
    print("事后反思报告(任务④)")
    print("=" * 62)
    findings = structural_findings(trace)
    for f in findings:
        print(f"  · [{f['type']}] {f['detail']}")

    rules, err = llm_rules(findings, existing)
    source = "LLM(deepseek)"
    if not rules:
        rules = template_rules(findings)
        source = f"模板档(LLM 不可用: {err})"
    # 去重(与既有规则粗匹配)
    new_rules = [r for r in rules if not any(r[:12] in ex or ex[:12] in r for ex in existing)]

    print(f"\n新增经验规则(来源: {source}):")
    if not new_rules:
        print("  (无新增——本次执行未暴露既有规则之外的问题)")
        return
    for r in new_rules:
        print(f"  + {r}")
    out = write_sop_v2(sop, new_rules)
    print(f"\n新版 SOP → {os.path.relpath(out, _ROOT)}(learned_rules {len(existing)}→{len(existing) + len(new_rules)} 条)")


if __name__ == "__main__":
    main()
