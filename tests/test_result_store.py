import json
import tempfile
import unittest
from pathlib import Path

from video_demo.result_store import ResultStore


def make_run(root: Path, name: str, sha: str, *, complete: bool = True, created_at: str = "2026-09-17T10:00:00Z", pipeline: bool = False) -> Path:
    directory = root / name
    (directory / "evidence").mkdir(parents=True)
    (directory / "evidence" / "F1.jpg").write_bytes(b"jpeg bytes")
    (directory / "result.json").write_text(json.dumps({
        "schema_version": "1.0", "complete": complete,
        "video": {"duration_ms": 2000}, "people": [],
        "events": [{"id": "E1", "start_ms": 0, "end_ms": 2000, "action": "搭建积木",
                    "evidence": [{"timestamp_ms": 1000, "frame_id": "F1", "image": "evidence/F1.jpg"}]}],
        "warnings": [],
    }), encoding="utf-8")
    (directory / "summary.md").write_text("# 摘要\n\n- 搭建积木\n", encoding="utf-8")
    manifest = {
        "input": "/data/example.mp4", "input_sha256": sha,
        "model": "Qwen3-VL-8B", "created_at": created_at,
    }
    if pipeline:
        manifest.pop("model")
        manifest["models"] = {"vlm": "Qwen3-VL-8B", "detector": "RT-DETR"}
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return directory


class ResultStoreTests(unittest.TestCase):
    def test_labels_runs_and_prefers_full_pipeline_over_newer_baseline(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sha = "a" * 64
            current = make_run(root, "current", sha, pipeline=True, created_at="2026-09-17T10:00:00Z")
            (current / "tracks.json").write_text("{}", encoding="utf-8")
            make_run(root, "baseline", sha, created_at="2026-09-17T11:00:00Z")
            make_run(root, "smoke", sha, complete=False, pipeline=True, created_at="2026-09-17T12:00:00Z")

            store = ResultStore(root)
            video = store.list_videos()[0]
            self.assertEqual(video["preferred_run_id"], "current")
            self.assertEqual({run["id"]: run["kind"] for run in video["runs"]},
                             {"current": "current", "baseline": "baseline", "smoke": "test"})
            self.assertIn("tracks.json", store.get_run("current")["downloads"])
            self.assertNotIn("tracks.json", store.get_run("baseline")["downloads"])

    def test_groups_runs_by_video_and_prefers_latest_complete_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sha = "a" * 64
            make_run(root, "full", sha, created_at="2026-09-17T10:00:00Z")
            make_run(root, "partial", sha, complete=False, created_at="2026-09-17T11:00:00Z")
            make_run(root, "other", "b" * 64)

            videos = ResultStore(root).list_videos()

            self.assertEqual(len(videos), 2)
            video = next(item for item in videos if item["id"] == sha)
            self.assertEqual(video["name"], "example.mp4")
            self.assertEqual({run["id"] for run in video["runs"]}, {"full", "partial"})
            self.assertEqual(video["preferred_run_id"], "full")

    def test_skips_incomplete_or_corrupt_run_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_run(root, "valid", "a" * 64)
            (root / "missing").mkdir()
            corrupt = make_run(root, "corrupt", "b" * 64)
            (corrupt / "result.json").write_text("{broken", encoding="utf-8")

            videos = ResultStore(root).list_videos()

            self.assertEqual([run["id"] for video in videos for run in video["runs"]], ["valid"])

    def test_only_serves_evidence_referenced_by_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = make_run(root, "valid", "a" * 64)
            (run / "evidence" / "secret.jpg").write_bytes(b"secret")
            store = ResultStore(root)

            self.assertEqual(store.read_evidence("valid", "F1.jpg"), b"jpeg bytes")
            with self.assertRaises(KeyError):
                store.read_evidence("valid", "secret.jpg")
            with self.assertRaises(KeyError):
                store.read_evidence("valid", "../manifest.json")
            with self.assertRaises(KeyError):
                store.get_run("../valid")

    def test_serves_narrative_sample_frames_but_not_unreferenced_images(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = make_run(root, "valid", "a" * 64)
            (run / "evidence" / "F2.jpg").write_bytes(b"second frame")
            (run / "evidence" / "secret.jpg").write_bytes(b"private frame")
            (run / "frames.json").write_text(json.dumps({"F2": {"timestamp_ms": 1500,
                "image": "evidence/F2.jpg"}}), encoding="utf-8")
            (run / "narrative.json").write_text(json.dumps({"segments": [
                {"frame_ids": ["F2"]}]}), encoding="utf-8")

            store = ResultStore(root)
            self.assertEqual(store.read_evidence("valid", "F2.jpg"), b"second frame")
            with self.assertRaises(KeyError):
                store.read_evidence("valid", "secret.jpg")

    def test_returns_original_summary_and_json_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_run(root, "valid", "a" * 64)
            store = ResultStore(root)

            self.assertIn("搭建积木", store.get_run("valid")["summary"])
            self.assertEqual(json.loads(store.read_file("valid", "result.json"))["events"][0]["id"], "E1")
            with self.assertRaises(KeyError):
                store.read_file("valid", "../../etc/passwd")

    def test_serves_optional_detailed_report_only_when_present(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = make_run(root, "valid", "a" * 64)
            store = ResultStore(root)
            self.assertIsNone(store.get_run("valid")["narrative"])
            with self.assertRaises(KeyError):
                store.read_file("valid", "narrative.md")
            (run / "narrative.md").write_text("# 视频详细描述\n\n可见人物在搭建积木。", encoding="utf-8")
            self.assertIn("可见人物", store.get_run("valid")["narrative"])
            self.assertIn("narrative.md", store.get_run("valid")["downloads"])

    def test_malformed_event_cannot_crash_evidence_endpoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = make_run(root, "valid", "a" * 64)
            result_path = run / "result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            result["events"] = [None]
            result_path.write_text(json.dumps(result), encoding="utf-8")

            with self.assertRaises(KeyError):
                ResultStore(root).read_evidence("valid", "F1.jpg")

    def test_symlinked_result_file_is_not_served(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = make_run(root, "valid", "a" * 64)
            outside = root / "outside.json"
            outside.write_bytes((run / "result.json").read_bytes())
            (run / "result.json").unlink()
            try:
                (run / "result.json").symlink_to(outside)
            except OSError:
                self.skipTest("symlinks unavailable on this host")

            self.assertEqual(ResultStore(root).list_videos(), [])


if __name__ == "__main__":
    unittest.main()
