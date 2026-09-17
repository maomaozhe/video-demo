"""Evidence-linked, readable descriptions from an existing structured run."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

from .analyze import SampledFrame


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _selected_frames(run: Path, frames: dict, start: int, end: int) -> list[SampledFrame]:
    available = []
    evidence_dir = (run / "evidence").resolve()
    for frame_id, item in frames.items():
        point = item["timestamp_ms"]
        if start <= point < end:
            path = run / item["image"]
            if path.is_symlink() or path.resolve().parent != evidence_dir or not path.is_file():
                raise ValueError(f"Missing or unsafe evidence frame: {frame_id}")
            available.append(SampledFrame(point, frame_id, path))
    available.sort(key=lambda frame: frame.timestamp_ms)
    if not available:
        raise ValueError(f"No evidence frames in {start}–{end} ms")
    chosen = []
    for index in range(min(4, len(available))):
        target = start + (end - start) * (2 * index + 1) / 8
        frame = min(available, key=lambda item: (abs(item.timestamp_ms - target), item.timestamp_ms))
        if frame not in chosen:
            chosen.append(frame)
    return chosen


def _describe_frames(model, selected: list[SampledFrame]) -> str:
    try:
        description = model.describe(selected).strip()
    except RuntimeError as exc:
        if "reached the output token limit" not in str(exc) or len(selected) < 2:
            raise
        middle = len(selected) // 2
        groups = (selected[:middle], selected[middle:])
        return "\n\n".join(
            f'{group[0].timestamp_ms / 1000:.1f}–{group[-1].timestamp_ms / 1000:.1f} 秒采样画面：'
            + _describe_frames(model, group) for group in groups
        )
    if not description:
        raise RuntimeError("Empty detailed description")
    return description


def generate_narrative(run: Path, model, *, segment_ms: int = 20000,
                       frame_group_size: int = 4) -> dict:
    """Create a detailed report and resume after completed segment descriptions."""
    started = time.monotonic()
    run = Path(run)
    result = json.loads((run / "result.json").read_text(encoding="utf-8"))
    frames = json.loads((run / "frames.json").read_text(encoding="utf-8"))
    manifest_path = run / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    duration = result["video"]["duration_ms"]
    if segment_ms <= 0 or duration <= 0 or not result.get("complete") or not 1 <= frame_group_size <= 4:
        raise ValueError("Narrative requires a completed run and positive segment length")
    partial_path = run / "narrative.partial.json"
    partial = json.loads(partial_path.read_text(encoding="utf-8")) if partial_path.is_file() else {}
    completed = partial.get("segments", []) if partial.get("input_sha256") == manifest.get("input_sha256") else []
    completed_stages = partial.get("stages", []) if partial.get("input_sha256") == manifest.get("input_sha256") else []
    segments = []
    for start in range(0, duration, segment_ms):
        end = min(start + segment_ms, duration)
        selected = _selected_frames(run, frames, start, end)
        frame_ids = [frame.frame_id for frame in selected]
        previous = completed[len(segments)] if len(completed) > len(segments) else None
        if previous and previous.get("start_ms") == start and previous.get("end_ms") == end and previous.get("frame_ids") == frame_ids:
            segment = previous
        else:
            if len(selected) <= frame_group_size:
                description = _describe_frames(model, selected)
            else:
                groups = [selected[index:index + frame_group_size]
                          for index in range(0, len(selected), frame_group_size)]
                description = "\n\n".join(
                    f'{group[0].timestamp_ms / 1000:.1f}–{group[-1].timestamp_ms / 1000:.1f} 秒采样画面：'
                    + _describe_frames(model, group) for group in groups
                )
            segment = {"start_ms": start, "end_ms": end, "frame_ids": frame_ids,
                       "description": description}
        segments.append(segment)
        _write(partial_path, {"input_sha256": manifest.get("input_sha256"), "segments": segments})
    stages = []
    if len(segments) > 4:
        for index in range(0, len(segments), 3):
            group = segments[index:index + 3]
            source_hash = hashlib.sha256(json.dumps(group, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            previous = completed_stages[len(stages)] if len(completed_stages) > len(stages) else None
            if previous and previous.get("source_sha256") == source_hash:
                stage = previous
            else:
                description = model.synthesize(group).strip()
                if not description:
                    raise RuntimeError("Empty stage synthesis")
                stage = {"start_ms": group[0]["start_ms"], "end_ms": group[-1]["end_ms"],
                         "description": description, "source_sha256": source_hash}
            stages.append(stage)
            _write(partial_path, {"input_sha256": manifest.get("input_sha256"),
                                  "segments": segments, "stages": stages})
    overall = (model.synthesize_overview(stages) if stages else model.synthesize(segments)).strip()
    if not overall:
        raise RuntimeError("Empty full-video synthesis")
    narrative = {"model": getattr(model, "model_id", "unknown"),
                 "generated_at": datetime.now(timezone.utc).isoformat(),
                 "overall": overall, "segments": segments, "stages": stages,
                 "note": "基于采样画面的模型描述；衣着、动作和跨片段身份需人工核对。"}
    lines = ["# 视频详细描述", "", f'输入视频：{Path(manifest["input"]).name}', "",
             "## 全片综合描述", "", overall, "", "## 分段细节", ""]
    for segment in segments:
        lines.extend([f'## {segment["start_ms"] / 1000:.1f}–{segment["end_ms"] / 1000:.1f} 秒',
                      "", segment["description"], "",
                      "采样证据帧：" + "、".join(segment["frame_ids"]), ""])
    lines.extend(["## 阅读提示", "", narrative["note"],
                  "只根据已采样画面描述；采样间发生的动作以及同一人物跨片段身份不能由文字直接确认。", ""])
    _write(run / "narrative.json", narrative)
    (run / "narrative.md").write_text("\n".join(lines), encoding="utf-8")
    manifest["narrative"] = {"model": narrative["model"], "generated_at": narrative["generated_at"],
                             "segments": len(segments), "elapsed_seconds": round(time.monotonic() - started, 2)}
    _write(manifest_path, manifest)
    partial_path.unlink(missing_ok=True)
    return narrative
