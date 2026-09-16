"""Frame-sampling baseline for the first offline video description loop."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Protocol

from .schema import Event, Evidence, validate_event
from .video import probe_video


@dataclass(frozen=True)
class SampledFrame:
    timestamp_ms: int
    frame_id: str
    path: Path


class Describer(Protocol):
    model_id: str

    def describe(self, frames: list[SampledFrame]) -> str: ...


def segment_ranges(duration_ms: int, segment_ms: int) -> list[tuple[int, int]]:
    if duration_ms <= 0 or segment_ms <= 0:
        raise ValueError("duration and segment length must be positive")
    return [(start, min(start + segment_ms, duration_ms)) for start in range(0, duration_ms, segment_ms)]


def _extract_frame(video: Path, timestamp_ms: int, destination: Path) -> None:
    command = [
        "ffmpeg", "-v", "error", "-ss", f"{timestamp_ms / 1000:.3f}",
        "-i", str(video), "-frames:v", "1", "-q:v", "3", "-y", str(destination),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise RuntimeError(f"Could not run ffmpeg: {exc}") from exc
    if result.returncode or not destination.is_file():
        raise RuntimeError(f"Could not extract frame at {timestamp_ms} ms: {result.stderr.strip()}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def analyze_video(
    video_path: Path,
    output_dir: Path,
    describer: Describer,
    *,
    segment_ms: int = 20000,
    frames_per_segment: int = 4,
    max_segments: int | None = None,
) -> dict:
    """Describe sampled frames. Person IDs and detailed actions come in later stages."""
    if frames_per_segment <= 0 or (max_segments is not None and max_segments <= 0):
        raise ValueError("frame count and max segments must be positive")

    metadata = probe_video(video_path)
    output_dir = Path(output_dir)
    evidence_dir = output_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    ranges = segment_ranges(metadata.duration_ms, segment_ms)
    selected_ranges = ranges[:max_segments]
    events = []
    lines = ["# 视频内容摘要", "", f"输入视频：{metadata.path.name}", ""]

    for segment_number, (start, end) in enumerate(selected_ranges, start=1):
        frames = []
        for sample_number in range(frames_per_segment):
            timestamp_ms = start + (end - start) * (2 * sample_number + 1) // (2 * frames_per_segment)
            timestamp_ms = min(timestamp_ms, end - 1)
            frame_id = f"F{segment_number:04d}_{sample_number + 1:02d}"
            frame_path = evidence_dir / f"{frame_id}.jpg"
            _extract_frame(metadata.path, timestamp_ms, frame_path)
            frames.append(SampledFrame(timestamp_ms, frame_id, frame_path))

        description = describer.describe(frames).strip()
        if not description:
            raise RuntimeError(f"Model returned an empty description for segment {segment_number}")
        event = Event(
            start_ms=start, end_ms=end, action=description, status="观察到",
            evidence=[Evidence(frame.timestamp_ms, frame.frame_id) for frame in frames],
        )
        validate_event(event, metadata.duration_ms)
        events.append({
            "id": f"E{segment_number}",
            **asdict(event),
            "evidence": [
                {"timestamp_ms": frame.timestamp_ms, "frame_id": frame.frame_id,
                 "image": f"evidence/{frame.path.name}"}
                for frame in frames
            ],
            "review_required": True,
        })
        lines.append(f"- {start / 1000:.1f}–{end / 1000:.1f} 秒：{description}")

    complete = len(selected_ranges) == len(ranges)
    warnings = ["人物关联尚未启用", "当前按采样帧描述，快速动作可能遗漏；描述需人工复核"]
    if not complete:
        warnings.append("只处理了视频的一部分，不代表完整视频结论")
    result = {
        "schema_version": "1.0", "complete": complete,
        "video": {"duration_ms": metadata.duration_ms, "width": metadata.width,
                  "height": metadata.height, "fps": metadata.fps, "has_audio": metadata.has_audio},
        "people": [], "events": events,
        "summary": "；".join(event["action"] for event in events), "warnings": warnings,
    }
    (output_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines.extend(["", "## 限制", *[f"- {warning}" for warning in warnings], ""])
    (output_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    manifest = {
        "input": str(metadata.path.resolve()), "input_sha256": _sha256(metadata.path),
        "model": getattr(describer, "model_id", type(describer).__name__),
        "segment_ms": segment_ms, "frames_per_segment": frames_per_segment,
        "max_segments": max_segments, "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
