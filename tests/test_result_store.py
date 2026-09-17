import json
import tempfile
import unittest
from pathlib import Path

from video_demo.result_store import ResultStore


def make_run(root: Path, name: str, sha: str, *, complete: bool = True, created_at: str = "2026-09-17T10:00:00Z") -> Path:
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
    (directory / "manifest.json").write_text(json.dumps({
        "input": "/data/example.mp4", "input_sha256": sha,
        "model": "Qwen3-VL-8B", "created_at": created_at,
    }), encoding="utf-8")
    return directory


class ResultStoreTests(unittest.TestCase):
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

    def test_returns_original_summary_and_json_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            make_run(root, "valid", "a" * 64)
            store = ResultStore(root)

            self.assertIn("搭建积木", store.get_run("valid")["summary"])
            self.assertEqual(json.loads(store.read_file("valid", "result.json"))["events"][0]["id"], "E1")
            with self.assertRaises(KeyError):
                store.read_file("valid", "../../etc/passwd")

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
