# Per-Home 学习测试台 — 实现交接 Spec

> 目标读者:实现这份 spec 的 Claude Code（或工程师）。
> 写这份 spec 的人已读过现有代码，下面的文件名/函数名/行为都是**当前真实状态**。
> 按 **Phase 0 → 3 顺序实现**，每个 Phase 有独立验收标准；**Phase 0 跑出正信号前，不要碰 Phase 1+**。

---

## 0. 背景与目标（必读，决定所有设计取舍）

这是一个"具身大脑"系统：master(LLM 规划, :5000) 把任务拆成子任务 → slaver 执行 →
`robot_api` → 可换后端。当前文本后端是 ALFWorld（`serve_alfworld/`, :5301）。

**产品目标**：机器人"住在同一个家"，随着在这个家干的活儿变多，**完成任务越来越快**
（找东西越来越省步数），而成功率保持。这跟 ALFRED 原 benchmark 的设计**相反**——
ALFRED 每个 episode 换新房间、重随机物体，刻意测"泛化/忘掉房间"；我们要测"记住这个家/适应"。

**两条必须贯穿全程的约束**：

1. **步数（step）是头条指标**，不是成功率。成功率会很快触顶；用户感知的"会学习"=**步数下降**。
2. **未来要上视觉/真机，那时没有 `won` oracle。** 所以凡是"判断成功"的逻辑，现在就要
   建成"**不依赖后端 `won`、自己从观测+动作流算**"的形态，用文本阶段还在的 `won` 来**校准它**。
   `won` 的角色从"裁判"翻转成"给我们的自写裁判打分的人"。

### 现有代码地图（grounding，别重复造轮子）

| 位置 | 现状 |
|---|---|
| `serve_alfworld/alf_env.py` `AlfEnv` | 单实例文本环境。`_step(cmd)` 是**所有**命令的唯一咽喉（navigate_to/grasp/place/raw 都走它）。`snapshot()` 返回 task/observation/holding/receptacles/objects_in_view/admissible_commands/won。`reset_to(split,index)` 确定性载入第 index 个 game。**已 track `self.holding`**。**没有步数计数器。** |
| `serve_alfworld/server.py` | Flask :5301。`GET /success` → `{"won":...}`。`GET /scene_state` → `snapshot()`。`POST /reset` 支持 `{split,index,seed}`。 |
| `bench/run_curve.py` `Driver` | `run_one_task(split,index)`：reset→publish 给 master→轮询 task_status 到 all_done→读 `/success` 的 won。**只读 won，不读步数。** |
| `bench/run_once.py` | 复用 `Driver`，`--no-freeze` 让经验在任务间**累积**（不还原 skills/）。 |
| `master/agents/agent.py` `auto_learn` | 任务结束自动读 won、LLM 总结经验写进 `master/memory/skills/multi_step.md`。 |
| `master/agents/planner.py` `forward()` | 规划时把 `scene_data`(/scene) + `experiences` 注进 prompt。ALFWorld 分支在 L76-119。 |

### 必须先核实的风险（开工前 30 分钟做掉）

- **R1 环境**：alfworld 装在专用 conda env（如 `alfworld`），`FQPlanner` env import 不了。所有
  涉及 `serve_alfworld` 的测试必须在 alfworld env 跑，且**改完要重启 :5301**。
- **R2 exploration_rate**：master 默认 `0.8`=忽略 80% 经验，会让步数曲线**平**。跑任何记忆实验前
  `export EXPLORATION_RATE=0.1`。（driver preflight 会拦 >0.3，但自己也要记得。）
- **R3 观测可解析性（gates Phase 2/3）**：影子状态靠解析 observation 文本。开工前先 dump 一批真实
  观测，确认这些模式稳定存在：`"On the X, you see ..."` / `"You clean the X"` / `"You heat the X"` /
  `"You cool the X"` / `"You put/move X ... to Y"` / take 成功句式。解析质量 = Phase 2/3 的上限。
- **R4 持续世界可行性（gates Phase 1）**：每个 ALFWorld game 内置**一个** quest，`info['won']` 是它。
  `alf_env._step` 里 `done` 触发 `_game_over` 后**会拦掉后续命令**。要在一个 game 里连续跑多个自定义
  目标，**必须让世界在 stock quest 完成后还能继续 step**。先验证 TextWorld 是否允许（很可能要：忽略
  stock `done`、不进 `_game_over`，改用自写裁判判我们自己的目标）。

