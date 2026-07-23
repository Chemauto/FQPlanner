"""vlm_judge.py — 任务② 多模态判断的 VLM 档(几何 mock → 真看照片)。

接 qwen-vl-max:对比 current(乱桌)与 standard(理想)两张照片 + SOP,判断当前
桌面每个物体应 clean(清理)/ organize(整理归位)/ keep(保留)。HEIC 自动转 JPG。
复用 slaver/config.yaml 的 vlm 配置(qwen-vl-max / dashscope-intl / VLM_API_KEY)。

用法: python master/sop/vlm_judge.py
"""

import base64
import glob
import json
import os
import re
import subprocess
import sys
from collections import Counter

import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
_CACHE = "/tmp/vlm_judge_cache"
sys.path.insert(0, _HERE)

ACT_LABEL = {"clean": "清理(垃圾)", "organize": "整理归位",
             "skip": "已就位·跳过", "keep": "保留·禁动"}


def _vlm_cfg():
    cfg = yaml.safe_load(open(os.path.join(_ROOT, "slaver", "config.yaml"), encoding="utf-8"))
    return (cfg.get("camera") or {}).get("vlm") or {}


def _api_key():
    for k in ("VLM_API_KEY", "CLOUD_API_KEY"):
        if os.environ.get(k):
            return os.environ[k]
    env = os.path.join(_ROOT, ".env")
    if os.path.isfile(env):
        for line in open(env, encoding="utf-8"):
            m = re.match(r"\s*VLM_API_KEY\s*=\s*(\S+)", line)
            if m:
                return m.group(1).strip().strip('"').strip("'")
    return None


