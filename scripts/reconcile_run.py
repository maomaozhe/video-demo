"""Apply conservative evidence/review corrections to an already completed run."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from video_demo.identity import IdentityResult, ReviewCandidate, prioritize_reviews


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def reconcile(root: Path) -> dict:
    manifest_path = root / "manifest.json"
    previous = _read(manifest_path).get("reconciliation")
    if previous:
        return {"filtered_evidence": previous["filtered_evidence"],
                "review_candidates": len(_read(root / "tracks.json")["review_candidates"])}
    result_path = root / "result.json"
    tracks_path = root / "tracks.json"
    result, tracks = _read(result_path), _read(tracks_path)
    if not result["complete"]:
        raise ValueError("Only completed runs can be reconciled")
    for filename in ("result.json", "tracks.json"):
        backup = root / f"{filename}.before-reconcile"
        if not backup.exists():
            shutil.copy2(root / filename, backup)
    track_by_id = {item["track_id"]: item for item in tracks["tracklets"]}
    mapping = {track_id: track["person_id"] for track_id, track in track_by_id.items()}
    association = IdentityResult(mapping, [ReviewCandidate(**item)
                                           for item in tracks["review_candidates"]])
    scenes = {track_id: track["scene_id"] for track_id, track in track_by_id.items()}
    tracks["review_candidates"] = [item.__dict__ for item in prioritize_reviews(association, scenes)]
    filtered = 0
    for event in result["events"]:
        if event["person_id"]:
            track = track_by_id[event["actor_track_id"]]
            before = len(event["evidence"])
            event["evidence"] = [item for item in event["evidence"]
                                 if item["frame_id"] in track["frame_ids"]]
            if not event["evidence"]:
                raise ValueError(f"No actor evidence remains for {event['id']}")
            filtered += before - len(event["evidence"])
            event["review_required"] = event["review_required"] or track["review_required"]
    _write(result_path, result)
    _write(tracks_path, tracks)
    _write(root / "events.partial.json", result["events"])
    manifest = _read(manifest_path)
    manifest["reconciliation"] = {"timestamp": datetime.now(timezone.utc).isoformat(),
                                   "reason": "actor-frame evidence and bounded review queue",
                                   "filtered_evidence": filtered}
    _write(manifest_path, manifest)
    with (root / "run.log").open("a", encoding="utf-8") as log:
        log.write(f"Reconciled actor evidence: removed {filtered} frames; "
                  f"retained {len(tracks['review_candidates'])} review candidates\n")
    return {"filtered_evidence": filtered,
            "review_candidates": len(tracks["review_candidates"])}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    print(json.dumps(reconcile(parser.parse_args().run), ensure_ascii=False, indent=2))
