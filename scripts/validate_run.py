"""Audit a completed offline run's timeline, person mapping and evidence files."""

import argparse
import json
from pathlib import Path


def validate_run(root: Path) -> dict:
    result = json.loads((root / "result.json").read_text(encoding="utf-8"))
    frames = json.loads((root / "frames.json").read_text(encoding="utf-8"))
    tracks = json.loads((root / "tracks.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    duration = result["video"]["duration_ms"]
    errors = []
    people = {item["id"]: item for item in result["people"]}
    track_by_id = {item["track_id"]: item for item in tracks["tracklets"]}
    if len(people) != len(result["people"]):
        errors.append("duplicate person ID")
    if len(track_by_id) != len(tracks["tracklets"]):
        errors.append("duplicate track ID")
    for person in people.values():
        if not 0 <= person["first_seen_ms"] <= person["last_seen_ms"] <= duration:
            errors.append(f"invalid person time: {person['id']}")
    for track in track_by_id.values():
        if track["person_id"] not in people:
            errors.append(f"unknown person on track: {track['track_id']}")
        if not 0 <= track["start_ms"] < track["end_ms"]:
            errors.append(f"invalid track time: {track['track_id']}")
    for item in tracks["review_candidates"]:
        if item["track_id"] not in track_by_id or item["possible_person_id"] not in people:
            errors.append("invalid review candidate reference")
    event_ids = set()
    for event in result["events"]:
        event_id = event["id"]
        if event_id in event_ids:
            errors.append(f"duplicate event: {event_id}")
        event_ids.add(event_id)
        if not 0 <= event["start_ms"] < event["end_ms"] <= duration:
            errors.append(f"invalid event time: {event_id}")
        if event["status"] not in {"观察到", "进行中", "已完成", "无法判断"}:
            errors.append(f"invalid status: {event_id}")
        if not event["evidence"]:
            errors.append(f"missing visual evidence: {event_id}")
        track_id = event.get("actor_track_id")
        track = track_by_id.get(track_id)
        if event["person_id"] is not None and (not track or track["person_id"] != event["person_id"]):
            errors.append(f"actor mapping mismatch: {event_id}")
        for evidence in event["evidence"]:
            frame = frames.get(evidence["frame_id"])
            if (not frame or frame["timestamp_ms"] != evidence["timestamp_ms"] or
                    frame["image"] != evidence["image"]):
                errors.append(f"frame mapping mismatch: {event_id}")
            if not event["start_ms"] <= evidence["timestamp_ms"] <= event["end_ms"]:
                errors.append(f"evidence outside event: {event_id}")
            image = root / evidence["image"]
            if not image.is_file() or image.resolve().parent != (root / "evidence").resolve():
                errors.append(f"missing evidence image: {event_id}")
            if event["person_id"] and track and evidence["frame_id"] not in track["frame_ids"]:
                errors.append(f"person absent at evidence frame: {event_id}")
    expected_summary = "；".join(
        f'{event["person_id"] or "人物未确认"}：{event["action"]}（{event["status"]}）'
        for event in result["events"]) or "未识别到有证据支持的事件。"
    if result["summary"] != expected_summary or expected_summary not in (
            root / "summary.md").read_text(encoding="utf-8"):
        errors.append("summary differs from validated events")
    if not manifest.get("input_sha256") or manifest.get("scene_count", 0) < 1:
        errors.append("incomplete manifest")
    return {"complete": result["complete"], "duration_ms": duration,
            "people": len(people), "tracklets": len(track_by_id),
            "review_candidates": len(tracks["review_candidates"]),
            "events": len(event_ids), "frames": len(frames),
            "elapsed_seconds": manifest.get("elapsed_seconds"), "errors": errors}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    report = validate_run(args.run)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(1 if report["errors"] or not report["complete"] else 0)
