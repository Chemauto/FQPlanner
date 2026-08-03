# 大脑 ↔ VLA 组 对接(接待 Demo:茶水间取可乐 → 会议室桌上)

## 你们做什么(起一个 HTTP 服务,实现这些)

| 接口 | 请求 | 返回 |
|---|---|---|
| `POST /grasp` | `{"object_name":"可乐"}` | `{"success":bool, "result":"…"}` |
| `POST /place` | `{"object_name":"可乐","target":"meeting_room"}` | `{"success":bool, "result":"…"}` |
| `POST /screenshot` | `{"context":"…"}` | jpg 字节 |
| 夹爪状态(二选一) | `GET /objects`(可乐带 `"grasped":bool`)或 `GET /gripper_status` | `{"grasped":bool}` |

## 我给你们什么

- **语义物体名**(`可乐`)+ 目标**区域名**(`meeting_room`),**不给坐标**——抓哪、怎么抓、放稳,你们看图解决。
- 抓/放前,机器人已由导航组送到位。

## 约定(3 条)

1. 给语义不给坐标。
2. **自报成功 ≠ 真成功**:我抓完会查 `grasped`、放完会拍照/数物体确认。所以 `grasped` 要真实反映夹爪——空抓(闭合但没夹住)必须报 `false`。
3. 抓不到就 `{"success":false}`,我重试(≤2 次)、超限停下上报。

## 请你们定

pi0.5 还在训 → **不必等它**。现在能给什么兜底(早期 checkpoint / 脚本抓取)?端口就绪我一行切过去。

服务起好把 `IP:端口` 发我。联系人:毕艺恒(github.com/Chemauto/FQPlanner)