def _to_jpg_b64(path):
    """HEIC/其他 → JPG(缩到 1024)→ base64。已是 jpg/png 直接编码。"""
    if path.lower().endswith((".jpg", ".jpeg", ".png")):
        jpg = path
    else:
        os.makedirs(_CACHE, exist_ok=True)
        jpg = os.path.join(_CACHE, os.path.splitext(os.path.basename(path))[0] + ".jpg")
        subprocess.run(["sips", "-s", "format", "jpeg", "-Z", "1024", path, "--out", jpg],
                       capture_output=True)
    with open(jpg, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _first_image(d):
    for ext in ("*.HEIC", "*.heic", "*.jpg", "*.jpeg", "*.png", "*.JPG"):
        g = sorted(glob.glob(os.path.join(d, ext)))
        if g:
            return g[0]
    return None


def _sop_summary(sop):
    trash = "、".join(t["type"] for t in sop["trash"])
    keep = "、".join(k["type"] for k in sop["keep_in_place"])
    std = "、".join(s["category"] for s in sop["standard_layout"])
    restock = "、".join(f"{r['item']}(标准 {r['min']} 个)" for r in sop["restock"])
    return (f"- 垃圾(clean 清理): {trash}\n- 保留(keep 禁动): {keep}\n"
            f"- 标准摆放物(organize 整理归位): {std}\n- 饮料补货: {restock}")


def judge(current_dir, standard_dir, sop):
    cur = _first_image(current_dir)
    std = _first_image(standard_dir)
    if not cur:
        return None, f"current 目录无照片: {current_dir}"
    key = _api_key()
    if not key:
        return None, "无 VLM_API_KEY"

    prompt = f"""你是机器人桌面整理的「判断大脑」。给你两张俯拍办公桌照片:
第一张【当前图】= 需要整理的乱桌;第二张【标准图】= 整理好的目标状态。以及整理规则 SOP。

【判断方法 —— 用物体间的空间关系对比,不用精确坐标】:
先描述每个可操作小物体相对【其他物体】和【环境参照(桌子边缘的黑线、盆栽等固定物)】的空间关系
(例:"三罐可乐排成一排、在盆栽右侧""牛奶盒散落在右侧""纸巾团散落在桌面中间")。
再对比【当前图】与【标准图】里同一物体的空间关系,按【关系差异】决定动作:
- skip(已就位):关系基本一致(位置和排列都没明显变化) → 不用动
- organize(整理归位):关系明显变化(散落→排整齐、挪了位置) → 需归位
- clean(清理):当前图有、标准图里【消失】了 → 垃圾(纸巾团/废纸/空瓶/压扁空盒)
- keep(保留):个人物品/工具/环境参照物,关系没变、也不属整理类别 → 不动

【最重要的一条】判断"要不要整理"看【关系变没变】,不是看"是不是标准物":
- 可乐若两图里都是"排成一排在盆栽右侧",关系没变 → skip,【绝不】判 organize
- 牛奶盒若"散落 → 排成一排",关系变了 → organize

只判桌面小物体;忽略机器人设备、机械臂、桌子、插线板、线缆、显示器。
同类物体合并成【恰好一项】,count = 当前图该类总数;散落/多出的不单独拆判成垃圾。

【SOP】
{_sop_summary(sop)}

严格只输出 JSON 数组,不要任何其他文字 / 解释 / markdown 代码块标记:
[{{"object":"中文名","count":数量,"current_rel":"当前关系(简短≤12字)","goal_rel":"标准关系(简短≤12字)","action":"clean|organize|skip|keep","reason":"简短"}}]"""

    cfg = _vlm_cfg()
    content = [
        {"type": "text", "text": prompt},
        {"type": "text", "text": "\n【当前图】(乱桌):"},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{_to_jpg_b64(cur)}"}},
    ]
    if std:
        content += [
            {"type": "text", "text": "【标准图】(目标):"},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{_to_jpg_b64(std)}"}},
        ]
    body = json.dumps({
        "model": cfg.get("model", "qwen-vl-max"),
        "messages": [{"role": "user", "content": content}],
        "max_tokens": 2000,
    }).encode()
    api_base = cfg.get("api_base", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")

    import urllib.request
    req = urllib.request.Request(
        api_base.rstrip("/") + "/chat/completions", data=body, method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            raw = json.loads(r.read())["choices"][0]["message"]["content"]
    except Exception as exc:
        return None, f"qwen-vl-max 调用失败: {exc}"

    m = re.search(r"\[.*\]", raw, re.S)
    try:
        return json.loads(m.group(0) if m else raw), None
    except Exception as exc:
        return None, f"JSON 解析失败: {exc}; 原文前 200 字: {raw[:200]}"


def main():
    from classify import load_sop
    sop = load_sop()
    cur_dir = os.path.join(_HERE, "photos", "current")
    std_dir = os.path.join(_HERE, "photos", "standard")
    print(f"current: {os.path.relpath(_first_image(cur_dir) or '无', _ROOT)}")
    print(f"standard: {os.path.relpath(_first_image(std_dir) or '无', _ROOT)}")
    print("调 qwen-vl-max 中(HEIC→JPG + 双图对比)...\n")

    result, err = judge(cur_dir, std_dir, sop)
    if not result:
        print("VLM 判断失败:", err)
        return
    print("=" * 78)
    print("VLM 关系对比判断(qwen-vl-max · 空间关系差异,不用坐标)")
    print("=" * 78)
    print(f"{'物体':10}{'判断':12}{'当前关系 → 标准关系(关系变了才动)'}")
    print("-" * 78)
    for it in result:
        cnt = f"×{it.get('count')}" if it.get("count") else ""
        rel = f"{it.get('current_rel','?')} → {it.get('goal_rel','?')}"
        print(f"{(it.get('object','')+cnt):10}{ACT_LABEL.get(it.get('action'),it.get('action','')):12}{rel}")
    print("-" * 78)
    c = Counter(it.get("action") for it in result)
    print("汇总: " + "   ".join(f"{ACT_LABEL.get(a,a)}×{n}" for a, n in c.items()))
    out = os.path.join(_HERE, "last_vlm_judge.json")
    json.dump(result, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[已存 → {os.path.relpath(out, _ROOT)}]")


if __name__ == "__main__":
    main()
