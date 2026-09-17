import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from video_demo.asr import transcribe


class AsrTests(unittest.TestCase):
    def test_noisy_audio_hallucination_is_not_used_as_speech_evidence(self):
        def segment(text, no_speech_prob, avg_logprob):
            return types.SimpleNamespace(start=1.0, end=2.0, text=text,
                                         no_speech_prob=no_speech_prob,
                                         avg_logprob=avg_logprob)

        class Model:
            def __init__(self, *args, **kwargs):
                pass

            def transcribe(self, *args, **kwargs):
                return iter([segment("我爱你", 0.56, -0.8),
                             segment("garbled 漢", 0.1, -1.2),
                             segment("明确语音", 0.1, -0.3)]), None

        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "model.bin").touch()
            with patch.dict(sys.modules, {"faster_whisper": types.SimpleNamespace(WhisperModel=Model)}):
                result = transcribe(Path("audio.wav"), directory, device="cpu")
        self.assertEqual(result, [{"start_ms": 1000, "end_ms": 2000, "text": "明确语音"}])


if __name__ == "__main__":
    unittest.main()
