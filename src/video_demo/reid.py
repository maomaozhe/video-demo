"""FastReID appearance vectors from representative track crops."""

from pathlib import Path
import sys


def embed_tracklets(video: Path, tracks: list[dict], repository: Path,
                    config_path: Path, weights_path: Path, fps: float) -> dict[str, tuple[float, ...]]:
    if not repository.is_dir() or not config_path.is_file() or not weights_path.is_file():
        raise FileNotFoundError("FastReID source, config and weights must exist locally")
    sys.path.insert(0, str(repository.resolve()))
    import cv2
    import torch
    from fastreid.config import get_cfg
    from fastreid.modeling.meta_arch import build_model
    from fastreid.utils.checkpoint import Checkpointer

    cfg = get_cfg()
    cfg.merge_from_file(str(config_path.resolve()))
    cfg.MODEL.BACKBONE.PRETRAIN = False
    cfg.MODEL.DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    cfg.freeze()
    model = build_model(cfg).eval()
    Checkpointer(model).load(str(weights_path.resolve()))
    cap = cv2.VideoCapture(str(video))
    vectors = {}
    try:
        for track in tracks:
            best = max(track["detections"], key=lambda x: x["confidence"])
            cap.set(cv2.CAP_PROP_POS_FRAMES, round(best["timestamp_ms"] / 1000 * fps))
            ok, image = cap.read()
            if not ok:
                continue
            x1, y1, x2, y2 = [round(v) for v in best["bbox"]]
            crop = image[max(0, y1):max(0, y2), max(0, x1):max(0, x2)]
            if crop.size == 0:
                continue
            height, width = cfg.INPUT.SIZE_TEST
            crop = cv2.resize(crop, (width, height))
            tensor = torch.as_tensor(crop.transpose(2, 0, 1).copy(),
                                     dtype=torch.float32, device=cfg.MODEL.DEVICE)[None]
            with torch.inference_mode():
                vector = model(tensor).flatten().float()
                vector = torch.nn.functional.normalize(vector, dim=0)
            vectors[track["track_id"]] = tuple(vector.cpu().tolist())
    finally:
        cap.release()
    return vectors
