#!/usr/bin/env python3
"""Extract, normalize and export subtitles without downloading full videos."""

from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

YTDLP = os.environ.get("YTDLP", "yt-dlp")
SUBTITLE_EXTS = {".json3", ".vtt", ".srt", ".ttml", ".dfxp", ".srv3", ".xml"}


class ToolError(Exception):
    code = "tool_error"


class NoSubtitles(ToolError):
    code = "no_subtitles"


def normalize_url(raw: str) -> str:
    value = raw.strip()
    if re.fullmatch(r"BV[0-9A-Za-z]{10}", value) or re.fullmatch(r"av\d+", value):
        return f"https://www.bilibili.com/video/{value}"
    if re.fullmatch(r"[0-9A-Za-z_-]{11}", value):
        return f"https://www.youtube.com/watch?v={value}"
    if re.match(r"^(?:www\.)?(?:b23\.tv|bilibili\.com|youtube\.com|youtu\.be)/", value):
        return "https://" + value
    return value


def detect_platform(url: str) -> str:
    host = (urlparse(url).hostname or "").lower().split(":")[0]
    if host == "youtu.be" or host.endswith(".youtube.com") or host.endswith(".youtube-nocookie.com"):
        return "youtube"
    if host == "b23.tv" or host.endswith(".bilibili.com"):
        return "bilibili"
    if host == "douyin.com" or host.endswith(".douyin.com"):
        return "douyin"
    if host in {"xiaohongshu.com", "xhslink.com"} or host.endswith(".xiaohongshu.com") or host.endswith(".xhslink.com"):
        return "xiaohongshu"
    return "generic"


def format_clock(seconds: float, srt: bool = False) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    if srt:
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def parse_time(value: str) -> float:
    text = value.strip().replace(",", ".")
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return float(text)
    parts = text.split(":")
    if len(parts) not in {2, 3}:
        raise ValueError(f"Invalid timestamp: {value}")
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + float(part)
    return seconds


def clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def normalize_segments(raw_segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in raw_segments:
        try:
            start = float(item["start"])
            end = float(item["end"])
        except (KeyError, TypeError, ValueError):
            continue
        text = clean_text(str(item.get("text") or ""))
        if not text or start < 0:
            continue
        if end <= start:
            end = start + 2.0
        result.append({"start": round(start, 3), "end": round(end, 3), "text": text})
    return result


def parse_timestamp_blocks(text: str) -> list[dict[str, Any]]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    segments: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        if "-->" not in lines[index]:
            index += 1
            continue
        left, right = lines[index].split("-->", 1)
        try:
            start = parse_time(left.strip().split()[-1])
            end = parse_time(right.strip().split()[0])
        except (ValueError, IndexError):
            index += 1
            continue
        index += 1
        content: list[str] = []
        while index < len(lines) and lines[index].strip():
            if "-->" in lines[index]:
                break
            content.append(lines[index].strip())
            index += 1
        segments.append({"start": start, "end": end, "text": clean_text(" ".join(content))})
    return normalize_segments(segments)


def parse_asr_text(text: str) -> list[dict[str, Any]]:
    pattern = re.compile(r"^\[([\d:.]+),([\d:.]+)(?:,([^\]]+))?\]\s?(.*)$")
    segments: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in text.replace("\r\n", "\n").split("\n"):
        match = pattern.match(line)
        if match:
            if current:
                segments.append(current)
            current = {
                "start": parse_time(match.group(1)),
                "end": parse_time(match.group(2)),
                "text": match.group(4).strip(),
            }
        elif current is not None and line.strip():
            current["text"] = f"{current['text']} {line.strip()}".strip()
    if current:
        segments.append(current)
    return normalize_segments(segments)


def parse_json3(data: dict[str, Any]) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    for event in data.get("events") or []:
        pieces = event.get("segs") or []
        text = clean_text("".join(str(piece.get("utf8") or "") for piece in pieces))
        if not text:
            continue
        start = float(event.get("tStartMs") or 0) / 1000
        duration = float(event.get("dDurationMs") or 0) / 1000
        segments.append({"start": start, "end": start + (duration or 2), "text": text})
    return normalize_segments(segments)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def parse_xml_subtitles(text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(text)
    segments: list[dict[str, Any]] = []
    for element in root.iter():
        if local_name(element.tag) != "p":
            continue
        attrs = {local_name(key): value for key, value in element.attrib.items()}
        try:
            if "begin" in attrs:
                start = parse_time(attrs["begin"])
            else:
                start = float(attrs.get("t", 0)) / 1000
            if "end" in attrs:
                end = parse_time(attrs["end"])
            elif "dur" in attrs:
                end = start + parse_time(attrs["dur"])
            else:
                end = start + float(attrs.get("d", 2000)) / 1000
        except (ValueError, TypeError):
            continue
        segments.append({"start": start, "end": end, "text": clean_text("".join(element.itertext()))})
    return normalize_segments(segments)


def parse_subtitle_file(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig")
    suffix = path.suffix.lower()
    if suffix in {".json", ".json3"}:
        data = json.loads(text)
        if isinstance(data, dict) and isinstance(data.get("segments"), list):
            return normalize_segments(data["segments"])
        if isinstance(data, dict) and isinstance(data.get("events"), list):
            return parse_json3(data)
        raise ToolError("JSON 中没有 segments 或 events；Whisper JSON 与 YouTube JSON3 可直接识别")
    if suffix in {".srt", ".vtt"}:
        return parse_timestamp_blocks(text)
    if suffix in {".ttml", ".dfxp", ".srv3", ".xml"}:
        return parse_xml_subtitles(text)
    return parse_asr_text(text)


def video_meta(info: dict[str, Any], platform: str, original_url: str) -> dict[str, Any]:
    return {
        "id": str(info.get("id") or ""),
        "title": info.get("title") or "",
        "uploader": info.get("uploader") or info.get("channel") or info.get("creator") or "",
        "duration_s": int(float(info.get("duration") or 0)),
        "url": info.get("webpage_url") or original_url,
        "platform": platform,
    }


def make_document(meta: dict[str, Any], source: str, language: str, segments: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": 1,
        "video": meta,
        "source": source,
        "language": language,
        "segments": normalize_segments(segments),
    }


def ytdlp_args(browser: str | None) -> list[str]:
    args = [YTDLP, "--no-warnings", "--no-playlist"]
    if browser:
        args.extend(["--cookies-from-browser", browser])
    return args


def run_ytdlp_info(url: str, browser: str | None) -> dict[str, Any]:
    process = subprocess.run(
        ytdlp_args(browser) + ["--dump-single-json", "--skip-download", url],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if process.returncode:
        detail = (process.stderr or process.stdout).strip().splitlines()
        raise ToolError("yt-dlp 解析失败：" + (detail[-1] if detail else "未知错误"))
    try:
        return json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise ToolError("yt-dlp 返回了无法解析的元信息") from exc


def subtitle_languages(info: dict[str, Any]) -> tuple[list[str], list[str]]:
    manual = sorted(key for key in (info.get("subtitles") or {}) if key != "danmaku")
    automatic = sorted(key for key in (info.get("automatic_captions") or {}) if key != "danmaku")
    return manual, automatic


def filter_languages(candidates: list[str], requested: str | None) -> list[str]:
    if not requested:
        return candidates
    exact = [lang for lang in candidates if lang.lower() == requested.lower()]
    if exact:
        return exact
    base = requested.lower().split("-")[0]
    return [lang for lang in candidates if lang.lower().split("-")[0] == base]


def choose_languages(info: dict[str, Any], requested: str | None) -> tuple[list[str], list[str]]:
    manual, automatic = subtitle_languages(info)
    if requested:
        selected_manual = filter_languages(manual, requested)
        selected_auto = filter_languages(automatic, requested)
        if not selected_manual and not selected_auto:
            raise NoSubtitles(f"没有匹配语言 {requested} 的字幕轨")
        return selected_manual, selected_auto
    if manual:
        return manual, []
    if automatic:
        preferred = info.get("language") or ""
        selected = filter_languages(automatic, preferred) if preferred else []
        if not selected:
            for candidate in ("zh-CN", "zh-Hans", "zh", "en"):
                selected = filter_languages(automatic, candidate)
                if selected:
                    break
        return [], selected or automatic[:1]
    return [], []


def safe_stem(document: dict[str, Any]) -> str:
    meta = document["video"]
    raw = f"{meta.get('title') or 'video'}-{meta.get('id') or 'subtitle'}"
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", raw).strip(" .")
    return (value or "video-subtitle")[:120]


def plain_text(segments: list[dict[str, Any]]) -> str:
    paragraphs: list[str] = []
    buffer = ""
    for segment in segments:
        text = segment["text"]
        buffer += text
        if len(buffer) >= 180:
            paragraphs.append(buffer)
            buffer = ""
    if buffer:
        paragraphs.append(buffer)
    return "\n\n".join(paragraphs) + ("\n" if paragraphs else "")


def write_outputs(document: dict[str, Any], output_dir: Path) -> dict[str, str]:
    if not document.get("segments"):
        raise ToolError("字幕轨存在，但解析后没有有效文本片段")
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = safe_stem(document)
    paths = {
        "json": output_dir / f"{stem}.segments.json",
        "txt": output_dir / f"{stem}.txt",
        "srt": output_dir / f"{stem}.srt",
        "md": output_dir / f"{stem}.md",
    }
    paths["json"].write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    paths["txt"].write_text(plain_text(document["segments"]), encoding="utf-8")
    srt_blocks = []
    md_lines = [
        f"# {document['video'].get('title') or '视频文字稿'}",
        "",
        f"- 平台：{document['video'].get('platform') or 'generic'}",
        f"- 作者：{document['video'].get('uploader') or '未知'}",
        f"- 来源：{document['source']}",
        f"- 语言：{document.get('language') or '未知'}",
        f"- 原始链接：{document['video'].get('url') or ''}",
        "",
    ]
    for number, segment in enumerate(document["segments"], 1):
        srt_blocks.append(
            f"{number}\n{format_clock(segment['start'], True)} --> {format_clock(segment['end'], True)}\n{segment['text']}"
        )
        md_lines.append(f"[{format_clock(segment['start'])}] {segment['text']}")
        md_lines.append("")
    paths["srt"].write_text("\n\n".join(srt_blocks) + "\n", encoding="utf-8")
    paths["md"].write_text("\n".join(md_lines), encoding="utf-8")
    return {key: str(path.resolve()) for key, path in paths.items()}


def youtube_video_id(url: str) -> str:
    if re.fullmatch(r"[0-9A-Za-z_-]{11}", url):
        return url
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host == "youtu.be":
        candidate = parsed.path.strip("/").split("/")[0]
    elif host.endswith("youtube.com") or host.endswith("youtube-nocookie.com"):
        candidate = parse_qs(parsed.query).get("v", [""])[0]
        if not candidate:
            match = re.match(r"^/(?:shorts|embed|live)/([0-9A-Za-z_-]{11})", parsed.path)
            candidate = match.group(1) if match else ""
    else:
        candidate = ""
    if not re.fullmatch(r"[0-9A-Za-z_-]{11}", candidate or ""):
        raise ToolError("无法从 YouTube 链接中识别视频 ID")
    return candidate


def http_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_youtube_innertube(url: str, language: str | None) -> dict[str, Any]:
    video_id = youtube_video_id(url)
    watch_url = f"https://www.youtube.com/watch?v={video_id}"
    page = http_text(watch_url)
    key_match = re.search(r'"INNERTUBE_API_KEY"\s*:\s*"([^"]+)"', page)
    version_match = re.search(r'"INNERTUBE_CLIENT_VERSION"\s*:\s*"([^"]+)"', page)
    if not key_match or not version_match:
        raise ToolError("YouTube 页面未提供 Innertube 配置")
    payload = {
        "context": {"client": {"clientName": "WEB", "clientVersion": version_match.group(1)}},
        "videoId": video_id,
        "contentCheckOk": True,
        "racyCheckOk": True,
    }
    request = Request(
        f"https://www.youtube.com/youtubei/v1/player?key={key_match.group(1)}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        player = json.loads(response.read().decode("utf-8"))
    captions = (player.get("captions") or {}).get("playerCaptionsTracklistRenderer") or {}
    tracks = captions.get("captionTracks") or []
    if not tracks:
        raise NoSubtitles("YouTube 没有可用字幕轨")
    candidates = tracks
    if language:
        candidates = [track for track in tracks if track.get("languageCode", "").lower() == language.lower()]
        if not candidates:
            base = language.lower().split("-")[0]
            candidates = [track for track in tracks if track.get("languageCode", "").lower().split("-")[0] == base]
        if not candidates:
            raise NoSubtitles(f"YouTube 没有匹配语言 {language} 的字幕轨")
    else:
        manual = [track for track in tracks if track.get("kind") != "asr"]
        candidates = manual or tracks
    track = candidates[0]
    base_url = track.get("baseUrl")
    if not base_url:
        raise ToolError("YouTube 字幕轨缺少下载地址")
    transcript_url = base_url + ("&" if "?" in base_url else "?") + "fmt=json3"
    transcript = json.loads(http_text(transcript_url))
    segments = parse_json3(transcript)
    if not segments:
        raise ToolError("YouTube Innertube 字幕内容为空或格式不受支持")
    details = player.get("videoDetails") or {}
    meta = video_meta({**details, "id": video_id, "webpage_url": watch_url, "uploader": details.get("author")}, "youtube", url)
    return make_document(meta, "innertube-automatic" if track.get("kind") == "asr" else "innertube-manual", track.get("languageCode") or "", segments)


def fetch_ytdlp_subtitles(url: str, output_dir: Path, language: str | None, browser: str | None) -> dict[str, Any]:
    info = run_ytdlp_info(url, browser)
    manual, automatic = choose_languages(info, language)
    languages = list(dict.fromkeys(manual + automatic))
    if not languages:
        raise NoSubtitles("没有人工字幕或自动字幕轨；下一步应提取音轨并转写")
    platform = detect_platform(url)
    with tempfile.TemporaryDirectory(prefix="video-subs-", dir=output_dir) as temp:
        command = ytdlp_args(browser) + [
            "--skip-download",
            "--write-subs",
            "--write-auto-subs",
            "--sub-langs",
            ",".join(languages),
            "--sub-format",
            "json3/vtt/srt/ttml/dfxp/srv3/best",
            "-o",
            str(Path(temp) / "source.%(ext)s"),
            url,
        ]
        process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if process.returncode:
            detail = (process.stderr or process.stdout).strip().splitlines()
            raise ToolError("yt-dlp 字幕下载失败：" + (detail[-1] if detail else "未知错误"))
        candidates = [path for path in Path(temp).iterdir() if path.suffix.lower() in SUBTITLE_EXTS]
        extension_rank = {".json3": 0, ".vtt": 1, ".srt": 2, ".ttml": 3, ".dfxp": 4, ".srv3": 5, ".xml": 6}
        candidates.sort(key=lambda path: (0 if path.stem.split(".")[-1] in manual else 1, extension_rank.get(path.suffix.lower(), 9)))
        errors: list[str] = []
        for candidate in candidates:
            try:
                segments = parse_subtitle_file(candidate)
            except (ToolError, ValueError, ET.ParseError, json.JSONDecodeError) as exc:
                errors.append(str(exc))
                continue
            if not segments:
                continue
            lang = candidate.stem.split(".")[-1]
            source = "yt-dlp-manual" if lang in manual else "yt-dlp-automatic"
            return make_document(video_meta(info, platform, url), source, lang, segments)
    detail = f"：{errors[-1]}" if errors else ""
    raise ToolError("字幕已下载，但没有可解析的字幕文件" + detail)


def cmd_probe(args: argparse.Namespace) -> dict[str, Any]:
    url = normalize_url(args.url)
    info = run_ytdlp_info(url, args.browser)
    manual, automatic = subtitle_languages(info)
    meta = video_meta(info, detect_platform(url), url)
    return {
        "ok": True,
        **meta,
        "duration": format_clock(meta["duration_s"]),
        "has_subtitles": bool(manual or automatic),
        "manual_subtitles": manual,
        "automatic_captions": automatic,
        "next": "fetch" if manual or automatic else "audio",
    }


def cmd_fetch(args: argparse.Namespace) -> dict[str, Any]:
    url = normalize_url(args.url)
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    platform = detect_platform(url)
    warnings: list[str] = []
    document: dict[str, Any] | None = None
    if platform == "youtube" and not args.no_innertube:
        try:
            document = fetch_youtube_innertube(url, args.lang)
        except (ToolError, OSError, ValueError, json.JSONDecodeError) as exc:
            warnings.append(f"YouTube Innertube 未取到字幕，已回退 yt-dlp：{exc}")
    if document is None:
        document = fetch_ytdlp_subtitles(url, output_dir, args.lang, args.browser)
    paths = write_outputs(document, output_dir)
    return {
        "ok": True,
        "platform": platform,
        "source": document["source"],
        "language": document["language"],
        "segments": len(document["segments"]),
        "paths": paths,
        "warnings": warnings,
    }


def cmd_audio(args: argparse.Namespace) -> dict[str, Any]:
    url = normalize_url(args.url)
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    command = ytdlp_args(args.browser) + [
        "-f",
        "bestaudio",
        "-o",
        str(output_dir / "%(id)s.%(ext)s"),
        "--print",
        "after_move:filepath",
        url,
    ]
    process = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if process.returncode:
        detail = (process.stderr or process.stdout).strip().splitlines()
        raise ToolError("音轨下载失败：" + (detail[-1] if detail else "未知错误"))
    audio = ""
    for line in reversed(process.stdout.splitlines()):
        candidate = Path(line.strip())
        if candidate.is_file():
            audio = str(candidate.resolve())
            break
    if not audio:
        raise ToolError("yt-dlp 完成后未找到音轨文件")
    return {"ok": True, "audio": audio, "bytes": Path(audio).stat().st_size, "next": "transcribe_then_normalize"}


def cmd_normalize(args: argparse.Namespace) -> dict[str, Any]:
    source_path = Path(args.input).expanduser().resolve()
    if not source_path.is_file():
        raise ToolError(f"找不到输入文件：{source_path}")
    segments = parse_subtitle_file(source_path)
    if not segments:
        raise ToolError("输入文件中没有可识别的字幕或转写片段")
    duration = args.duration if args.duration is not None else int(max(segment["end"] for segment in segments))
    meta = {
        "id": args.video_id or "",
        "title": args.title or source_path.stem,
        "uploader": args.uploader or "",
        "duration_s": duration,
        "url": args.url or "",
        "platform": args.platform,
    }
    document = make_document(meta, args.source, args.lang or "", segments)
    paths = write_outputs(document, Path(args.output_dir).expanduser().resolve())
    return {"ok": True, "source": args.source, "segments": len(segments), "paths": paths}


def cmd_export(args: argparse.Namespace) -> dict[str, Any]:
    source_path = Path(args.input).expanduser().resolve()
    document = json.loads(source_path.read_text(encoding="utf-8-sig"))
    if not isinstance(document.get("segments"), list):
        raise ToolError("输入不是统一 segment JSON")
    document["segments"] = normalize_segments(document["segments"])
    paths = write_outputs(document, Path(args.output_dir).expanduser().resolve())
    return {"ok": True, "segments": len(document["segments"]), "paths": paths}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="通用视频字幕提取、归一化与导出")
    subparsers = parser.add_subparsers(dest="command", required=True)

    probe = subparsers.add_parser("probe", help="探测视频元信息和字幕轨")
    probe.add_argument("url")
    probe.add_argument("--browser", choices=["chrome", "edge", "firefox"])
    probe.set_defaults(handler=cmd_probe)

    fetch = subparsers.add_parser("fetch", help="提取字幕并输出 JSON/TXT/SRT/MD")
    fetch.add_argument("url")
    fetch.add_argument("output_dir")
    fetch.add_argument("--lang")
    fetch.add_argument("--browser", choices=["chrome", "edge", "firefox"])
    fetch.add_argument("--no-innertube", action="store_true")
    fetch.set_defaults(handler=cmd_fetch)

    audio = subparsers.add_parser("audio", help="仅下载音轨供 ASR 使用")
    audio.add_argument("url")
    audio.add_argument("output_dir")
    audio.add_argument("--browser", choices=["chrome", "edge", "firefox"])
    audio.set_defaults(handler=cmd_audio)

    normalize = subparsers.add_parser("normalize", help="把 ASR/SRT/VTT/Whisper JSON 归一化并导出")
    normalize.add_argument("input")
    normalize.add_argument("output_dir")
    normalize.add_argument("--source", default="unknown")
    normalize.add_argument("--platform", default="generic")
    normalize.add_argument("--lang")
    normalize.add_argument("--title")
    normalize.add_argument("--url")
    normalize.add_argument("--video-id")
    normalize.add_argument("--uploader")
    normalize.add_argument("--duration", type=int)
    normalize.set_defaults(handler=cmd_normalize)

    export = subparsers.add_parser("export", help="从统一 segment JSON 重新导出 TXT/SRT/MD")
    export.add_argument("input")
    export.add_argument("output_dir")
    export.set_defaults(handler=cmd_export)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = args.handler(args)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except NoSubtitles as exc:
        print(json.dumps({"ok": False, "error_code": exc.code, "error": str(exc), "next": "audio"}, ensure_ascii=False))
        return 2
    except (ToolError, OSError, ValueError, ET.ParseError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error_code": "tool_error", "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