---

## Phase 0 — 步数埋点 + 同 game 重复跑（最小冒烟测试）★先做这个★

**问题**：记忆机制能不能让**同一个任务重复跑**时步数下降？这是"机制 work 吗"的地板。
通不过，后面更难的都别想。

### 改动

**(a) `serve_alfworld/alf_env.py` 加步数计数器**
- `__init__` 加 `self._steps = 0`。
- `_after_reset()` 里 `self._steps = 0`（每局清零）。
- `_step(command)`：在真正调用 `self._env.step([command])` **之前**（即 `_game_over` 守卫之后）
  `self._steps += 1`。即"发出一条命令算一步"。go/open/examine/take/move/clean… 每条都计。
- `snapshot()` 增加 `"steps": self._steps`。
- 加只读属性/方法 `def steps(self) -> int: return self._steps`。

**(b) `serve_alfworld/server.py` 暴露步数**
- `GET /success` 改成 `{"won": env.won(), "steps": env.steps()}`。

**(c) `bench/run_repeat.py`（新文件，复用 Driver）**
- 用 `from run_curve import Driver, backup_and_clear_skills, log`。
- 参数：`--split`(默认 train) `--index`(单个 game) `--repeats N`(默认 8) `--reset-experience`。
- `Driver.run_one_task` 当前只返回 won；扩展或旁路它，让每跑完一次**也读 `/success` 的 steps**。
  （最小改：复制 `run_one_task` 成 `run_one_task_with_steps` 返回 `(won, steps)`，或在循环里
  publish 后轮询完直接自己 `GET {backend}/success` 拿 `{won,steps}`。）
- 循环 `for k in range(repeats)`：**同一个 index** 反复 `run_one_task_with_steps`，
  **不快照/不还原 skills**（经验累积）。记录 `(k, won, steps)` 写 CSV `bench/repeat_results.csv`。
- 跑前若 `--reset-experience`：`backup_and_clear_skills` 清空经验库 → 真零记忆起步。

### 运行手册
```
# 后端（alfworld env，固定 seed）
export ALFWORLD_SEED=0 ALFWORLD_DATA=~/alfworld_data ALFWORLD_CONFIG=~/alfworld-repo/configs/base_config.yaml
python serve_alfworld/main.py            # :5301（改完务必重启）
redis-server
export EXPLORATION_RATE=0.1               # ★关键，否则曲线平
python master/run.py                      # :5000
python slaver/run.py
# 选一个搜索重的任务（clean&place 之类，搜索步数多 → 提速空间大）
python bench/run_repeat.py --index <i> --repeats 8 --reset-experience --yes
```

### 验收标准
- 选 1~3 个搜索重的 game。在 `EXPLORATION_RATE=0.1` 下：
  **steps(run 8) 明显 < steps(run 1)，且 won 保持 True。**
- 反例对照（强烈建议）：把 `EXPLORATION_RATE=0.9` 再跑一遍 → 步数应**不降**（证明降是记忆带来的，
  不是别的）。
- 产出：`bench/repeat_results.csv`（列 `run_k, won, steps`）+ 一张 steps-vs-run 折线（可加到
  `bench/plot_curve.py` 或单写）。

> ⚠ 已知局限（写进结论，别过度声称）：同 game 重复 = 同一批实例，当前 `save_experience` 写的
> 实例级经验（如"spatula 在 drawer 3"）在这里**正好够用**，所以 Phase 0 通过**不代表**经验能跨家务/
> 跨家迁移。它只证明"捕获→检索→应用→变快"这条管线通。跨任务/跨家的真证据在 Phase 3。

---

## Phase 1 — 持续的"家"（一个世界，多个任务，状态延续）

**问题**：ALFWorld 同 floorplan 下不同任务会**重随机物体位置**（已核实：同 floorplan 家具一致，
但物体摆放只有约 1/5 重合）。所以"同一个家、东西停在上次放的地方"**stock 不送，要自己建**。

**设计（推荐 1a：单世界 + 自定义目标序列）**：选一个 game 当"家的世界"，**载入后不再 re-init**，
在这个持续世界上连续派多个目标；物体状态自然延续（你 task1 把 mug 放台上，task2 它还在台上）。

