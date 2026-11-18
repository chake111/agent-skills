from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).parents[1] / "scripts" / "video_subtitle.py"
SPEC = importlib.util.spec_from_file_location("video_subtitle", SCRIPT)
vs = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(vs)


def document(platform="generic"):
    return vs.make_document(
        {"id": "abc", "title": "测试视频", "uploader": "作者", "duration_s": 4, "url": "https://example.com/v", "platform": platform},
        "asr",
        "zh",
        [{"start": 0, "end": 2.25, "text": "第一句"}, {"start": 2.25, "end": 4, "text": "第二句"}],
    )


class PlatformTests(unittest.TestCase):
    def test_platform_detection(self):
        cases = {
            "https://youtu.be/abcdefghijk": "youtube",
            "https://www.youtube.com/shorts/abcdefghijk": "youtube",
            "https://www.bilibili.com/video/BV1KwNvzqECx": "bilibili",
            "https://b23.tv/abc": "bilibili",
            "https://www.douyin.com/video/123": "douyin",
            "https://www.xiaohongshu.com/explore/123": "xiaohongshu",
            "https://xhslink.com/a/123": "xiaohongshu",
            "https://vimeo.com/123": "generic",
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(vs.detect_platform(url), expected)

    def test_bilibili_and_youtube_shorthands(self):
        self.assertEqual(vs.normalize_url("BV1KwNvzqECx"), "https://www.bilibili.com/video/BV1KwNvzqECx")
        self.assertEqual(vs.normalize_url("av123"), "https://www.bilibili.com/video/av123")
        self.assertEqual(vs.youtube_video_id(vs.normalize_url("abcdefghijk")), "abcdefghijk")

    def test_youtube_url_variants(self):
        for url in (
            "https://www.youtube.com/watch?v=abcdefghijk",
            "https://youtu.be/abcdefghijk?t=2",
            "https://www.youtube.com/shorts/abcdefghijk",
            "https://www.youtube.com/embed/abcdefghijk",
        ):
            with self.subTest(url=url):
                self.assertEqual(vs.youtube_video_id(url), "abcdefghijk")


class ParserTests(unittest.TestCase):
    def test_srt(self):
        segments = vs.parse_timestamp_blocks("1\n00:00:01,000 --> 00:00:02,500\nHello <b>world</b>\n\n")
        self.assertEqual(segments, [{"start": 1.0, "end": 2.5, "text": "Hello world"}])

    def test_vtt_with_cue_settings(self):
        text = "WEBVTT\n\n00:00:03.000 --> 00:00:05.000 line:90%\n第二句\n"
        self.assertEqual(vs.parse_timestamp_blocks(text)[0]["start"], 3.0)

    def test_asr_with_speaker_and_continuation(self):
        text = "[0:01.000,0:02.500,0] 你好\n继续说一句\n[0:03.000,0:04.000,1] 世界\n"
        segments = vs.parse_asr_text(text)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0]["text"], "你好 继续说一句")

    def test_json3(self):
        data = {"events": [{"tStartMs": 1000, "dDurationMs": 1500, "segs": [{"utf8": "hello\n"}, {"utf8": "world"}]}]}
        self.assertEqual(vs.parse_json3(data), [{"start": 1.0, "end": 2.5, "text": "hello world"}])

    def test_ttml_and_youtube_srv3(self):
        ttml = '<tt xmlns="http://www.w3.org/ns/ttml"><body><p begin="00:00:01.000" end="00:00:02.000">字幕</p></body></tt>'
        srv3 = '<timedtext><body><p t="2000" d="1500"><s>下一句</s></p></body></timedtext>'
        self.assertEqual(vs.parse_xml_subtitles(ttml)[0]["text"], "字幕")
        self.assertEqual(vs.parse_xml_subtitles(srv3)[0]["start"], 2.0)

    def test_danmaku_excluded_and_manual_preferred(self):
        info = {"subtitles": {"danmaku": [], "zh-CN": []}, "automatic_captions": {"en": []}}
        self.assertEqual(vs.choose_languages(info, None), (["zh-CN"], []))
        self.assertEqual(vs.choose_languages(info, "en"), ([], ["en"]))

    def test_timestamp_rounding(self):
        self.assertEqual(vs.format_clock(59.9996, True), "00:01:00,000")


