"""Offline scene, person, speech and evidence pipeline."""

from datetime import datetime, timezone
import hashlib
from importlib import metadata as package_metadata
import json
from pathlib import Path
import platform
import subprocess
import time

from .analyze import SampledFrame, _extract_frame
from .pipeline import detect_scenes, normalize_candidate, scene_segments
from .video import probe_video


def _write(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _log(output: Path, message: str) -> None:
    with (output / "run.log").open("a", encoding="utf-8") as target:
        target.write(f"{datetime.now(timezone.utc).isoformat()} {message}\n")


def _hash(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _weights(path: Path) -> dict:
    if path.is_file():
        return {path.name: _hash(path)}
    if path.is_dir():
        return {item.name: _hash(item) for item in sorted(path.iterdir())
                if item.is_file() and item.suffix in {".bin", ".safetensors", ".pt", ".pth"}}
    return {}


def _versions() -> dict:
    names = ("torch", "transformers", "ultralytics", "scenedetect",
             "faster-whisper", "qwen-vl-utils")
    result = {}
    for name in names:
        try:
            result[name] = package_metadata.version(name)
        except package_metadata.PackageNotFoundError:
            result[name] = None
    return result


def _revision(path: Path | None) -> str | None:
    if not path or not path.is_dir():
        return None
    proc = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else None


def _gpu_peak_mib() -> float | None:
    try:
        import torch
        return round(torch.cuda.max_memory_allocated() / 1024**2, 1) if torch.cuda.is_available() else None
    except ImportError:
        return None


def analyze_full(video_path: Path, output: Path, model, *, detector_path: str,
                 whisper_path: str, tasks: list[str] | None = None,
                 segment_ms: int = 20000, max_segments: int | None = None,
                 reid_repository: Path | None = None, reid_config: Path | None = None,
                 reid_weights: Path | None = None, merge_threshold: float | None = None,
                 review_threshold: float = 0.75) -> dict:
    started = time.monotonic()
    metadata = probe_video(video_path)
    output.mkdir(parents=True, exist_ok=True)
    _log(output, "Started full pipeline")
    evidence_dir = output / "evidence"
    evidence_dir.mkdir(exist_ok=True)
    scenes = detect_scenes(metadata.path, metadata.duration_ms)
    _log(output, f"Detected {len(scenes)} scenes")
    overlap_ms = min(2000, segment_ms // 10)
    segments = scene_segments(scenes, segment_ms, overlap_ms)
    complete = max_segments is None or max_segments >= len(segments)
    segments = segments[:max_segments]
    frames: dict[str, dict] = {}
    for start, end, scene_id in segments:
        points = list(range(start + 500, end, 1000)) or [start + (end - start) // 2]
        for point in points:
            frame_id = f"F{point:09d}"
            if frame_id not in frames:
                path = evidence_dir / f"{frame_id}.jpg"
                _extract_frame(metadata.path, point, path)
                frames[frame_id] = {"timestamp_ms": point, "image": f"evidence/{path.name}",
                                    "scene_id": scene_id}
    _write(output / "frames.json", frames)
    _log(output, f"Extracted {len(frames)} evidence frames")

    from .tracking import track_people
    if complete:
        tracked_scenes = scenes
    else:
        last_scene = max(scene_id for _, _, scene_id in segments)
        tracked_scenes = scenes[:last_scene] + [
            (scenes[last_scene][0], segments[-1][1])]
    tracklets = track_people(metadata.path, tracked_scenes,
                             {key: item["timestamp_ms"] for key, item in frames.items()},
                             detector_path)
    _log(output, f"Tracked {len(tracklets)} local people")
    people = []
    track_map = {}
    embeddings = {}
    reviews = []
    mapping = {}
    if reid_repository and reid_config and reid_weights and tracklets:
        from .reid import embed_tracklets
        from .identity import Tracklet, associate_tracklets, prioritize_reviews
        embeddings = embed_tracklets(metadata.path, tracklets, reid_repository,
                                     reid_config, reid_weights, metadata.fps)
        eligible = [Tracklet(t["track_id"], t["start_ms"], t["end_ms"],
                             embeddings[t["track_id"]]) for t in tracklets
                    if t["track_id"] in embeddings]
        if eligible:
            association = associate_tracklets(eligible, merge_threshold=merge_threshold or 1.0,
                                               review_threshold=review_threshold,
                                               max_review_candidates=len(eligible),
                                               merge_enabled=merge_threshold is not None)
            mapping = association.track_to_person
            scene_by_track = {t["track_id"]: t["scene_id"] for t in tracklets}
            reviews = [item.__dict__ for item in prioritize_reviews(association, scene_by_track)]
    next_id = max([int(value[1:]) for value in mapping.values()], default=0)
    for track in sorted(tracklets, key=lambda item: (item["start_ms"], item["track_id"])):
        person_id = mapping.get(track["track_id"])
        if person_id is None:
            next_id += 1
            person_id = f"P{next_id}"
        track["person_id"] = person_id
        track["review_required"] = merge_threshold is None
        track_map[track["track_id"]] = track
    for person_id in sorted({track["person_id"] for track in tracklets}, key=lambda x: int(x[1:])):
        members = [t for t in tracklets if t["person_id"] == person_id]
        people.append({"id": person_id,
                       "first_seen_ms": min(t["start_ms"] for t in members),
                       "last_seen_ms": min(max(t["end_ms"] for t in members), metadata.duration_ms),
                       "review_required": any(t["review_required"] for t in members)})
    _write(output / "tracks.json", {"tracklets": tracklets,
                                     "review_candidates": reviews,
                                     "association": "FastReID" if embeddings else "unavailable",
                                     "embedding_count": len(embeddings)})
    _log(output, f"FastReID embedded {len(embeddings)} tracklets")

    transcript = []
    if metadata.has_audio:
        from .asr import extract_audio, transcribe
        audio = output / "audio.wav"
        extract_audio(metadata.path, audio)
        transcript = transcribe(audio, whisper_path)
        if transcript:
            _write(output / "transcript.json", transcript)
        audio.unlink(missing_ok=True)
    _log(output, f"Transcribed {len(transcript)} speech segments")

    events = []
    invalid = 0
    seen = set()
    for segment_number, (start, end, scene_id) in enumerate(segments, 1):
        selected = [SampledFrame(item["timestamp_ms"], key, output / item["image"])
                    for key, item in frames.items() if start <= item["timestamp_ms"] < end]
        local_tracks = [item for item in tracklets if item["scene_id"] == scene_id and
                        item["start_ms"] < end and item["end_ms"] > start]
        spoken = [item for item in transcript if item["start_ms"] < end and item["end_ms"] > start]
        allowed_frames = {frame.frame_id: frames[frame.frame_id] for frame in selected}
        for candidate in model.extract(selected, local_tracks, spoken, tasks or []):
            event = normalize_candidate(candidate, allowed_frames, track_map,
                                        metadata.duration_ms, spoken)
            if event is None or not start <= event["start_ms"] < end:
                invalid += 1
                continue
            if tasks and event["task_type"] not in tasks:
                event["task_type"] = None
                event["review_required"] = True
            signature = (event["person_id"], event["action"],
                         tuple(x["frame_id"] for x in event["evidence"]))
            if signature in seen:
                continue
            seen.add(signature)
            event["id"] = f"E{len(events) + 1}"
            events.append(event)
        _write(output / "events.partial.json", events)
        _log(output, f"Analyzed segment {segment_number}/{len(segments)}; {len(events)} valid events")

    summary = "；".join(f'{event["person_id"] or "人物未确认"}：{event["action"]}（{event["status"]}）'
                       for event in events) or "未识别到有证据支持的事件。"
    warnings = []
    if not tracklets:
        warnings.append("未检测到人物；事件不绑定人物 ID")
    elif not embeddings:
        warnings.append("FastReID 未配置或未取得外观向量；跨镜头人物不合并")
    elif merge_threshold is None:
        warnings.append("FastReID 阈值未用标注集校准；相似候选需人工复核，不自动合并")
    if metadata.has_audio and not transcript:
        warnings.append("音轨中未检测到可信语音")
    if invalid:
        warnings.append(f"丢弃了 {invalid} 个缺少有效时间或画面证据的模型候选")
    if not complete:
        warnings.append("只处理视频部分片段")
    result = {"schema_version": "1.0", "complete": complete,
              "video": {"duration_ms": metadata.duration_ms, "width": metadata.width,
                        "height": metadata.height, "fps": metadata.fps, "has_audio": metadata.has_audio},
              "people": people, "events": events, "summary": summary, "warnings": warnings}
    _write(output / "result.json", result)
    lines = ["# 视频内容摘要", "", summary, "", "## 时间线", ""]
    lines += [f'- {event["start_ms"] / 1000:.3f}–{event["end_ms"] / 1000:.3f} 秒 '
              f'{event["person_id"] or "人物未确认"}：{event["action"]}（{event["status"]}）'
              for event in events]
    lines += ["", "## 限制", ""] + [f"- {warning}" for warning in warnings]
    (output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    _write(output / "manifest.json", {
        "input": str(metadata.path.resolve()), "input_sha256": _hash(metadata.path),
        "models": {"vlm": getattr(model, "model_id", "unknown"), "detector": detector_path,
                   "vlm_weights_sha256": _weights(Path(getattr(model, "model_id", ""))),
                   "detector_sha256": _hash(Path(detector_path)), "asr": whisper_path,
                   "asr_weights_sha256": _weights(Path(whisper_path)),
                   "reid_weights": str(reid_weights) if reid_weights else None,
                   "reid_sha256": _hash(reid_weights) if reid_weights else None,
                   "reid_source_revision": _revision(reid_repository)},
        "package_versions": _versions(),
        "runtime": {"python": platform.python_version(), "platform": platform.platform()},
        "parameters": {"segment_ms": segment_ms, "overlap_ms": overlap_ms,
                       "vlm_fps": 1, "tracking_fps": 3, "max_segments": max_segments,
                       "merge_threshold": merge_threshold, "review_threshold": review_threshold},
        "scene_count": len(scenes), "elapsed_seconds": round(time.monotonic() - started, 2),
        "peak_torch_gpu_allocated_mib": _gpu_peak_mib(),
        "created_at": datetime.now(timezone.utc).isoformat()})
    if complete and hasattr(model, "describe") and hasattr(model, "synthesize"):
        from .narrative import generate_narrative

        generate_narrative(output, model, segment_ms=segment_ms, frame_group_size=2)
        _log(output, "Generated detailed segment and full-video narrative")
    return result
