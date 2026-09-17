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
    analyze.add_argument("--model", default="models/Qwen3-VL-8B-Instruct")
    analyze.add_argument("--segment-seconds", type=int, default=20)
    analyze.add_argument("--frames-per-segment", type=int, default=4)
    analyze.add_argument("--max-segments", type=int)
    analyze.add_argument("--task-config", type=Path)
    analyze.add_argument("--detector", default="models/rtdetr-l.pt")
    analyze.add_argument("--asr-model", default="models/faster-whisper-small")
    analyze.add_argument("--reid-repository", type=Path)
    analyze.add_argument("--reid-config", type=Path)
    analyze.add_argument("--reid-weights", type=Path)
    analyze.add_argument("--merge-threshold", type=float)
    analyze.add_argument("--review-threshold", type=float, default=0.75)
    args = parser.parse_args(argv)

    if args.segment_seconds <= 0 or args.frames_per_segment <= 0 or (
        args.max_segments is not None and args.max_segments <= 0
    ):
        parser.error("segment seconds, frame count and max segments must be positive")
    reid_paths = (args.reid_repository, args.reid_config, args.reid_weights)
    if any(reid_paths) and not all(reid_paths):
        parser.error("FastReID requires repository, config and weights together")
    if not 0 <= args.review_threshold < 1 or (
        args.merge_threshold is not None and not args.review_threshold < args.merge_threshold <= 1
    ):
        parser.error("review and merge thresholds must satisfy 0 <= review < merge <= 1")
    if args.merge_threshold is not None and not all(reid_paths):
        parser.error("merge threshold requires FastReID source, config and weights")

    try:
        probe_video(args.video)
    except (FileNotFoundError, VideoProbeError) as exc:
        parser.error(str(exc))

    tasks = []
    if args.task_config:
        try:
            import json
            if args.task_config.suffix.lower() == ".json":
                config = json.loads(args.task_config.read_text(encoding="utf-8"))
            else:
                import yaml
                config = yaml.safe_load(args.task_config.read_text(encoding="utf-8"))
            tasks = config["tasks"]
            if not isinstance(tasks, list) or any(not isinstance(item, str) for item in tasks):
                raise ValueError("tasks must be a list of strings")
        except (OSError, ValueError, KeyError, ImportError) as exc:
            parser.error(f"Invalid task config: {exc}")

    args.output.mkdir(parents=True, exist_ok=True)
    try:
        from .vlm import QwenDescriber

        model_path = "models/Qwen3-VL-8B-Instruct" if args.model.lower() == "qwen3-vl-8b" else args.model
        describer = QwenDescriber(model_path)
        if hasattr(describer, "extract"):
            from .mvp import analyze_full
            analyze_full(args.video, args.output, describer, detector_path=args.detector,
                         whisper_path=args.asr_model, tasks=tasks,
                         segment_ms=args.segment_seconds * 1000, max_segments=args.max_segments,
                         reid_repository=args.reid_repository, reid_config=args.reid_config,
                         reid_weights=args.reid_weights, merge_threshold=args.merge_threshold,
                         review_threshold=args.review_threshold)
        else:
            analyze_video(args.video, args.output, describer,
                          segment_ms=args.segment_seconds * 1000,
                          frames_per_segment=args.frames_per_segment,
                          max_segments=args.max_segments)
    except KeyboardInterrupt:
        with (args.output / "run.log").open("a", encoding="utf-8") as log:
            log.write("Interrupted by user\n")
        return 4
    except Exception:
        with (args.output / "run.log").open("a", encoding="utf-8") as log:
            log.write(traceback.format_exc())
        return 3
    with (args.output / "run.log").open("a", encoding="utf-8") as log:
        log.write("Completed\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
