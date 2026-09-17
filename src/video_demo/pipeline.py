"""Scene timing and conservative model candidate validation."""


def scene_segments(scenes: list[tuple[int, int]], length_ms: int = 20000,
                   overlap_ms: int = 2000) -> list[tuple[int, int, int]]:
    if length_ms <= overlap_ms or overlap_ms < 0:
        raise ValueError("invalid segment length/overlap")
    result = []
    for scene_id, (start, end) in enumerate(scenes):
        if end <= start:
            continue
        cursor = start
        while cursor < end:
            stop = min(cursor + length_ms, end)
            result.append((cursor, stop, scene_id))
            if stop == end:
                break
            cursor = stop - overlap_ms
    return result


def detect_scenes(video_path, duration_ms: int) -> list[tuple[int, int]]:
    """Return contiguous scene intervals on the original video timeline."""
    from scenedetect import ContentDetector, SceneManager, open_video

    stream = open_video(str(video_path))
    manager = SceneManager()
    manager.add_detector(ContentDetector())
    manager.detect_scenes(stream)
    boundaries = [0]
    for start, _ in manager.get_scene_list():
        point = round(start.get_seconds() * 1000)
        if 0 < point < duration_ms:
            boundaries.append(point)
    boundaries.append(duration_ms)
    boundaries = sorted(set(boundaries))
    return list(zip(boundaries, boundaries[1:]))


def normalize_candidate(candidate: dict, frames: dict, tracks: dict,
                        duration_ms: int, transcript: list[dict] | None = None) -> dict | None:
    """Keep only claims supported by named frames; never trust an actor name alone."""
    try:
        start = int(candidate["start_ms"])
        end = int(candidate["end_ms"])
        action = str(candidate["action"]).strip()
        ids = list(candidate["evidence_frame_ids"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (0 <= start < end <= duration_ms) or not action:
        return None
    evidence = []
    for frame_id in ids:
        frame = frames.get(frame_id)
        if frame and start <= frame["timestamp_ms"] <= end:
            evidence.append({"timestamp_ms": frame["timestamp_ms"],
                             "frame_id": frame_id, "image": frame["image"]})
    if not evidence:
        return None
    track_id = candidate.get("actor_track_id")
    track = tracks.get(track_id) if track_id else None
    person_id = track["person_id"] if track and any(
        frame["frame_id"] in track["frame_ids"] for frame in evidence
    ) else None
    if person_id:
        evidence = [frame for frame in evidence if frame["frame_id"] in track["frame_ids"]]
    status = candidate.get("status", "无法判断")
    if status not in {"观察到", "进行中", "已完成", "无法判断"}:
        status = "无法判断"
    review = bool(track and track.get("review_required")) or bool(track_id and person_id is None)
    text_span = candidate.get("evidence_text_span")
    if text_span is not None and not isinstance(text_span, str):
        text_span = None
        review = True
    if text_span and not any(start < item["end_ms"] and end > item["start_ms"]
                             and text_span in item["text"] for item in (transcript or [])):
        text_span = None
        review = True
    proposed_status = None
    if status == "已完成":
        proposed_status = status
        # A model-named frame verifies location, not the semantic result.
        status = "无法判断"
        review = True
    return {"start_ms": start, "end_ms": end, "person_id": person_id,
            "actor_track_id": track_id, "action": action,
            "object": candidate.get("object"), "task_type": candidate.get("task_type"),
            "status": status, "evidence": evidence,
            "evidence_text_span": text_span,
            "uncertainty_reason": candidate.get("uncertainty_reason"),
            "proposed_status": proposed_status,
            "review_required": review}
