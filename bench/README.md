# bench — 经验学习曲线(ALFWorld)

验证「机器人总结经验」的功能会不会随着学到的任务变多、**逐步提升任务成功率**。
产出一张双线折线图:

- **sr_heldout**（实线，头条指标）：在 `valid_unseen` 留出集上、**冻结经验只读**测得的成功率 → 真·泛化。
- **sr_sameset**（虚线，sanity / 上界）：在训练用过的同一批任务上测得 → 含「背答案」成分。

> 两条都涨 = 经验能泛化;只有 sameset 涨 = 主要在背答案。成功裁判用 ALFWorld 内置 `won`(= ALFRED success)。

## 原理(一句话)

固定 seed 让每个 split 的 game 顺序确定 → driver 用 `(split, index)` 确定性载入任务 →
每个 checkpoint **快照经验库** 跑留出/同集评测(每个任务后还原,保证整批看同一份经验快照)→
然后进入**学习相**:顺着 train 流再学 `chunk` 个新任务,`auto_learn` 把经验写进 `master/memory/skills/` →
下个 checkpoint 重复。X 轴 = 已学任务数,Y 轴 = SR。

## 前置:两个旋钮(都不用手改 tracked 配置,driver 会自动校验)

1. **exploration_rate**(默认 `0.8` = 80% 忽略经验,会让曲线变平)。
   **不用改 `master/config.yaml`**,起 master 前 `export EXPLORATION_RATE=0.1` 即可([agent.py](../master/agents/agent.py) 认这个环境变量覆盖)。
   忘了也没关系:driver 开跑前会查 master 的 `/api/exploration_rate`,**高于 `--max-exploration`(默认 0.3)直接报错退出**,不会白跑。
2. **seed**:不用"改",`export ALFWORLD_SEED=0` 一处同时喂给后端和 driver(driver 的 `--seed` 默认读它)。
   两边不一致时 driver preflight 会拦。
3. **`robot_api/config.yaml`** 切到 alfworld 后端、关掉 mujoco(否则 `required:1` 的 mujoco 连不上会让调用失败)。
   见 `serve_alfworld/README.md` 的「切到 ALFWorld 后端」。

可选:`camera.enabled` 在文本模式无意义,确认是 `false`(当前已是)。

## 起服务(四个终端)

```bash
# 1) ALFWorld 后端(用一个固定 seed,benchmark 靠它复现固定任务集)
conda activate alfworld
export ALFWORLD_DATA=~/alfworld_data
export ALFWORLD_CONFIG=~/alfworld-repo/configs/base_config.yaml
export ALFWORLD_SEED=0
python serve_alfworld/main.py          # :5301

# 2) redis
redis-server

# 3) master(EXPLORATION_RATE 低值,不用改 config)
conda activate FQPlanner
export EXPLORATION_RATE=0.1
python master/run.py                   # :5000

# 4) slaver
python slaver/run.py
```

> 不需要 `deploy/run.py`(Web 控制台);driver 直接打 master 的 HTTP。

## 跑曲线

```bash
conda activate FQPlanner            # 有 requests 即可

# ① 先烟雾测试跑通全链路(~42 次执行),并从零经验开始:
python bench/run_curve.py --smoke --reset-experience --yes

# ② 正式跑(论文级);--reset-experience 把现有经验库备份后清空 → 真零基线:
python bench/run_curve.py --n-train 100 --chunk 20 --n-eval 50 --n-sameset 50 --reset-experience --yes

# 中途崩了/想接着跑(沿用已写入的经验库,从 CSV 最后一个 checkpoint 续):
python bench/run_curve.py --n-train 100 --chunk 20 --n-eval 50 --n-sameset 50 --resume --yes

# 先只看计划和总任务数,不连服务:
python bench/run_curve.py --dry-run --n-train 100 --chunk 20 --n-eval 50 --n-sameset 50

# 画图:
python bench/plot_curve.py --csv bench/curve_results.csv
```

