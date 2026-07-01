"""
serve_alfworld/alf_env.py — ALFWorld(纯文本)后端核心

封装 ALFWorld TextWorld 环境 + 一个「语义意图 → 合法命令」解析器。
解析器是适配器的心脏:大脑说 navigate_to("countertop"),ALFWorld 要的是
`go to countertop 1`;大脑说 place("spraybottle","countertop"),ALFWorld 要的是
`move spraybottle 1 to countertop 1`。每一步用 info['admissible_commands'] 当 ground
truth 来匹配,匹配不到就如实失败(并把合法动作清单返回,便于上层报清楚)。

可独立 smoke test:
    export ALFWORLD_DATA=~/alfworld_data
    python serve_alfworld/alf_env.py
"""

from __future__ import annotations

import os
import re

import yaml
from serve_alfworld.shadow_state import ShadowState
# NOTE: `import alfworld...` is done lazily inside _get_split() so this module (and the
# pure helper repair_command below) can be imported/tested without alfworld installed.

DEFAULT_CONFIG = os.path.expanduser(
    os.environ.get("ALFWORLD_CONFIG", "~/alfworld-repo/configs/base_config.yaml")
)


# ---------------- 文本解析小工具 ----------------
_ENTITY_RE = re.compile(r"\b([a-z]+ \d+)\b")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())


def _base(name: str) -> str:
    """去掉尾部实例号:'countertop 1' -> 'countertop'。"""
    return re.sub(r"\s*\d+$", "", _norm(name))


def _entities(text: str) -> list[str]:
    """从一段观测里抽出 'name N' 实体(去重保序)。"""
    seen, out = set(), []
    for m in _ENTITY_RE.findall(text or ""):
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out


def _floorplan_id(game_file: str) -> str | None:
    """从 game 文件路径解析 AI2-THOR floorplan id。

    ALFWorld 路径里 task 目录名格式固定:
      pick_and_place_simple-AlarmClock-None-Dresser-301/trial_T2019.../game.tw-pddl
    最后那个 '-NNN' 段(301)就是 floorplan id —— 同 id = 同一套家具布局("同一个家")。
    取路径里「含 >=4 个 '-' 段且尾段是数字」的目录段的尾段(最后一个匹配为准)。
    """
    found = None
    for seg in str(game_file).split(os.sep):
        bits = seg.split("-")
        if len(bits) >= 4 and bits[-1].isdigit():
            found = bits[-1]
    return found


# 只对「操作动词」做实例号修复;绝不碰 go/open/close/examine(它们的实例号是有意的位置选择)。
_REPAIRABLE_VERBS = {"move", "put", "clean", "heat", "cool", "slice", "use", "take"}


def repair_command(command: str, admissible: list[str], holding: str | None = None) -> str:
    """用 admissible_commands 作 ground truth,纠正硬编码的物体实例号。

    master planner 常发 'move bowl 1 to cabinet 1',而机器人实际持有的是 'bowl 2'
    (auto-take 抓到的是现场实际存在的实例)→ ALFWorld 回 'Nothing happens.'。
    admissible_commands 里只会有真实存在/持有的实例,所以把命令重写成「同动词 + 同物体基名
    (按顺序)」的那条合法命令。只修操作动词,location/access 动词(go/open/close/examine)不动。
    找不到安全匹配就原样返回 → 只会帮忙,不会帮倒忙。
    """
    norm_cmd = _norm(command)
    by_norm = {_norm(c): c for c in admissible}
    if norm_cmd in by_norm:                       # 本来就合法,直接用规范化原文
        return by_norm[norm_cmd]
    toks = norm_cmd.split()
    if not toks or toks[0] not in _REPAIRABLE_VERBS:
        return command
    verb = toks[0]
    want_bases = [_base(e) for e in _entities(norm_cmd)]
    if not want_bases:
        return command
    candidates = []
    for c in admissible:
        ct = _norm(c).split()
        if ct and ct[0] == verb and [_base(e) for e in _entities(_norm(c))] == want_bases:
            candidates.append(c)
    if not candidates:
        return command
    if len(candidates) == 1:
        return candidates[0]
    # 现场有多个同类实例(如两个 bowl):优先选我们实际持有的那个
    if holding:
        held = _norm(holding)
        for c in candidates:
            ents = _entities(_norm(c))
            if ents and _norm(ents[0]) == held:
                return c
    return candidates[0]


