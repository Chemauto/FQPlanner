# serve_dream — 导航建图组(DREAM)真机后端适配

把导航建图组的三类交付物翻译成 FQPlanner 标准后端 HTTP 接口,**master / slaver /
nav2 生成器零改动**即可跑真机地图:

| 他们的交付物 | 适配为 | 适配器 |
|---|---|---|
| `map.yaml` + `map.pgm`(ROS map_server trinary) | `GET /map_data` | `adapters/rosmap.py` |
| `total_scene_graph_latest.json`(场景关系图) | `GET /objects` `/fixtures` `/scene` | `adapters/scene_graph.py` |
| `nav_map_latest.json`(robot_xyt 位姿) | `GET /base_status` | `service/server.py` |
| 导航执行 | `POST /nav`(转发/文件交接) | `adapters/exchange.py` / `nav_handoff.py` |

**通道两种**(config.yaml `exchange.mode`):
- `http`(联调首选):数据 GET 对方静态文件服务(`base_url`);导航 POST 对方
  `nav2_goal_bridge` 的 `/nav`(`nav_url`,同步)。
- `dir`(离线测试/备用):读本地目录;导航走 `tasks/` 文件契约
  (对方可用 `templates/nav_task_watcher.py` 监听执行)。

`/grasp` `/place` `/screenshot` 返回 501:真机上由 VLA 组后端提供(robot_api 双后端分路由)。

## 用法

```bash
# 1. config.yaml: mode 选 http(填对方 base_url/nav_url)或 dir(本地目录)
python serve_dream/main.py   # 默认端口 5006

# 2. robot_api/config.yaml: dream.enabled=1(状态+导航), VLA 后端管操作

# 3. 用他们的地图重建工作点(全程复用现有 nav2 管线):
python nav2/free_points_generator.py --map /path/to/shared_dir/map.yaml
python nav2/workpoints_generator.py     # /objects /fixtures 已由本服务提供
#   注意先把 nav2/config.yaml 的 waypoints.fixtures 换成场景图 id(table→table_1 等)
```

## 离线自测(不需要对方在线)

```bash
python serve_dream/selftest.py
```

样例数据在 `sample/`(来自对方 2026-07-13 首次交接包,场景图为裁剪版)。

对接契约、坐标系约定、双方职责见 `docs/对接手册-导航建图组.md`。
