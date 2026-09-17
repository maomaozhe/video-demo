"""Timestamped local speech transcription."""

from pathlib import Path
import subprocess
import re


def extract_audio(video: Path, destination: Path) -> None:
    result = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vn", "-ac", "1",
                             "-ar", "16000", "-c:a", "pcm_s16le", "-y", str(destination)],
                            capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(f"Audio extraction failed: {result.stderr.strip()}")


def transcribe(audio: Path, model_path: str, *, device: str = "cpu") -> list[dict]:
    if not (Path(model_path) / "model.bin").is_file():
        raise RuntimeError(f"Local faster-whisper weights are missing: {model_path}")
    if device == "cuda":
        # CTranslate2 does not search PyTorch's wheel-bundled CUDA libraries.
        import ctypes
        import torch
        nvidia = Path(torch.__file__).resolve().parent.parent / "nvidia"
        for relative in ("cublas/lib/libcublasLt.so.12", "cublas/lib/libcublas.so.12",
                         "cudnn/lib/libcudnn.so.9"):
            library = nvidia / relative
            if library.is_file():
                ctypes.CDLL(str(library), mode=ctypes.RTLD_GLOBAL)
    from faster_whisper import WhisperModel

    model = WhisperModel(model_path, device=device, compute_type="float16" if device == "cuda" else "int8")
    segments, _ = model.transcribe(str(audio), vad_filter=True, beam_size=5)
    return [{"start_ms": round(item.start * 1000), "end_ms": round(item.end * 1000),
             "text": item.text.strip()} for item in segments
            if item.no_speech_prob < 0.5 and item.avg_logprob > -1.0
            and re.search(r"[A-Za-z\u4e00-\u9fff]", item.text)]
