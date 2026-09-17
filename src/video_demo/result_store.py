"""Read completed local analysis runs without exposing arbitrary files."""

import json
from pathlib import Path
import re


_RUN_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_FILE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\.(?:jpg|jpeg|png|webp)\Z", re.IGNORECASE)
_SHA256 = re.compile(r"[0-9a-fA-F]{64}\Z")
_DOWNLOADS = {"result.json", "summary.md", "manifest.json"}
_OPTIONAL_DOWNLOADS = {"tracks.json", "transcript.json"}


class ResultStore:
    def __init__(self, runs_dir: Path):
        self.root = Path(runs_dir).resolve()

    def _directory(self, run_id: str) -> Path:
        if not _RUN_NAME.fullmatch(run_id):
            raise KeyError(run_id)
        directory = self.root / run_id
        if directory.is_symlink() or not directory.is_dir() or directory.resolve().parent != self.root:
            raise KeyError(run_id)
        return directory

    def get_run(self, run_id: str) -> dict:
        directory = self._directory(run_id)
        try:
            for filename in _DOWNLOADS:
                path = directory / filename
                if path.is_symlink() or not path.is_file() or path.resolve().parent != directory:
                    raise ValueError("run file is missing or linked outside")
            result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
            summary = (directory / "summary.md").read_text(encoding="utf-8")
            manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
            if not isinstance(result, dict) or not isinstance(result.get("events"), list):
                raise ValueError("invalid result")
            if not isinstance(result.get("video"), dict) or not isinstance(manifest, dict):
                raise ValueError("invalid metadata")
            if not isinstance(manifest.get("input"), str) or not _SHA256.fullmatch(manifest.get("input_sha256", "")):
                raise ValueError("invalid input identity")
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError) as exc:
            raise KeyError(run_id) from exc
        return {"id": run_id, "video_id": manifest["input_sha256"].lower(),
                "result": result, "summary": summary, "manifest": manifest}

    def list_videos(self) -> list[dict]:
        if not self.root.is_dir():
            return []
        groups: dict[str, dict] = {}
        for directory in self.root.iterdir():
            if not directory.is_dir() or directory.is_symlink():
                continue
            try:
                run = self.get_run(directory.name)
            except KeyError:
                continue
            manifest, result = run["manifest"], run["result"]
            video_id = run["video_id"]
            group = groups.setdefault(video_id, {
                "id": video_id,
                "name": Path(manifest["input"].replace("\\", "/")).name,
                "runs": [],
            })
            group["runs"].append({
                "id": run["id"], "created_at": str(manifest.get("created_at", "")),
                "model": str(manifest.get("model") or manifest.get("models", {}).get("vlm", "")),
                "complete": result.get("complete") is True,
                "event_count": len(result["events"]),
            })
        for group in groups.values():
            group["runs"].sort(key=lambda item: (item["created_at"], item["id"]), reverse=True)
            preferred = next((run for run in group["runs"] if run["complete"]), group["runs"][0])
            group["preferred_run_id"] = preferred["id"]
        return sorted(groups.values(), key=lambda item: item["runs"][0]["created_at"], reverse=True)

    def read_file(self, run_id: str, filename: str) -> bytes:
        if filename not in _DOWNLOADS | _OPTIONAL_DOWNLOADS:
            raise KeyError(filename)
        self.get_run(run_id)
        directory = self._directory(run_id)
        path = directory / filename
        if path.is_symlink() or not path.is_file() or path.resolve().parent != directory:
            raise KeyError(filename)
        return path.read_bytes()

    def read_evidence(self, run_id: str, filename: str) -> bytes:
        if not _FILE_NAME.fullmatch(filename):
            raise KeyError(filename)
        run = self.get_run(run_id)
        expected = f"evidence/{filename}"
        referenced = False
        for event in run["result"]["events"]:
            if not isinstance(event, dict) or not isinstance(event.get("evidence"), list):
                continue
            if any(isinstance(item, dict) and item.get("image") == expected for item in event["evidence"]):
                referenced = True
                break
        if not referenced:
            raise KeyError(filename)
        evidence_dir = self._directory(run_id) / "evidence"
        path = evidence_dir / filename
        if path.is_symlink() or not path.is_file() or path.resolve().parent != evidence_dir.resolve():
            raise KeyError(filename)
        return path.read_bytes()