class ProbeTests(unittest.TestCase):
    def test_probe_uses_platform_neutral_fields(self):
        info = {
            "id": "BV1KwNvzqECx",
            "title": "测试视频",
            "uploader": "作者",
            "duration": 4,
            "subtitles": {"zh-CN": []},
            "automatic_captions": {"en": []},
        }
        with patch.object(vs, "run_ytdlp_info", return_value=info):
            result = vs.cmd_probe(argparse.Namespace(url="BV1KwNvzqECx", browser=None))
        self.assertTrue(result["has_subtitles"])
        self.assertEqual(result["manual_subtitles"], ["zh-CN"])
        self.assertEqual(result["automatic_captions"], ["en"])
        self.assertNotIn("has_cc", result)
        self.assertNotIn("cc_langs", result)


class ExportTests(unittest.TestCase):
    def test_all_outputs_and_unified_schema(self):
        with tempfile.TemporaryDirectory() as temp:
            paths = vs.write_outputs(document(), Path(temp))
            self.assertEqual(set(paths), {"json", "txt", "srt", "md"})
            saved = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
            self.assertEqual(saved["segments"][0], {"start": 0.0, "end": 2.25, "text": "第一句"})
            self.assertIn("00:00:00,000 --> 00:00:02,250", Path(paths["srt"]).read_text(encoding="utf-8"))
            self.assertIn("[0:00] 第一句", Path(paths["md"]).read_text(encoding="utf-8"))
            self.assertIn("第一句第二句", Path(paths["txt"]).read_text(encoding="utf-8"))

    def test_whisper_json_cli(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "whisper.json"
            source.write_text(json.dumps({"segments": [{"start": 0, "end": 1.5, "text": "Whisper 文本"}]}), encoding="utf-8")
            out = Path(temp) / "out"
            process = subprocess.run(
                [sys.executable, str(SCRIPT), "normalize", str(source), str(out), "--source", "asr", "--url", "https://example.com/v", "--video-id", "abc", "--uploader", "作者"],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            result = json.loads(process.stdout)
            self.assertTrue(all(Path(path).is_file() for path in result["paths"].values()))
            saved = json.loads(Path(result["paths"]["json"]).read_text(encoding="utf-8"))
            self.assertEqual(saved["video"]["id"], "abc")
            self.assertEqual(saved["video"]["uploader"], "作者")
            self.assertEqual(saved["video"]["url"], "https://example.com/v")


class RoutingTests(unittest.TestCase):
    def args(self, url):
        return argparse.Namespace(url=url, output_dir=self.temp, lang=None, browser=None, no_innertube=False)

    def test_youtube_prefers_innertube(self):
        with tempfile.TemporaryDirectory() as temp:
            self.temp = temp
            with patch.object(vs, "fetch_youtube_innertube", return_value=document("youtube")) as direct, patch.object(vs, "fetch_ytdlp_subtitles") as fallback:
                result = vs.cmd_fetch(self.args("https://youtu.be/abcdefghijk"))
                self.assertTrue(result["ok"])
                direct.assert_called_once()
                fallback.assert_not_called()

    def test_youtube_falls_back_and_bilibili_uses_existing_route(self):
        for url, platform in (("https://youtu.be/abcdefghijk", "youtube"), ("https://b23.tv/abc", "bilibili")):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as temp:
                self.temp = temp
                with patch.object(vs, "fetch_youtube_innertube", side_effect=vs.NoSubtitles("none")), patch.object(vs, "fetch_ytdlp_subtitles", return_value=document(platform)) as fallback:
                    result = vs.cmd_fetch(self.args(url))
                    self.assertEqual(result["platform"], platform)
                    fallback.assert_called_once()


if __name__ == "__main__":
    unittest.main()
