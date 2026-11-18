---
name: video-subtitle
description: 通用视频字幕提取与转写，覆盖 YouTube、B站、抖音、小红书及其他 yt-dlp 支持的网站。识别平台后优先获取人工或自动字幕，无字幕时仅提取音轨并用 AudioTranscribe 或 Whisper 兜底，统一为 start/end/text 片段并导出 TXT、SRT、MD。用户给视频链接并要求字幕、文字稿、逐字稿、转录或总结视频内容时使用。只读公开内容，不下载完整视频，不绕过登录、付费或地区限制。
agent_created: true
---

# 通用视频字幕提取

规范入口是 `scripts/video_subtitle.py`；B站旧脚本已迁移到 `scripts/bilibili-legacy.sh`（已弃用），`scripts/bili.sh` 只作为转发兼容入口。脚本只依赖 Python 标准库与 yt-dlp，YouTube 直连使用 Innertube，不要求安装 Node.js 包。

## 路由与回退

1. 用 `probe` 获取标题、作者、时长、人工字幕和自动字幕，先确认抓到正确视频。
2. 用 `fetch` 获取字幕并一次导出统一 JSON、TXT、SRT、MD。
3. 按平台处理：
   - YouTube：先试 Innertube 字幕轨；失败或受限时自动回退 yt-dlp。
   - B站：沿用现有 yt-dlp 元信息与字幕逻辑；排除 `danmaku`，弹幕不是字幕。
   - 抖音、小红书及其他平台：使用 yt-dlp 的人工/自动字幕轨；多数短视频没有独立字幕轨，应预期走 ASR。
4. `fetch` 返回 `error_code: no_subtitles` 时，用 `audio` 仅提取音轨，再转写；不要把解析失败、登录限制误报成“无字幕”。
5. 把 ASR 结果归一化为相同 segment 模型，再导出交付文件。

统一模型：

```json
{
  "version": 1,
  "video": {"id": "", "title": "", "uploader": "", "duration_s": 0, "url": "", "platform": ""},
  "source": "innertube-manual | innertube-automatic | yt-dlp-manual | yt-dlp-automatic | asr",
  "language": "",
  "segments": [{"start": 0.0, "end": 2.5, "text": "..."}]
}
```

## 命令

在 skill 目录运行，或将脚本路径替换为绝对路径：

```bash
# 1. 探测；可选 --browser chrome/edge/firefox 使用浏览器现有登录态
python scripts/video_subtitle.py probe "https://www.youtube.com/watch?v=VIDEO_ID"
python scripts/video_subtitle.py probe "BV1KwNvzqECx"

# 2. 提取字幕，输出 .segments.json、.txt、.srt、.md
python scripts/video_subtitle.py fetch "视频URL" "输出目录"
python scripts/video_subtitle.py fetch "视频URL" "输出目录" --lang zh-CN

# 3. 无字幕时仅下载音轨，返回可供转写工具使用的绝对路径
python scripts/video_subtitle.py audio "视频URL" "输出目录"

# 4. 将 AudioTranscribe 文本、Whisper JSON、SRT、VTT、JSON3、TTML 统一导出
python scripts/video_subtitle.py normalize "转写结果.txt" "输出目录" --source asr --platform bilibili --lang zh --url "原始视频URL" --video-id "BV号" --uploader "UP主"
python scripts/video_subtitle.py normalize "whisper.json" "输出目录" --source asr --platform youtube --lang en --url "原始视频URL"

# 从统一 JSON 重新生成三种交付格式
python scripts/video_subtitle.py export "文稿.segments.json" "输出目录"
```

Windows 上把脚本返回的绝对音频路径直接交给 AudioTranscribe；不要把 Git Bash 的 `/tmp` 路径当成 Windows 真实路径。使用本地 Whisper 时优先输出 JSON，再用 `normalize` 导入；不要把无时间轴的纯文本伪造成 SRT。

## ASR 兜底

1. 执行 `audio`，确认返回 `ok: true` 和音频绝对路径。
2. 调用 AudioTranscribe 转写，或在已有 Whisper/faster-whisper 环境中转写；保留每段起止时间。
3. AudioTranscribe 文本格式为 `[起点,终点,说话人] 文本`，保存为 UTF-8 文本后执行 `normalize --source asr`。
4. Whisper JSON 需含 `segments` 数组，每段含 `start/end/text`；直接执行 `normalize --source asr`。
5. 标注“机器转写，未校对”，提醒核对专有名词、人名、数字和口音较重部分。

## 输出与交付

- 报告视频标题、作者、平台、时长、字幕语言和片段数，便于用户核对来源。
- 明确区分人工字幕、自动字幕和 ASR；不要统称为“官方字幕”。
- TXT 是无时间轴正文，SRT 保留标准时间轴，MD 含元信息和逐段时间戳，`.segments.json` 供二次加工。
- B站分 P 默认处理链接指向的当前 P；需要其他 P 时使用对应 `?p=N` 链接。
- 长视频先报告时长，再按用户要求处理全集或指定区间；不得因时长擅自改下完整视频。

## 边界与故障

- 平台“支持”指 yt-dlp 能解析公开可访问内容，不保证每个站点、每个视频始终可用；平台接口和反爬策略会变化。
- 优先无登录访问。只有用户明确要求且浏览器已登录时才使用 `--browser`；不要索取密码或手工 Cookie。
- 不下载完整视频，不绕过大会员、付费、私密、地区或 DRM 限制，不换账号重试。
- Innertube 是非公开稳定接口，失败时保留 warning 并回退 yt-dlp；两者都失败时如实报告。
- 无字幕与访问失败分开处理：只有明确没有字幕轨才进入 ASR。
- ASR 稿件是未校对文本，不作为逐字准确的原文引用。
