"""Command line entry point for local batch analysis."""

import argparse
from pathlib import Path
import traceback

from .analyze import analyze_video
from .video import VideoProbeError, probe_video


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="video-demo")
    commands = parser.add_subparsers(dest="command", required=True)
    analyze = commands.add_parser("analyze", help="Describe sampled video frames locally")
    analyze.add_argument("video", type=Path)
    analyze.add_argument("--output", type=Path, required=True)
    analyze.add_argument("--model", default="Qwen/Qwen3-VL-8B-Instruct")
    analyze.add_argument("--segment-seconds", type=int, default=20)
    analyze.add_argument("--frames-per-segment", type=int, default=4)
    analyze.add_argument("--max-segments", type=int)
    args = parser.parse_args(argv)

    if args.segment_seconds <= 0 or args.frames_per_segment <= 0 or (
        args.max_segments is not None and args.max_segments <= 0
    ):
        parser.error("segment seconds, frame count and max segments must be positive")

    try:
        probe_video(args.video)
    except (FileNotFoundError, VideoProbeError) as exc:
        parser.error(str(exc))

    args.output.mkdir(parents=True, exist_ok=True)
    try:
        from .vlm import QwenDescriber

        describer = QwenDescriber(args.model)
        analyze_video(
            args.video, args.output, describer,
            segment_ms=args.segment_seconds * 1000,
            frames_per_segment=args.frames_per_segment,
            max_segments=args.max_segments,
        )
    except KeyboardInterrupt:
        (args.output / "run.log").write_text("Interrupted by user\n", encoding="utf-8")
        return 4
    except Exception:
        (args.output / "run.log").write_text(traceback.format_exc(), encoding="utf-8")
        return 3
    (args.output / "run.log").write_text("Completed\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
