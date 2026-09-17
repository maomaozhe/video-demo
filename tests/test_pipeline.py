import unittest
import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from video_demo.pipeline import scene_segments, normalize_candidate
from video_demo.mvp import analyze_full
from scripts.validate_run import validate_run
from scripts.reconcile_run import reconcile


class PipelineTests(unittest.TestCase):
    def test_long_scene_overlaps_and_short_scene_ends_at_boundary(self):
        self.assertEqual(scene_segments([(0, 52000), (52000, 57000)], 20000, 2000),
                         [(0, 20000, 0), (18000, 38000, 0), (36000, 52000, 0),
                          (52000, 57000, 1)])

    def test_candidate_requires_real_frame_and_person_detection(self):
        frames = {"F1": {"timestamp_ms": 1000, "image": "evidence/F1.jpg"},
                  "F2": {"timestamp_ms": 1500, "image": "evidence/F2.jpg"}}
        tracks = {"S0_T1": {"person_id": "P1", "frame_ids": ["F1"]}}
        candidate = {"start_ms": 0, "end_ms": 2000, "actor_track_id": "S0_T1",
                     "action": "搬运箱子", "status": "已完成", "evidence_frame_ids": ["F1", "F2"]}
        event = normalize_candidate(candidate, frames, tracks, 5000)
        self.assertEqual(event["person_id"], "P1")
        self.assertEqual([x["frame_id"] for x in event["evidence"]], ["F1"])
        self.assertEqual(event["status"], "无法判断")
        self.assertEqual(event["proposed_status"], "已完成")
        self.assertTrue(event["review_required"])

        candidate["completion_evidence"] = {"frame_id": "F1", "description": "结果可见"}
        self.assertEqual(normalize_candidate(candidate, frames, tracks, 5000)["status"], "无法判断")

        candidate["evidence_frame_ids"] = ["F404"]
        self.assertIsNone(normalize_candidate(candidate, frames, tracks, 5000))

    def test_unverified_actor_is_not_bound_to_a_person(self):
        frames = {"F1": {"timestamp_ms": 1000, "image": "evidence/F1.jpg"}}
        candidate = {"start_ms": 0, "end_ms": 2000, "actor_track_id": "unknown",
                     "action": "站立", "status": "观察到", "evidence_frame_ids": ["F1"]}
        event = normalize_candidate(candidate, frames, {}, 5000)
        self.assertIsNone(event["person_id"])
        self.assertTrue(event["review_required"])

    def test_uncalibrated_track_requires_event_review(self):
        frames = {"F1": {"timestamp_ms": 1000, "image": "evidence/F1.jpg"}}
        tracks = {"S0_T1": {"person_id": "P1", "frame_ids": ["F1"],
                            "review_required": True}}
        event = normalize_candidate({"start_ms": 0, "end_ms": 2000,
                                     "actor_track_id": "S0_T1", "action": "搬运",
                                     "status": "观察到", "evidence_frame_ids": ["F1"]},
                                    frames, tracks, 5000)
        self.assertTrue(event["review_required"])

    def test_model_cannot_invent_a_transcript_quote(self):
        frames = {"F1": {"timestamp_ms": 1000, "image": "evidence/F1.jpg"}}
        candidate = {"start_ms": 0, "end_ms": 2000, "action": "拿起物品",
                     "evidence_frame_ids": ["F1"], "evidence_text_span": "已经完成"}
        event = normalize_candidate(candidate, frames, {}, 5000, [])
        self.assertIsNone(event["evidence_text_span"])
        self.assertTrue(event["review_required"])

    def test_full_pipeline_emits_track_evidence_and_manifest(self):
        class FakeModel:
            model_id = "test-model"

            def extract(self, frames, tracks, transcript, tasks):
                return [{"start_ms": 0, "end_ms": 1500, "actor_track_id": "S0_T1",
                         "action": "人物经过画面", "status": "观察到",
                         "evidence_frame_ids": [frames[0].frame_id]}]

            def describe(self, frames):
                return "画面中有人在室内移动。"

            def synthesize(self, segments):
                return "视频中有人在室内移动，身份未确认。"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "clip.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                            "color=c=blue:s=160x90:r=10", "-t", "2", "-c:v", "mpeg4",
                            "-y", str(video)], check=True, capture_output=True)
            output = root / "run"
            track = {"track_id": "S0_T1", "scene_id": 0, "start_ms": 0,
                     "end_ms": 1800, "detections": [], "frame_ids": ["F000000500"]}
            with patch("video_demo.mvp.detect_scenes", return_value=[(0, 2000)]), \
                 patch("video_demo.tracking.track_people", return_value=[track]):
                result = analyze_full(video, output, FakeModel(), detector_path="unused",
                                      whisper_path="unused")
            self.assertEqual(result["events"][0]["person_id"], "P1")
            self.assertEqual(result["people"][0]["id"], "P1")
            self.assertTrue((output / result["events"][0]["evidence"][0]["image"]).is_file())
            self.assertEqual(json.loads((output / "tracks.json").read_text(encoding="utf-8"))
                             ["association"], "unavailable")
            self.assertTrue((output / "manifest.json").is_file())
            self.assertIn("视频中有人", (output / "narrative.md").read_text(encoding="utf-8"))
            self.assertEqual(validate_run(output)["errors"], [])
            self.assertEqual(reconcile(output)["filtered_evidence"], 0)
            self.assertEqual(reconcile(output)["filtered_evidence"], 0)
            self.assertEqual(validate_run(output)["errors"], [])

    def test_no_person_and_no_speech_is_explicit(self):
        class FakeModel:
            model_id = "test-model"

            def extract(self, frames, tracks, transcript, tasks):
                return [{"start_ms": 0, "end_ms": 1000, "actor_track_id": None,
                         "action": "画面中有物体", "status": "观察到",
                         "evidence_frame_ids": [frames[0].frame_id]}]

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "clip.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                            "color=c=blue:s=160x90:r=10", "-t", "1", "-c:v", "mpeg4",
                            "-y", str(video)], check=True, capture_output=True)
            output = root / "run"
            with patch("video_demo.mvp.detect_scenes", return_value=[(0, 1000)]), \
                 patch("video_demo.tracking.track_people", return_value=[]):
                result = analyze_full(video, output, FakeModel(), detector_path="unused",
                                      whisper_path="unused")
            self.assertEqual(result["people"], [])
            self.assertIsNone(result["events"][0]["person_id"])
            self.assertFalse((output / "transcript.json").exists())


if __name__ == "__main__":
    unittest.main()
