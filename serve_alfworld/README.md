# serve_alfworld — ALFWorld(纯文本)后端

把 ALFWorld 包成一个符合 `robot_api/contract.md` 的后端,让现有 **master / slaver / robot_api 一行不改**就能驱动它。换 benchmark = 换这个 `serve_*` 文件夹 + 在 `robot_api/config.yaml` 里切后端。

## 为什么是文本版

你是 arm64 + macOS 12 + 磁盘紧张,跑不了 ai2thor 渲染。ALFWorld 文本版无需 GPU/渲染,
任务、场景、PDDL 目标判定和 ALFRED 一致,`info['won']` 直接给**内置可信成功信号**——
正好做大脑/规划/自我学习,且动作空间是封闭可枚举的(`admissible_commands`),评估很干净。

## 进度

- [x] `alf_env.py` — ALFWorld 封装 + 「意图→合法命令」解析器(适配器核心)。**可独立 smoke test。**
- [ ] `server.py` / `main.py` — Flask,把契约 endpoint 映射到 alf_env(alf_env 验通后再加)。
- [ ] `robot_api/config.yaml` 加 `alfworld` 后端 + slaver 两个工具的解耦(见下)。

## 第一步:smoke test `alf_env.py`(先做这个)

在装了 alfworld 的 conda 环境里:

```bash
conda activate alfworld
export ALFWORLD_DATA=~/alfworld_data
# 若 config 不在默认位置可指定:export ALFWORLD_CONFIG=~/alfworld-repo/configs/base_config.yaml
cd /Users/christinebi/FQPlanner
python serve_alfworld/alf_env.py
```

应看到:任务、观测、合法动作列表,以及解析器自动把 `navigate_to('<容器名>')`
匹配成 `go to <容器名> 1` 并执行。打印 `OK` 就说明程序化 API 和解析器在你机器上都正常。
**跑通后告诉我,我立刻补 `server.py` + `main.py` + robot_api 接线。**

## 契约 endpoint → alf_env 映射(server.py 的计划)

| robot_api 契约 | serve_alfworld 内部 |
|---|---|
| `POST /reset` | `env.reset()` → 返回 task + observation + admissible_commands |
| `POST /nav {target}` | `env.navigate_to(target)` → `go to <target> N` |
| `POST /grasp {obj_name}` | `env.grasp(obj_name)` → `take <obj> from <recep>` |
| `POST /place {obj_name, target}` | `env.place(obj_name, target)` → `move <obj> to <target>` |
| `GET /scene`、`/scene_state`、`/objects` | `env.snapshot()`(task/观测/合法动作/手持/可见实体) |
| **`GET /success`(新增)** | `env.won()` —— 内置成功信号,替掉手搓 verifier |
| `GET /fixtures`、`/base_status`、`/status`、`POST /screenshot` | 文本模式返回 stub(保持契约完整) |

## ⚠️ 一个必须解耦的点(接线时处理,不是现在)

slaver 的两个工具把 MuJoCo 专属的坐标逻辑写死在了工具层,ALFWorld 没坐标:

- `slaver/robot/module/base.py`:`navigate_to_target` 用 `find_waypoint` 把名字转成 `(x,y)` 再发。
- `slaver/robot/module/place.py`:`place_on_top` 用 `get_scene` 算 `(x,y,z)` 再发。

而 `robot_api.runtime` 对**字符串** target 本来就会发 `{"target": name}`(见 `_navigation_payload`),
对 ALFWorld 正好。所以解耦方向是:**让这两个工具把名字透传给 robot_api,坐标解析下沉到各自后端**
(MuJoCo 后端里做 waypoint/geometry,ALFWorld 后端里做合法命令匹配)。这样契约才真正跨符号/坐标后端成立。
改动很小,但要动 slaver——接线那步我会给你最小 diff,你拍板。

## 切到 ALFWorld 后端(接线时)

`robot_api/config.yaml` 里加一项,并把 `mujoco` 关掉(否则 `required:1` 的 mujoco 连不上会让调用失败):

```yaml
  alfworld:
    enabled: 1
    provide_state: 1
    accept_action: 1
    required: 1
    url: "http://127.0.0.1:5301"
    timeout: 120
    launch_hint: "serve_alfworld/main.py"
```

依赖:`pip install flask flask-cors`(server.py 用,alf_env.py 不需要)。
