# 进度接力 / RESUME

> 给回来的我 / 新对话窗口。2026-06-23 因工具输出乱码(疑似网络/VPN)暂停。
> 读这一篇就能直接上手。设计背景见同目录 `e2e_debug_view.md`。

## 现在在做什么

做 **ALFWorld 端到端调试视图**:能完整看到一个任务"指令 → master 拆子任务 → slaver 每步动作 → 后端观测 → 结果"。
**第一步**:实地看现有 `bench/extract_traces.py` 对某个任务够不够用,再决定补强还是重做。

## 为什么暂停

工具调用输出一直乱码/截断(疑似网络/VPN)。表现:Edit/Write 几次看似成功实则没落盘(得用干净命令反复核实)、Bash 输出被截断混入乱码。**换环境重连后再继续。**

## 已完成(已核实落盘)

- **Phase 0 步数埋点**(原为 per-home 测试台准备,per-home 现已暂缓):
  - `serve_alfworld/alf_env.py`:`self._steps` 计数器 5 处(`__init__`/`_after_reset`/`_step`/`steps()`/`snapshot`)
  - `serve_alfworld/server.py`:`/success` 返回 `{won, steps}`
  - `bench/run_repeat.py`(同 game 重复跑读步数)、`bench/plot_repeat.py`(画 steps-vs-run)
  - 四个文件均编译通过
- **建档**:`christine/e2e_debug_view.md`(端到端调试视图的目的/意义/注意事项/方向)
- **清理**:删了 `bench/traces*`、`bench/curve_results.*`、`bench/__pycache__`

## 立即待办(回来第一件事)

1. 确认新环境工具不乱码。
2. **诊断 `put a pan on the diningtable`(train index 4)为什么失败**:
   - ★ **先查服务有没有重启、用的是不是最新代码**。put pan 是最简单的 pick&place,通用层写死后同类任务
     之前 10/10 全赢过;现在 8 次全超时(`steps=50`)**很反常**,强烈怀疑这次起服务时 slaver/serve_alfworld
     没重启、跑的是旧代码(少了"开放表面优先 + 两遍搜索"等修复 → 简单任务也搜不完 50 步)。
   - 跑 `extract_traces.py` 抽这次执行的 trace,看 master 怎么拆、slaver 每步发了什么、**哪一步先崩**。
3. **据此评估 extract_traces**:够用 → 补强它;漏命令/时间窗对不齐 → 换成"**执行时主动记一份结构化 trace**"。
   这就是端到端调试视图第一步的落地决策点。

## 关键事实(别忘)

- 架构:master(:5000)→ redis → slaver → robot_api → `serve_alfworld`(:5301)
- **ALFWorld 每局 max_steps = 50**;`steps=50 且 won=False` = 撞上限超时,**不是真实完成步数**
- 通用层写死后零经验能到 **10/10**(train[0..9]);put pan 现在失败 → 疑似服务/代码状态问题,不是任务太难
- 跑任何实验前:`export EXPLORATION_RATE=0.1`(否则 LLM 忽略经验)

## 服务起法(四个终端)

```bash
# 1) 后端(alfworld conda env)
conda activate alfworld
export ALFWORLD_SEED=0 ALFWORLD_DATA=~/alfworld_data ALFWORLD_CONFIG=~/alfworld-repo/configs/base_config.yaml
python serve_alfworld/main.py            # :5301

# 2) redis
redis-server

# 3) master(FQPlanner env,低 exploration)
conda activate FQPlanner
cd master && export EXPLORATION_RATE=0.1 && python run.py     # :5000

# 4) slaver —— 启动日志要看到「[search.py] search_and_grasp 工具已注册」= 新代码生效
conda activate FQPlanner
python slaver/run.py
```

## 工作约定

- 和我对接的文件(笔记/spec/报告)放 `christine/`,**不放项目根目录**;代码改动仍在原位置。
- 别过度设计:先把 ALFWorld 文本调试视图做扎实,**不为还不存在的 mujoco 提前搭通用框架**;
  只保持"数据与展示分开"这点结构卫生即可。
