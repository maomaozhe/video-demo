"""RT-DETR and per-scene BoT-SORT person tracklets."""

from collections import defaultdict
from pathlib import Path


def track_people(video: Path, scenes: list[tuple[int, int]], frame_times: dict[str, int],
                 model_path: str, *, fps: float = 3.0) -> list[dict]:
    if not Path(model_path).is_file():
        raise RuntimeError(f"Local RT-DETR weights are missing: {model_path}")
    import cv2
    from ultralytics import RTDETR

    model = RTDETR(model_path)
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise RuntimeError("Cannot decode video for tracking")
    frame_rate = capture.get(cv2.CAP_PROP_FPS)
    if frame_rate <= 0:
        raise RuntimeError("Cannot determine tracking frame rate")
    tracks = defaultdict(lambda: {"detections": [], "frame_ids": set()})
    try:
        for scene_id, (start, end) in enumerate(scenes):
            if model.predictor is not None and getattr(model.predictor, "trackers", None):
                model.predictor.trackers[0].reset()
            step = max(1, round(frame_rate / fps))
            first = max(0, round(start / 1000 * frame_rate))
            last = round(end / 1000 * frame_rate)
            evidence_indices = {round(value / 1000 * frame_rate) for value in frame_times.values()
                                if start <= value < end}
            for index in sorted(set(range(first, last, step)) | evidence_indices):
                capture.set(cv2.CAP_PROP_POS_FRAMES, index)
                ok, image = capture.read()
                if not ok:
                    continue
                timestamp_ms = round(index / frame_rate * 1000)
                prediction = model.track(image, persist=True, classes=[0], conf=0.35,
                                         tracker="botsort.yaml", verbose=False)[0]
                boxes = prediction.boxes
                if boxes is None or boxes.id is None:
                    continue
                nearby = [key for key, value in frame_times.items()
                          if abs(value - timestamp_ms) <= 1000 / frame_rate]
                for identifier, box, confidence in zip(boxes.id.tolist(), boxes.xyxy.tolist(),
                                                        boxes.conf.tolist()):
                    key = f"S{scene_id}_T{int(identifier)}"
                    tracks[key]["detections"].append({"timestamp_ms": timestamp_ms,
                                                       "bbox": [round(v, 1) for v in box],
                                                       "confidence": round(confidence, 4)})
                    tracks[key]["frame_ids"].update(nearby)
    finally:
        capture.release()
    return [{"track_id": key, "scene_id": int(key.split("_")[0][1:]),
             "start_ms": value["detections"][0]["timestamp_ms"],
             "end_ms": value["detections"][-1]["timestamp_ms"] + round(1000 / fps),
             "detections": value["detections"], "frame_ids": sorted(value["frame_ids"])}
            for key, value in tracks.items()]