class AlfEnv:
    """单实例、单任务的 ALFWorld 文本环境封装。"""

    def __init__(self, config_path: str = DEFAULT_CONFIG, split: str = "train",
                 rng_seed: int | None = None):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)
        self.config["env"]["type"] = "AlfredTWEnv"  # 强制纯文本,绝不触发 ai2thor
        # 500 steps: enough for ~5 full task attempts without hitting the limit.
        # Calling reset() loads a NEW game from the dataset — don't call it between tasks.
        self.config["env"]["max_steps"] = 500
        self._config_path = config_path
        self._default_split = split
        self._seed = rng_seed
        # Caches for deterministic, addressable resets (benchmark harness).
        # Built lazily per split so we can serve train + eval splits from one env.
        self._tw_cache: dict[str, object] = {}        # split -> AlfredTWEnv wrapper
        self._files_cache: dict[str, list[str]] = {}  # split -> ordered game files
        self._env = None  # active TextWorld gym env; built on first reset()/reset_to()
        self.obs: str = ""
        self.info: dict = {}
        self.task: str = ""
        self.holding: str | None = None
        self.receptacles: list[str] = []
        self._game_over: bool = False
        self._steps: int = 0  # 每发出一条命令 +1；reset 清零（Phase 0 步数指标）
        # Phase 1 持续世界：True 时世界载入后不再 re-init，且 stock quest 的 done
        # 不锁死环境（我们只借这个 game 的物理世界，自定义目标由上层/自写裁判判成功）。
        self._persistent: bool = False
        self.shadow: ShadowState = ShadowState()

    # ---------------- 数据集寻址(benchmark harness) ----------------
    def _get_split(self, split: str):
        """Return (AlfredTWEnv, ordered_game_files) for a split, building+caching once.

        Order is `sorted()` of the game-file paths (stable across runs/machines),
        then optionally deterministically shuffled by rng_seed. This is what lets the
        driver replay an IDENTICAL fixed task set at every checkpoint: same split +
        same index -> same game.
        """
        if split not in self._tw_cache:
            import alfworld.agents.environment as environment
            env_cls = environment.get_environment("AlfredTWEnv")
            tw = env_cls(self.config, train_eval=split)
            files = sorted(getattr(tw, "game_files", []) or [])
            if self._seed is not None:
                import random as _rng
                _rng.Random(self._seed).shuffle(files)
            self._tw_cache[split] = tw
            self._files_cache[split] = files
        return self._tw_cache[split], self._files_cache[split]

    def dataset_size(self, split: str | None = None) -> int:
        _, files = self._get_split(split or self._default_split)
        return len(files)

    def reset_to(self, split: str, index: int) -> dict:
        """Deterministically load one specific game by (split, sorted/seeded index).

        Forces exactly games[index] regardless of ALFWorld's internal sampler, so the
        benchmark can re-run the same held-out set every checkpoint, and walk the train
        stream by index. Re-inits the gym env on the single chosen game each call;
        per-task overhead is negligible next to the LLM planning/execution loop.
        """
        tw, files = self._get_split(split)
        if not files:
            raise RuntimeError(f"split '{split}' has no game files")
        chosen = files[index % len(files)]
        tw.game_files = [chosen]  # pristine order preserved in self._files_cache
        self._env = tw.init_env(batch_size=1)
        self._persistent = False
        return self._after_reset()

    # ---------------- 持续世界(Phase 1) ----------------
    def homes(self, split: str | None = None) -> dict[str, list[int]]:
        """按 floorplan 把一个 split 的 game 分组 → {floorplan_id: [game indices]}。

        同 floorplan = 同一套家具布局("同一个家")。一个 home 下有多个 game(不同 stock
        任务、物体摆放也不同),所以这只用来挑一个代表 game 当持续世界,不指望它们状态互通。
        """
        _, files = self._get_split(split or self._default_split)
        groups: dict[str, list[int]] = {}
        for idx, path in enumerate(files):
            fid = _floorplan_id(path)
            if fid:
                groups.setdefault(fid, []).append(idx)
        return groups

    def reset_home(self, floorplan_id: str, split: str | None = None) -> dict:
        """载入某个 home 的代表 game 作为「持续世界」,之后不再 re-init。

        与 reset_to 的区别:置 _persistent=True → 后续 stock quest 即使被顺手完成(done),
        环境也不锁死,可继续 step;成功判定交给上层自定义目标 / Phase 2 自写裁判。
        """
        split = split or self._default_split
        groups = self.homes(split)
        fid = str(floorplan_id)
        if fid not in groups:
            raise ValueError(f"floorplan '{fid}' 不存在;可用: {sorted(groups)[:20]}")
        tw, files = self._get_split(split)
        chosen = files[groups[fid][0]]  # 该 home 的第一个 game 当代表世界
        tw.game_files = [chosen]
        self._env = tw.init_env(batch_size=1)
        snap = self._after_reset()
        self._persistent = True  # 在 _after_reset(清状态)之后再置位
        snap["persistent"] = True
        snap["floorplan"] = fid
        return snap

    def move_object(self, obj: str, to_receptacle: str) -> dict:
        """测试注入:把 obj 挪到 to_receptacle,模拟「家里东西被人动了」(Phase 3 漂移测试)。

        走不计步的内部路径(_uncounted_step):这是外部干预,不该算进 agent 的任务步数。
        尽力序列:(必要时遍历位置)找到并 take obj → go 到目标 → put。仅持续模式可用,
        且假定调用时 agent 空手(任务之间注入)。
        """
        if not self._persistent:
            return {"success": False, "result": "move_object 仅持续世界(reset_home 后)可用"}
        obj_base = _base(obj)
        to_norm = _norm(to_receptacle)

        def _find(prefix: str, *needs: str) -> str | None:
            for c in self.admissible():
                cl = _norm(c)
                if cl.startswith(prefix) and all(n in cl for n in needs):
                    return c
            return None

        # 若 agent 已持有目标物体,跳过 take 直接放置(inject 在 LLM 任务未完成时会遇到此情况)
        already_holding = self.holding and _base(self.holding) == obj_base
        if not already_holding:
            take = _find("take ", obj_base)
            if not take:
                # ALFWorld go-to 命令是位置相关的：进入 cabinet/drawer 子位置后可达性缩减。
                # 优先去高连通性的开放表面（从初始位置肯定可直达），再处理封闭容器；
                # 每次导航都在上一次落脚点出发，开放表面→开放表面的连通性高，不会迷路。
                _OPEN = ("countertop", "sinkbasin", "stoveburner", "shelf",
                         "garbagecan", "toaster", "coffeemachine",
                         "diningtable", "sidetable", "sofa", "armchair", "bed")
                gos_all = [c for c in self.admissible() if _norm(c).startswith("go to ")]
                gos_open = [c for c in gos_all if any(k in _norm(c) for k in _OPEN)]
                gos_closed = [c for c in gos_all if not any(k in _norm(c) for k in _OPEN)]
                for go in gos_open + gos_closed:
                    self._uncounted_step(go)
                    take = _find("take ", obj_base)
                    if take:
                        break
                    # 目标可能在关闭的容器里:尝试打开当前可开的容器再查
                    for opn in list(self.admissible()):
                        if _norm(opn).startswith("open "):
                            self._uncounted_step(opn)
                            take = _find("take ", obj_base)
                            if take:
                                break
                    if take:
                        break
                if not take:
                    return {"success": False, "result": f"move_object: 全场未找到 '{obj}'"}
            self._uncounted_step(take)

        # 用 _pick（带 word-boundary）避免 "cabinet 1" 误中 "cabinet 14" 等
        go_target = self._pick("go to ", to_norm)
        if go_target:
            self._uncounted_step(go_target)
        put = self._pick("move ", obj_base, to_norm) or self._pick("put ", obj_base, to_norm)
        if not put:  # 目标是关着的带门容器(cabinet/drawer/fridge…) → 先 open 再放
            opn = self._pick("open ", to_norm)
            if opn:
                obs_open = self._uncounted_step(opn)
                # ALFWorld 有时 open 容器会自动放入持有物（如 open microwave 放入 plate）→ 视为成功
                if obj_base in obs_open.lower() and any(v in obs_open.lower() for v in ("move", "put")):
                    self.holding = None
                    return {"success": True, "result": obs_open, "command": opn}
                put = self._pick("move ", obj_base, to_norm) or self._pick("put ", obj_base, to_norm)
        if not put:
            return {"success": False, "result": f"move_object: 无法把 '{obj}' 放到 '{to_receptacle}'"}
        obs = self._uncounted_step(put)
        if obs.strip().lower().startswith("nothing happens"):
            return {"success": False, "result": f"move_object: put 无效({put}) → {obs}"}
        self.holding = None  # 注入结束,世界里 agent 空手
        return {"success": True, "result": obs, "command": put}

    def _uncounted_step(self, command: str) -> str:
        """执行一条命令但**不计入 _steps**、不碰 _game_over —— 仅测试注入用。"""
        obs, _scores, _dones, info = self._env.step([command])
        self.obs, self.info = obs[0], info
        return self.obs

    # ---------------- 生命周期 ----------------
    def reset(self) -> dict:
        self._persistent = False
        if self._env is None:
            tw, files = self._get_split(self._default_split)
            tw.game_files = list(files)  # full ordered list; legacy sequential cycling
            self._env = tw.init_env(batch_size=1)
        return self._after_reset()

    def _after_reset(self) -> dict:
        obs, info = self._env.reset()
        self.obs, self.info = obs[0], info
        self.task = self._parse_task(self.obs)
        self.receptacles = _entities(self.obs)
        self.holding = None
        self._game_over = False
        self._steps = 0  # 每局清零
        self.shadow = ShadowState()  # 每局/每 home 重置 shadow
        return self.snapshot()

    def _step(self, command: str) -> dict:
        # If episode already ended (max steps reached without winning), block further steps.
        if self._game_over:
            return {
                "command": command,
                "observation": self.obs,
                "done": True,
                "won": False,
                "game_over": True,
            }
        self._steps += 1  # 发出一条命令算一步（go/open/examine/take/move/clean… 都计）
        obs, _scores, dones, info = self._env.step([command])
        self.obs, self.info = obs[0], info
        done = bool(dones[0])
        game_over = done and not self.won()
        # 持续世界(Phase 1)不被 stock quest 的结束信号锁死：忽略 done，继续接受命令。
        if game_over and not self._persistent:
            self._game_over = True
        return {
            "command": command,
            "observation": self.obs,
            "done": done,
            "won": self.won(),
            "game_over": game_over,
        }

    # ---------------- 解析器(适配器核心) ----------------
    def admissible(self) -> list[str]:
        ac = self.info.get("admissible_commands")
        return ac[0] if ac else []

    def _pick(self, prefix: str, *names: str) -> str | None:
        # _norm keeps instance numbers ("drawer 5", "cabinet 2").
        # Simple substring is not enough: "cabinet 2" would match "cabinet 24".
        # For tokens that end with a digit we require a word boundary after the number
        # so "cabinet 2" matches "go to cabinet 2" but NOT "go to cabinet 24".
        # Generic names without a trailing digit (e.g. "counter") still match via
        # substring ("counter" ⊂ "countertop 1").
        wants = [_norm(n) for n in names if n]
        for c in self.admissible():
            cl = _norm(c)
            if not cl.startswith(prefix):
                continue
            if all(
                (re.search(r'\b' + re.escape(w) + r'(?=\s|$)', cl) is not None)
                if w and w[-1].isdigit()
                else (w in cl)
                for w in wants
            ):
                return c
        return None

    def resolve_navigate(self, target: str) -> str | None:
        return self._pick("go to ", target)

    def resolve_grasp(self, obj: str) -> str | None:
        return self._pick("take ", obj)

    def resolve_place(self, obj: str, target: str) -> str | None:
        return self._pick("move ", obj, target)

    # ---------------- 语义动作(给 HTTP 层调用,返回 robot_api 风格 dict) ----------------
    def navigate_to(self, target: str) -> dict:
        if self._game_over:
            return {"success": False, "result": "游戏已超时（最大步数），本轮任务失败", "won": False}
        cmd = self.resolve_navigate(target)
        if not cmd:
            return self._fail(f"没有可前往 '{target}' 的合法动作")
        r = self._step(cmd)
        if r.get("game_over"):
            return {"success": False, "result": "游戏已超时（最大步数），本轮任务失败", "won": False, "command": cmd}
        self.shadow.update(cmd, r["observation"])
        return {"success": True, "result": r["observation"], "won": r["won"], "command": cmd}

    def grasp(self, obj: str) -> dict:
        if self._game_over:
            return {"success": False, "result": "游戏已超时（最大步数），本轮任务失败", "won": False}
        cmd = self.resolve_grasp(obj)
        if not cmd:
            if self.holding:
                return self._fail(
                    f"无法抓取 '{obj}'：robot 当前已持有 '{self.holding}'，"
                    f"ALFWorld 不支持同时持有多个物体"
                )
            return self._fail(f"当前位置没有可抓取 '{obj}' 的合法动作(可能要先 go to 它所在的容器)")
        r = self._step(cmd)
        if r.get("game_over"):
            return {"success": False, "result": "游戏已超时（最大步数），本轮任务失败", "won": False, "command": cmd}
        self.holding = obj
        self.shadow.update(cmd, r["observation"])
        return {"success": True, "result": r["observation"], "won": r["won"], "command": cmd}

    def place(self, obj: str, target: str) -> dict:
        if self._game_over:
            return {"success": False, "result": "游戏已超时（最大步数），本轮任务失败", "won": False}
        cmd = self.resolve_place(obj, target)
        if not cmd:
            return self._fail(f"没有把 '{obj}' 放到 '{target}' 的合法动作(要先抓着它并 go to 目标)")
        r = self._step(cmd)
        if r.get("game_over"):
            return {"success": False, "result": "游戏已超时（最大步数），本轮任务失败", "won": False, "command": cmd}
        self.holding = None
        self.shadow.update(cmd, r["observation"])
        return {"success": True, "result": r["observation"], "won": r["won"], "command": cmd}

    def _repair_command(self, command: str) -> str:
        return repair_command(command, self.admissible(), self.holding)

    def raw(self, command: str) -> dict:
        """直接执行一条命令(给 open/heat/cool/clean/toggle 等扩展动作用)。

        先做实例修复:planner 常把持有物写死成 '<obj> 1',实际持有可能是 '<obj> 2',
        用 admissible_commands 把实例号纠正过来(只改 move/put/clean 等操作动词)。
        """
        repaired = self._repair_command(command)
        if repaired != command:
            command = repaired

        # 放置自洽兜底:move/put X to Y 若当前不可执行(agent 不在 Y),自动先导航到 Y 再放。
        # 规划骨架本应在放置前加'导航到 Y'子任务,但 search_and_grasp 会把 agent 带离去找物体,
        # 一旦 planner 省了那步导航,放置就会因'人不在目标处'而 Nothing happens。这里兜底自导航,
        # 必要时开门,使放置不依赖 planner 是否生成了独立导航子任务。
        cmd_l = _norm(command)
        if (cmd_l.startswith("move ") or cmd_l.startswith("put ")) and \
                cmd_l not in [_norm(c) for c in self.admissible()]:
            m = re.match(r"(?:move|put)\s+.+?\s+(?:in(?:to)?|on(?:to)?|to)\s+(.+)$", cmd_l)
            if m:
                recep = m.group(1).strip()
                go_target = self._pick("go to ", recep)
                if go_target:
                    nav_obs = self._step(go_target).get("observation", "")
                    self.shadow.update(go_target, nav_obs)
                    # 目标是带门容器(cabinet/drawer/fridge…)且未开 → 先开门再放
                    if not (self._pick("move ", recep) or self._pick("put ", recep)):
                        opn = self._pick("open ", recep)
                        if opn:
                            self.shadow.update(opn, self._step(opn).get("observation", ""))
                    # 导航/开门后 admissible 变了,重修实例号
                    repaired2 = self._repair_command(command)
                    if repaired2 != command:
                        command = repaired2

        r = self._step(command)
        if r.get("game_over"):
            return {"success": False, "result": "游戏已超时（最大步数），本轮任务失败", "won": False, "command": command}
        obs = r["observation"]
        success = obs != "Nothing happens."
        if success:
            cmd_lower = command.lower()
            if cmd_lower.startswith("take "):
                # "take spatula 1 from drawer 2" → holding = "spatula 1"
                m = re.match(r"take\s+(.+?)\s+from\b", cmd_lower)
                if m:
                    self.holding = m.group(1).strip()
            elif cmd_lower.startswith("move ") or cmd_lower.startswith("put "):
                self.holding = None
        self.shadow.update(command, obs)
        return {"success": success, "result": obs, "won": r["won"], "command": command}

    # ---------------- 状态视图 ----------------
    def won(self) -> bool:
        w = self.info.get("won")
        if isinstance(w, (list, tuple)):
            return bool(w[0])
        return bool(w)

    def steps(self) -> int:
        """本局至今发出的命令数（Phase 0 头条指标：步数）。"""
        return self._steps

    def snapshot(self) -> dict:
        """给 /scene_state、/reset 用的结构化视图。"""
        return {
            "task": self.task,
            "observation": self.obs,
            "holding": self.holding,
            "receptacles": self.receptacles,
            "objects_in_view": [e for e in _entities(self.obs) if e not in self.receptacles],
            "admissible_commands": self.admissible(),
            "won": self.won(),
            "steps": self._steps,
            "persistent": self._persistent,
        }

    # ---------------- 内部 ----------------
    @staticmethod
    def _parse_task(obs: str) -> str:
        m = re.search(r"your task is to:\s*(.+)", obs, flags=re.IGNORECASE)
        return m.group(1).strip() if m else ""

    def _fail(self, msg: str) -> dict:
        return {"success": False, "result": msg, "won": self.won(), "admissible_commands": self.admissible()}


# ---------------- 独立 smoke test ----------------
if __name__ == "__main__":
    env = AlfEnv()
    snap = env.reset()
    print("=== TASK ===\n ", snap["task"])
    print("\n=== OBS (前 600 字) ===\n", snap["observation"][:600])
    print("\n=== 合法动作 (前 15 条) ===")
    for c in snap["admissible_commands"][:15]:
        print("   ", c)

    # demo:用解析器走到第一个容器
    first_recep = snap["receptacles"][0] if snap["receptacles"] else None
    if first_recep:
        base_name = _base(first_recep)
        print(f"\n=== navigate_to('{base_name}') ===")
        r = env.navigate_to(base_name)
        print("  matched command:", r.get("command"))
        print("  success:", r["success"], "| won:", r["won"])
        print("  obs:", r["result"][:200])
    print("\nOK: alf_env 程序化 API 正常。")