### 改动 `serve_alfworld/alf_env.py`
- **floorplan 寻址**：game 文件路径尾部 `-NNN` 是 floorplan id。加：
  - `homes() -> dict[str, list[int]]`：扫 `self._files_cache[split]`，按 floorplan 分组 → {id: [indices]}。
  - `reset_home(floorplan_id)`：载入该 home 的一个代表 game 作为持续世界（沿用 `reset_to` 的载入逻辑）。
- **持续世界**：加状态位 `self._persistent = True/False`。持续模式下：
  - 后续"换任务"**不调 `init_env`/`reset`**，世界 state 保留。
  - **不因 stock quest 的 `done` 进 `_game_over`**（见 R4）。成功判定改用 Phase 2 的自写裁判。
- **挪物体注入（drift 测试用）**：加 `move_object(obj, to_receptacle)`，直接发对应 ALFWorld 命令把
  物体挪走（模拟"家里东西被人动了"），用于后面测"belief 失效→重搜→更新"。

### 改动 `serve_alfworld/server.py`
- `GET /homes` → `homes()`。
- `POST /reset_home {floorplan_id}` → `reset_home(...)`。
- `POST /inject_move {obj, to}` → `move_object(...)`（仅持续模式）。

### 验收
- `POST /reset_home` 后连发 2 个动作序列，确认**世界状态延续**（task1 放下的物体，task2 的
  observation 里还在原地），且能继续 step（不被 stock done 拦）。

---

## Phase 2 — 自写裁判（影子状态），用 `won` 校准

**问题**：自定义任务没有 stock `won`；而且未来上真机本就没 oracle。要"自己判成功"。

**设计**：维护一份**影子符号状态**，全靠"命令 + 观测"更新（绝不依赖特权 facts），
目标=该状态上的谓词。用文本阶段还在的 `won` **量这个裁判准不准**。

### 新模块 `serve_alfworld/world_state.py`
- `ShadowState`：
  - `holding: str|None`（迁移现有逻辑）。
  - `locations: dict[obj -> receptacle]`：解析 `"On the X you see a/an Y..."` 和 `"You put/move Y to X"`
    更新。
  - `latent: dict[obj -> set]`：解析 `"You clean the Y"`→加 `clean`；`"You heat the Y"`→`hot`（清 `cold`）；
    `"You cool the Y"`→`cold`（清 `hot`）。**这三个都只能靠 provenance（动作记录），不靠"看"——理由见下方
    「何时靠看、何时靠记得」（clean 尤其：上了视觉也不许改成靠看）。**
  - 每个 latent 条目带 `last_changed_step`（衰减/有效窗用；产品里热会凉，benchmark 里 heat→立即 place
    所以窗很短）。
  - `update(command, observation)`：在 `alf_env._step` 之后调用一次。
- `Goal` 谓词 + `judge(goal, state) -> bool`，例：
  `cool_and_place(mug, coffeemachine)` = `"cold" in latent[mug]` AND `locations[mug]=="coffeemachine"`。

### 何时靠"看"、何时靠"记得"（verify 判据；迁视觉时尤其别搞错）

判据**不是**"这个状态看不看得见"，而是**"感知能不能可靠测量这个谓词的真实定义"**。看得见 ≠ 测得准。

| 谓词 | 真实定义 | 文本阶段 | 迁视觉后 |
|---|---|---|---|
| 位置 / open / sliced | 在哪 / 开没开 / 切没切 | provenance + 观测 | **可迁到"看"**（视觉能可靠测量它） |
| **clean** | **"被洗过"（一个过程）**，不是"看起来干净" | provenance | **仍靠记得**——看起来干净 ≠ 真干净，视觉是不可靠代理 |
| hot / cold | 温度 | provenance | **仍靠记得**（视觉根本测不到，除非加红外测温） |

- **clean 永不因为上了视觉就改成"靠看"。** 它的目标定义是"洗过"，视觉测的是"外观"，两者不是一回事。
- 一个有用的不对称：视觉能**证伪** clean（明显脏 → 一定没洗净，哪怕 provenance 说洗过，比如洗完又沾了
  酱），可当"provenance 失效、需重洗"的触发器；但视觉**不能证实** clean。**对 clean，视觉只做单向 refute，
  永不做 confirm。**

### 校准（关键交付）
- `bench/judge_accuracy.py`：跑一批 **stock** 任务（有真 `won`），每个任务结束同时算**自写裁判**结果，
  报告 **judge-vs-won 一致率**，并**按谓词类型**拆开（location / clean / hot / cool 各自的准确率）。
