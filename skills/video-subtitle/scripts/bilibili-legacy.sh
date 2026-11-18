#!/usr/bin/env bash
# bilibili-legacy.sh — B站视频字幕/转写辅助（已弃用）
# 新任务请用 scripts/video_subtitle.py；scripts/bili.sh 仅作为转发兼容入口。
# 子命令：probe | audio | srt | plain
# 转写本身由 agent 的 AudioTranscribe 工具完成（本脚本只负责取音轨和格式化）

set -uo pipefail

YTDLP="${YTDLP:-yt-dlp}"
PY="${PY:-python}"

usage() {
  cat <<'EOF'
用法:
  bilibili-legacy.sh probe <链接|BV号|av号> [浏览器名]   看元信息、时长、有没有站内CC字幕
  bilibili-legacy.sh audio <链接|BV号|av号> [输出目录]   只下音轨，打印文件绝对路径
  bilibili-legacy.sh srt   <转写文本> [输出.srt]         时间轴文本 -> SRT 字幕
  bilibili-legacy.sh plain <转写文本> [输出.txt]         时间轴文本 -> 纯文本稿

浏览器名可选 chrome / edge / firefox，用于读取该浏览器已登录的 B站 Cookie，
多数带 CC 字幕的视频需要它；不填则按未登录访问。

已弃用：新任务请用 video_subtitle.py；bili.sh 为兼容转发入口。
EOF
}

norm() {
  local raw="$1"
  raw="${raw// /}"
  case "$raw" in
    BV??????????)   echo "https://www.bilibili.com/video/$raw" ;;
    av[0-9]*)       echo "https://www.bilibili.com/video/$raw" ;;
    b23.tv/*|www.b23.tv/*) echo "https://$raw" ;;
    http*)          echo "$raw" ;;
    *)              echo "$raw" ;;
  esac
}

cmd_probe() {
  local url ck="${2:-}"
  url=$(norm "${1:?缺少链接}")
  local args=(--dump-json --no-warnings --no-playlist)
  [[ -n "$ck" ]] && args+=(--cookies-from-browser "$ck")

  local json
  json=$("$YTDLP" "${args[@]}" "$url" 2>/dev/null) || {
    echo '{"ok":false,"error":"解析失败：链接无效、需要登录，或该视频不可访问"}'
    return 1
  }

  printf '%s' "$json" | "$PY" -c '
import json, sys
d = json.load(sys.stdin)
subs = dict(d.get("subtitles") or {})
subs.update(d.get("automatic_captions") or {})
real = sorted(k for k in subs if k != "danmaku")
dur = int(d.get("duration") or 0)
out = {
    "ok": True,
    "bvid": d.get("id"),
    "title": d.get("title") or "",
    "uploader": d.get("uploader") or d.get("channel") or "",
    "duration_s": dur,
    "duration": "%d:%02d" % (dur // 60, dur % 60),
    "has_cc": bool(real),
    "cc_langs": real,
    "url": d.get("webpage_url") or "",
}
print(json.dumps(out, ensure_ascii=False))
'
}

cmd_audio() {
  local url outdir
  url=$(norm "${1:?缺少链接}")
  outdir="${2:-${TMPDIR:-/tmp}/bili-sub}"
  mkdir -p "$outdir" || { echo '{"ok":false,"error":"输出目录不可写"}'; return 1; }

  local before after
  "$YTDLP" --no-warnings --no-playlist -f bestaudio \
      -o "$outdir/%(id)s.%(ext)s" "$url" >/dev/null 2>&1 || {
    echo '{"ok":false,"error":"音轨下载失败：视频可能需要登录/大会员，或链接不对"}'
    return 1
  }

  local f
  f=$(ls -t "$outdir"/* 2>/dev/null | head -1)
  [[ -n "$f" ]] || { echo '{"ok":false,"error":"下载后没找到音频文件"}'; return 1; }

  local dir
  dir=$(cd "$(dirname "$f")" && pwd -W 2>/dev/null); [[ -n "$dir" ]] || dir=$(dirname "$f")
  printf '{"ok":true,"audio":"%s/%s","bytes":%s}\n' \
    "$dir" "$(basename "$f")" "$(stat -c%s "$f" 2>/dev/null || echo 0)"
}

cmd_srt() {
  local src="${1:?缺少转写文本}"
  local out="${2:-${src%.*}.srt}"
  [[ -f "$src" ]] || { echo "找不到文件: $src" >&2; return 1; }
  "$PY" - "$src" "$out" <<'PYEOF'
import re, sys

src, out = sys.argv[1], sys.argv[2]
pat = re.compile(r'^\[([\d:.]+),([\d:.]+)(?:,(\d+))?\]\s?(.*)$')

def tosec(t):
    s = 0.0
    for p in t.split(':'):
        s = s * 60 + float(p)
    return s

def ts(sec):
    if sec < 0: sec = 0
    h = int(sec // 3600); m = int(sec % 3600 // 60)
    s = int(sec % 60); ms = int(round((sec - int(sec)) * 1000))
    if ms == 1000: s, ms = s + 1, 0
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)

segs, cur = [], None
for line in open(src, encoding='utf-8-sig'):
    line = line.rstrip('\n')
    m = pat.match(line)
    if m:
        if cur: segs.append(cur)
        cur = [tosec(m.group(1)), tosec(m.group(2)), m.group(4).strip()]
    elif cur is not None and line.strip():
        cur[2] = (cur[2] + ' ' + line.strip()).strip()
if cur: segs.append(cur)

with open(out, 'w', encoding='utf-8') as f:
    n = 0
    for a, b, txt in segs:
        if not txt: continue
        n += 1
        f.write("%d\n%s --> %s\n%s\n\n" % (n, ts(a), ts(b), txt))
print(out)
PYEOF
}

cmd_plain() {
  local src="${1:?缺少转写文本}"
  local out="${2:-${src%.*}.txt}"
  [[ -f "$src" ]] || { echo "找不到文件: $src" >&2; return 1; }
  "$PY" - "$src" "$out" <<'PYEOF'
import re, sys
src, out = sys.argv[1], sys.argv[2]
pat = re.compile(r'^\[[\d:.]+,[\d:.]+(?:,\d+)?\]\s?')
paras, buf = [], []
for line in open(src, encoding='utf-8-sig'):
    t = pat.sub('', line.rstrip('\n')).strip()
    if not t: continue
    buf.append(t)
    if sum(len(x) for x in buf) > 180:
        paras.append(''.join(buf)); buf = []
if buf: paras.append(''.join(buf))
open(out, 'w', encoding='utf-8').write('\n\n'.join(paras) + '\n')
print(out)
PYEOF
}

case "${1:-}" in
  probe) shift; cmd_probe "$@" ;;
  audio) shift; cmd_audio "$@" ;;
  srt)   shift; cmd_srt   "$@" ;;
  plain) shift; cmd_plain "$@" ;;
  *)     usage ;;
esac
