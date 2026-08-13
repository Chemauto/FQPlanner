# NX 语音触发接待(voice trigger)

对着 G1 的 NX 说 **"开始接待"** → 大脑接待任务被触发、前端自动显示。这是接待 demo 的**语音入口**。

## 链路

```
M260 USB 麦克风 → arecord 录音 → 音量门限(VAD)滤静音 → qwen-omni 云 ASR 转文字
→ 文字含"开始接待" → POST 大脑 deploy 的 /publish_task → master 命中接待 skill
```

脚本常驻跑在 NX 上,和 master/slaver/deploy(在大脑机上)是**两台机器**,靠一个 HTTP POST 连起来。

## 硬件

- **M260 USB 麦克风阵列**(型号 XFM-DP-V0.0.18),插 NX 的 USB 口。
- ⚠️ **必须接独立供电** —— 否则枚举失败、`dmesg` 会狂刷 `error -71 / power cycle`,系统认不到声卡。
- ⚠️ **别和 CAN 总线(PCAN-USB)共同一个 USB hub** —— 插拔麦克风会扰动 CAN(疑似运动/传感器通信)。正式用**短 USB 线直插 NX**。
- 声卡号脚本会**自动识别**(`arecord -l` 找 XFM),NX 重启后卡号变了也不用管。
- (为什么不用 G1 板载麦 → 见文末)

## 依赖

- **NX 上**:`python3`(仅标准库,用 `urllib` 无需 dashscope SDK)、`alsa-utils`(提供 `arecord`)。
- **一个 key**:dashscope 国际版**兼容模式**的 API key —— 就是本项目 `.env` 里的 `VLM_API_KEY`(`sk-ws-` 开头)。

## 部署(4 步)

```bash
# 1. 把 key 写到 NX(不入库):
printf '%s' '<粘贴 .env 里的 VLM_API_KEY>' > ~/.vlm_key && chmod 600 ~/.vlm_key

# 2. 传脚本到 NX:
scp reception_voice.py dev@<NX_IP>:~/

# 3. (换了大脑机才需要)改触发地址,默认指向 192.168.0.229:8888:
export DEPLOY_URL=http://<大脑 deploy 机的 IP>:8888/publish_task

# 4. 常驻启动:
nohup python3 -u ~/reception_voice.py >~/voice.log 2>&1 </dev/null & echo "PID $!"
```

> ⚠️ **启动的坑**:别用 `tmux`(非交互 ssh 无 tty 会挂→255);`nohup` 命令末尾**别接** `sleep`/`tail`(会让 ssh 挂住)。就用上面那条 `nohup ... </dev/null & echo $!`。

## 运维

```bash
# 看实时识别(只在有人说话时出 heard,带 rms 音量):
ssh dev@<NX_IP> 'tail -f ~/voice.log'

# 停 / 重启(精确按进程名杀,别用 pkill -f reception_voice.py —— 它会连执行命令的 ssh bash 一起杀!):
ssh dev@<NX_IP> 'for p in $(pgrep -f reception_voice.py); do [ "$(cat /proc/$p/comm)" = python3 ] && kill -9 $p; done'
```

- 触发后有 **8 秒冷却**(防连发)。
- 调**触发词 / 灵敏度**:改脚本顶部 `TRIGGER` / `SILENCE_RMS`(RMS 门限,实测说话 1200~1400、底噪 <800)。

## 已知取舍

- ASR 用 `qwen3-omni-flash`(**全模态大模型**,非专门 ASR),识别一般但**对触发够用**(只认"开始接待"四个字)。要更准可换 `paraformer`(需 dashscope **原生** key,现在这个 `sk-ws-` 只能走兼容模式)或本地 `whisper`。
- qwen-omni 对底噪会**幻觉**出固定句子("我今天要讲的是…提升幸福感"),靠 VAD 门限 + prompt("没听清就输出空") + `HALLUC` 黑名单三重压制。

## 为什么不用 G1 板载麦(探尽了)

板载麦由 RockChip MCU 管、音频输出**没启用**:ALSA 无录音设备、无 UDP 音频多播、`/audiosender`(unitree_go/AudioData)`publisher=0` 没采集、audio ASR(api_id 1002)和 VUI 调用都**超时**(3104,服务端没起);C++/Python SDK 的 `AudioClient` 都只有 TTS 输出、ASR 只注册没实现。要启用得动核心主机 `192.168.123.161`(SSH 端口锁死够不着)或 MCU 固件。所以改用 M260 外接。参考实现:GitHub `SaxionMechatronics/unitree_converse`。