- 验收：location/clean 类一致率应很高；hot/cool 类一致率体现 provenance+衰减窗调得对不对。
  **这张表就是你上真机前对自写裁判的信任度证明。**

> 接 `alf_env`：在 `_step` 成功后调 `shadow.update(command, obs)`；`snapshot()` 暴露 `shadow` 摘要。
> 持续模式(Phase 1)用 `judge()` 判我们自定义目标；stock 模式仍可读 `won` 做校准。

---

## Phase 3 — Per-home 位置 belief 作为搜索先验（跨家务步数下降引擎）

**问题**：让**不同家务**在**同一个家**里也变快——靠记住"这个家东西在哪"，把搜索从"扫一遍"
压成"确认一个点"。

**核心原则**（务必照此实现，别退化成盲缓存）：
> belief 不是 ground truth，是**带 confidence/时间戳的搜索先验**：用它**排序**去哪先看，
> 到了**仍要看一眼确认**；命中→刷新，未命中（被挪走）→丢弃该条→退回搜索→找到后写新位置。
> 感知与记忆不对立：**记忆决定先看哪，感知保证记忆不烂。**

### 新模块 `master/memory/home_belief.py`（或挂在 agent 上）
- 存储**按 home_id 分键**：`belief[home_id][obj_key] = {location, confidence, last_seen_task, source}`，
  `source ∈ {placed_by_me(高), perceived(高), inferred(低)}`。持久化到
  `master/memory/homes/<home_id>.json`（**跨任务保留**，这是 per-home 记忆）。
- 更新：每次感知（解析 observation）和每次自己 place（provenance，高 confidence）写入。
- confidence 随"距上次确认的任务数"衰减。

### 搜索先验级联（注入 planner）
规划搜索时，给出**排好序**的候选位置：
```
① 该实例的缓存位置（per-home 记忆，最高信息）
② 这个家学到的"物体类型→容器"先验（A 类·习得）
③ 通用常识先验（A 类·写死，已在 planner.py 的 _alfworld_rules 里）
```
- 在 `master/agents/planner.py` `forward()` 的 ALFWorld 分支，新增一段 `location_prior`，按上面级联
  给出"搜 X 时，先去 [排序后的位置]"。**只改注入内容，别动现有 _alfworld_rules 结构。**
- 命中/未命中后更新 belief（命中刷新；未命中丢弃+触发更广搜索）。

### 验收（这才是产品证据）
- 在**一个 home** 里**顺序派多个不同家务**（用 floorplan 301 那 13 个不同任务做素材，家具一致）：
  **第 k 个家务的步数随 k 下降**（因为家变熟了），won 保持。
- **漂移测试**：用 `POST /inject_move` 把某物体挪走 → 下个任务该物体的 belief 应"命中失败→重搜→
  更新到新位置"，且**步数只多花'看一眼'，不退化成全搜**。
- 注意 measurement 坑：**按任务类型分别看**步数（look_at vs clean&place 难度差很多，混在一起趋势会被
  任务难度污染）。

---

## 跨切面 & 红线

- **记忆按 home 分键**：现在所有经验糊在一个 `multi_step.md`。Phase 3 起，位置 belief 按 `home_id`
  存；检索键 = `(home_id, 任务类型, 物体类型)`。
- **别碰的东西**：
  - 不要动 `serve/`（MuJoCo）那条链路——这几个 Phase **只在文本后端**做。
  - 不要在这几个 Phase 里重写"经验抽象层级(A/C/D/E)"逻辑——那是**另一条独立工作流**，别捆进来。
  - 不要删/改 `reset_to`、`/success`(保留 won)、现有 bench 行为——`run_curve.py` 仍要能跑。
  - 保持 stock `won` 通路可用（Phase 2 校准、Phase 3 对照都要用它）。
- **每个 Phase 独立验收后再进下一个。** 尤其 **Phase 0 不出正信号，停下来查（多半是 R2
  exploration_rate 或经验没在累积），别往 Phase 1 冲。**

## 实现顺序回顾
Phase 0（步数埋点+同 game 重复，证明机制） → R4 验证持续世界可行 → Phase 1（持续的家） →
Phase 2（自写裁判+校准） → Phase 3（位置 belief 先验+漂移测试，拿产品证据）。