输出:`bench/curve_results.csv` 和 `bench/curve_results.png`。
`--reset-experience` 不会删数据:旧经验库备份到 `master/memory/skills_backup_<时间戳>/`。

## 算力:总任务执行次数 ≈ `n_train + (n_train/chunk + 1) × (n_eval + n_sameset)`

每次执行 = **一整轮** LLM 规划 + slaver 多步执行,不是一次 API 调用。先用小 N 跑通再放大。

| 配置 | 总执行次数 |
|---|---|
| 烟雾测试 `--n-train 10 --chunk 10 --n-eval 8 --n-sameset 8` | 10 + 2×16 = **42** |
| 默认 `--n-train 20 --chunk 10 --n-eval 15 --n-sameset 15` | 20 + 3×30 = **110** |
| 论文级 `--n-train 100 --chunk 20 --n-eval 50 --n-sameset 50` | 100 + 6×100 = **700** |

## 重要参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--smoke` | off | 烟雾预设(n_train=10,chunk=10,n_eval=8,n_sameset=8);显式 `--n-*` 仍优先 |
| `--reset-experience` | off | 开跑前把经验库备份到 `skills_backup_<时间戳>/` 并清空 → 真零基线 |
| `--resume` | off | 从已有 CSV 最后一个 checkpoint 之后续跑(沿用当前经验库;与 `--reset-experience` 互斥) |
| `--max-exploration` | 0.3 | master exploration_rate 高于此值则拒跑 |
| `--n-train` | 20 | 训练流总任务数(经验从这些任务里学) |
| `--chunk` | 10 | 每个 checkpoint 之间新学多少任务 = X 轴步长 |
| `--n-eval` | 15 | 每次留出评测任务数(valid_unseen 的前 N 个) |
| `--n-sameset` | 15 | 每次同集评测任务数(train 的前 N 个,都在训练流里) |
| `--eval-split` | `eval_out_of_distribution` | 留出集;`eval_in_distribution`=valid_seen 也可 |
| `--seed` | `$ALFWORLD_SEED` 或 0 | 固定任务集;driver 会校验与后端 seed 一致 |
| `--task-timeout` | 300 | 单任务最长等待秒,超时记失败并跳下一个 |

## 几个会让曲线失真的坑(已处理 / 需注意)

- **背答案 vs 泛化**:同集评测一定会涨;**以 `sr_heldout` 为准**判断"经验真的有用"。
- **冻结评测**:评测任务跑完会还原 `master/memory/skills/`,所以评测自身不污染经验库(driver 自动做)。
- **seed 一致**(driver 已自动校验):`--seed` 默认读 `ALFWORLD_SEED`,与后端不一致直接报错。
- **exploration_rate**(driver 已自动校验):忘了调低会被 preflight 拦下,不会白跑。
- **LLM 随机性**:同一 checkpoint 的 SR 仍有采样噪声;要更稳可把 LLM 温度调低,或多 seed 重复取均值。
- **零经验基线**:想要曲线从真零起步,用 `--reset-experience`(否则会带着旧 `skills/` 里已有的经验开跑)。

## 改了什么(为支持本 benchmark)

- `serve_alfworld/alf_env.py`:加 `reset_to(split, index)` + `dataset_size()` —— 按 `sorted()`(+seed shuffle)确定性寻址 game,
  让同一批留出任务能在每个 checkpoint 原样重放。原 `reset()`(顺序前进)行为保留。
- `serve_alfworld/server.py`:`POST /reset` 支持 `{split, index, seed}`;新增 `GET /dataset_info?split=`(含 seed,供 driver 校验)。无 `index` 时是旧行为。
- `serve_alfworld/main.py`:seed 优先级 `--game` > `ALFWORLD_SEED` > 随机,让固定任务集可复现。
- `master/agents/agent.py`:`exploration_rate` 支持 `EXPLORATION_RATE` 环境变量覆盖(不用改 tracked config)。
- `master/run.py`:新增只读 `GET /api/exploration_rate`(driver preflight 用它防止高探索率白跑)。
