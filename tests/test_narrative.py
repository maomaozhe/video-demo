import json
import tempfile
import unittest
from pathlib import Path

from video_demo.narrative import generate_narrative
from video_demo.cli import main
from unittest.mock import patch


class FakeNarrator:
    model_id = "test-vlm"

    def __init__(self):
        self.segments = []
        self.synthesis_input = None

    def describe(self, frames):
        self.segments.append([frame.timestamp_ms for frame in frames])
        return "一名穿深色衣服的人在地面操作积木。"

    def synthesize(self, segments):
        self.synthesis_input = segments
        return "视频中多名人物在室内操作积木；无法确认跨片段是否为同一人。"


class NarrativeTests(unittest.TestCase):
    def test_synthesizes_long_video_through_short_stage_summaries(self):
        class LimitedSynthesis(FakeNarrator):
            def __init__(self):
                super().__init__()
                self.calls = []

            def synthesize(self, segments):
                self.calls.append(len(segments))
                if len(segments) > 4:
                    raise RuntimeError("Full-video synthesis reached the output token limit")
                return "根据相邻片段，儿童在室内搭建积木；跨片段身份未确认。"

        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary)
            (run / "evidence").mkdir()
            frames = {}
            for index in range(11):
                ms = index * 20000 + 500
                frame_id = f"F{ms}"
                (run / "evidence" / f"{frame_id}.jpg").write_bytes(b"jpeg")
                frames[frame_id] = {"timestamp_ms": ms, "image": f"evidence/{frame_id}.jpg"}
            (run / "frames.json").write_text(json.dumps(frames), encoding="utf-8")
            (run / "result.json").write_text('{"video":{"duration_ms":220000},"complete":true,"events":[]}', encoding="utf-8")
            (run / "manifest.json").write_text('{"input":"/data/video.mp4"}', encoding="utf-8")
            model = LimitedSynthesis()

            narrative = generate_narrative(run, model)

            self.assertEqual(model.calls, [3, 3, 3, 2, 4])
            self.assertEqual(len(narrative["segments"]), 11)
            self.assertIn("跨片段身份未确认", narrative["overall"])

    def test_long_segment_retries_in_smaller_frame_groups(self):
        class LimitedNarrator(FakeNarrator):
            def describe(self, frames):
                if len(frames) > 2:
                    raise RuntimeError("Model description reached the output token limit")
                self.segments.append([frame.timestamp_ms for frame in frames])
                return f"看到 {frames[0].timestamp_ms} 至 {frames[-1].timestamp_ms} 毫秒的动作。"

        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary)
            (run / "evidence").mkdir()
            frames = {}
            for ms in (2500, 7500, 12500, 17500):
                frame_id = f"F{ms}"
                (run / "evidence" / f"{frame_id}.jpg").write_bytes(b"jpeg")
                frames[frame_id] = {"timestamp_ms": ms, "image": f"evidence/{frame_id}.jpg"}
            (run / "frames.json").write_text(json.dumps(frames), encoding="utf-8")
            (run / "result.json").write_text('{"video":{"duration_ms":20000},"complete":true,"events":[]}', encoding="utf-8")
            (run / "manifest.json").write_text('{"input":"/data/video.mp4"}', encoding="utf-8")
            model = LimitedNarrator()

            narrative = generate_narrative(run, model)

            self.assertEqual(model.segments, [[2500, 7500], [12500, 17500]])
            self.assertIn("2500 至 7500", narrative["segments"][0]["description"])
            self.assertIn("12500 至 17500", narrative["segments"][0]["description"])

    def test_cli_can_add_narrative_to_existing_run_without_reanalyzing_video(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary)
            (run / "evidence").mkdir()
            (run / "evidence" / "F1.jpg").write_bytes(b"jpeg")
            (run / "frames.json").write_text(json.dumps({"F1": {"timestamp_ms": 500,
                "image": "evidence/F1.jpg"}}), encoding="utf-8")
            (run / "result.json").write_text(json.dumps({"video": {"duration_ms": 1000},
                "complete": True, "events": []}), encoding="utf-8")
            (run / "manifest.json").write_text('{"input":"/data/video.mp4"}', encoding="utf-8")
            with patch("video_demo.vlm.QwenDescriber", return_value=FakeNarrator()):
                self.assertEqual(main(["narrate", "--run", str(run), "--model", "unused"]), 0)
            self.assertTrue((run / "narrative.md").is_file())

    def test_generates_evidence_linked_segments_and_one_overall_description(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary)
            evidence = run / "evidence"
            evidence.mkdir()
            frames = {}
            for ms in range(500, 25500, 1000):
                frame_id = f"F{ms:09d}"
                (evidence / f"{frame_id}.jpg").write_bytes(b"jpeg")
                frames[frame_id] = {"timestamp_ms": ms, "image": f"evidence/{frame_id}.jpg"}
            (run / "frames.json").write_text(json.dumps(frames), encoding="utf-8")
            (run / "result.json").write_text(json.dumps({"video": {"duration_ms": 25000},
                "complete": True, "events": [{"start_ms": 1000, "end_ms": 18000, "action": "搭建积木"}]}), encoding="utf-8")
            (run / "manifest.json").write_text(json.dumps({"input": "/data/video.mp4"}), encoding="utf-8")
            model = FakeNarrator()

            result = generate_narrative(run, model)

            self.assertEqual(len(result["segments"]), 2)
            self.assertEqual(model.segments[0], [2500, 7500, 12500, 17500])
            self.assertEqual(model.segments[1], [20500, 21500, 23500, 24500])
            self.assertEqual(model.synthesis_input, result["segments"])
            self.assertIn("全片综合描述", (run / "narrative.md").read_text(encoding="utf-8"))
            self.assertIn("0.0–20.0 秒", (run / "narrative.md").read_text(encoding="utf-8"))
            self.assertEqual(json.loads((run / "narrative.json").read_text(encoding="utf-8"))["segments"], result["segments"])
            self.assertFalse((run / "narrative.partial.json").exists())

    def test_can_preselect_shorter_groups_for_dense_scenes(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary)
            (run / "evidence").mkdir()
            frames = {}
            for ms in (2500, 7500, 12500, 17500):
                frame_id = f"F{ms}"
                (run / "evidence" / f"{frame_id}.jpg").write_bytes(b"jpeg")
                frames[frame_id] = {"timestamp_ms": ms, "image": f"evidence/{frame_id}.jpg"}
            (run / "frames.json").write_text(json.dumps(frames), encoding="utf-8")
            (run / "result.json").write_text('{"video":{"duration_ms":20000},"complete":true,"events":[]}', encoding="utf-8")
            (run / "manifest.json").write_text('{"input":"/data/video.mp4"}', encoding="utf-8")
            model = FakeNarrator()

            narrative = generate_narrative(run, model, frame_group_size=2)

            self.assertEqual(model.segments, [[2500, 7500], [12500, 17500]])
            self.assertEqual(len(narrative["segments"][0]["frame_ids"]), 4)

    def test_resume_keeps_completed_segments_and_rejects_missing_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary)
            (run / "evidence").mkdir()
            (run / "result.json").write_text(json.dumps({"video": {"duration_ms": 1000}, "complete": True,
                                                          "events": []}), encoding="utf-8")
            (run / "manifest.json").write_text('{"input":"/data/video.mp4"}', encoding="utf-8")
            (run / "frames.json").write_text(json.dumps({"F1": {"timestamp_ms": 500,
                "image": "evidence/missing.jpg"}}), encoding="utf-8")
            with self.assertRaises(ValueError):
                generate_narrative(run, FakeNarrator())


if __name__ == "__main__":
    unittest.main()
