import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from video_demo.cli import main


class FakeDescriber:
    model_id = "fake"

    def __init__(self, model_id):
        pass

    def describe(self, frames):
        return "画面中有红色背景。"


class FailingDescriber(FakeDescriber):
    def describe(self, frames):
        raise RuntimeError("model failed")


class CliTests(unittest.TestCase):
    def test_partial_reid_configuration_exits_as_input_error(self):
        with self.assertRaises(SystemExit) as raised:
            main(["analyze", "unused.mp4", "--output", "unused", "--reid-weights", "weights.pth"])
        self.assertEqual(raised.exception.code, 2)

    def test_missing_video_exits_with_input_error(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(SystemExit) as raised:
                main(["analyze", str(Path(directory) / "missing.mp4"),
                      "--output", str(Path(directory) / "output")])
            self.assertEqual(raised.exception.code, 2)

    def test_cli_writes_results_with_injected_model(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "sample.mp4"
            subprocess.run(
                ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=160x90:r=10",
                 "-t", "1", "-c:v", "mpeg4", "-y", str(video)],
                check=True, capture_output=True,
            )
            output = root / "output"
            with patch("video_demo.vlm.QwenDescriber", FakeDescriber):
                code = main(["analyze", str(video), "--output", str(output)])

            self.assertEqual(code, 0)
            self.assertEqual(json.loads((output / "result.json").read_text(encoding="utf-8"))["events"][0]["action"],
                             "画面中有红色背景。")
            self.assertTrue((output / "manifest.json").is_file())

    def test_model_failure_writes_run_log(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "sample.mp4"
            subprocess.run(
                ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=160x90:r=10",
                 "-t", "1", "-c:v", "mpeg4", "-y", str(video)],
                check=True, capture_output=True,
            )
            output = root / "output"
            with patch("video_demo.vlm.QwenDescriber", FailingDescriber):
                code = main(["analyze", str(video), "--output", str(output)])

            self.assertEqual(code, 3)
            self.assertIn("model failed", (output / "run.log").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
