from dataclasses import dataclass
from fractions import Fraction
import json
from pathlib import Path
import subprocess


class VideoProbeError(ValueError):
    pass


@dataclass(frozen=True)
class VideoMetadata:
    path: Path
    duration_ms: int
    width: int
    height: int
    fps: float
    has_audio: bool


def probe_video(path: Path) -> VideoMetadata:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() not in {".mp4", ".mov"}:
        raise VideoProbeError("Input must be MP4/MOV")

    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries",
                "format=duration:stream=codec_type,width,height,r_frame_rate",
                "-of", "json", str(path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise VideoProbeError(f"Could not run ffprobe: {exc}") from exc

    if result.returncode != 0:
        raise VideoProbeError(f"Could not read video: {result.stderr.strip()}")

    try:
        data = json.loads(result.stdout)
        streams = data["streams"]
        video_stream = next(stream for stream in streams if stream["codec_type"] == "video")
        duration_ms = round(float(data["format"]["duration"]) * 1000)
        width = int(video_stream["width"])
        height = int(video_stream["height"])
        fps = float(Fraction(video_stream["r_frame_rate"]))
        if duration_ms <= 0 or width <= 0 or height <= 0 or fps <= 0:
            raise ValueError("non-positive metadata")
    except (KeyError, ValueError, StopIteration, ZeroDivisionError) as exc:
        raise VideoProbeError(f"Invalid video metadata: {exc}") from exc

    try:
        decoded = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-frames:v", "1",
                                  "-f", "null", "-"], capture_output=True, text=True, check=False)
    except OSError as exc:
        raise VideoProbeError(f"Could not run ffmpeg: {exc}") from exc
    if decoded.returncode:
        raise VideoProbeError(f"Could not decode first video frame: {decoded.stderr.strip()}")

    return VideoMetadata(
        path=path,
        duration_ms=duration_ms,
        width=width,
        height=height,
        fps=fps,
        has_audio=any(stream.get("codec_type") == "audio" for stream in streams),
    )
