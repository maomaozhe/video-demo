import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from video_demo.analyze import analyze_video, segment_ranges


class FakeDescriber:
    def __init__(self):
        self.calls = []

    def describe(self, frames):
        self.calls.append(frames)
        return "画面中出现红色背景。"


class AnalyzeTests(unittest.TestCase):
    def test_segment_ranges_cover_duration_without_gaps(self):
        self.assertEqual(segment_ranges(25001, 10000), [(0, 10000), (10000, 20000), (20000, 25001)])

    def test_writes_result_summary_and_real_evidence_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "sample.mp4"
            output = root / "result"
            subprocess.run(
                ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=160x90:r=10",
                 "-t", "2", "-c:v", "mpeg4", "-y", str(video)],
                check=True, capture_output=True,
            )
            describer = FakeDescriber()

            analyze_video(video, output, describer, frames_per_segment=2)

            data = json.loads((output / "result.json").read_text(encoding="utf-8"))
            self.assertEqual(data["video"]["duration_ms"], 2000)
            self.assertEqual(data["events"][0]["action"], "画面中出现红色背景。")
            self.assertIsNone(data["events"][0]["person_id"])
            self.assertEqual(len(describer.calls[0]), 2)
            for evidence in data["events"][0]["evidence"]:
                self.assertTrue((output / evidence["image"]).is_file())
            self.assertIn("人物关联尚未启用", data["warnings"])
            self.assertIn("画面中出现红色背景", (output / "summary.md").read_text(encoding="utf-8"))

    def test_partial_run_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "sample.mp4"
            subprocess.run(
                ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=160x90:r=10",
                 "-t", "2", "-c:v", "mpeg4", "-y", str(video)],
                check=True, capture_output=True,
            )
            output = root / "result"

            analyze_video(video, output, FakeDescriber(), segment_ms=1000, max_segments=1)

            data = json.loads((output / "result.json").read_text(encoding="utf-8"))
            self.assertFalse(data["complete"])
            self.assertEqual(len(data["events"]), 1)
            self.assertTrue(any("部分" in warning for warning in data["warnings"]))


if __name__ == "__main__":
    unittest.main()
