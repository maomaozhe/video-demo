import contextlib
import tempfile
import unittest
from pathlib import Path

from video_demo.analyze import SampledFrame
from video_demo.vlm import QwenDescriber


class FakeTokens:
    def __init__(self, length):
        self.shape = (1, length)

    def __getitem__(self, index):
        return FakeTokens(self.shape[1] - index[1].start)


class FakeInputs(dict):
    def __init__(self):
        super().__init__(input_ids=FakeTokens(1))

    @property
    def input_ids(self):
        return self["input_ids"]

    def to(self, device):
        return self


class FakeProcessor:
    def apply_chat_template(self, *args, **kwargs):
        return "prompt"

    def __call__(self, **kwargs):
        return FakeInputs()

    def batch_decode(self, *args, **kwargs):
        return ["详细的场景和人物动作。"]


class FakeModel:
    device = "cpu"

    def generate(self, **kwargs):
        return FakeTokens(1501)


class VlmTests(unittest.TestCase):
    def test_detailed_description_accepts_more_than_1024_output_tokens(self):
        describer = QwenDescriber.__new__(QwenDescriber)
        describer._processor = FakeProcessor()
        describer._model = FakeModel()
        describer._torch = type("FakeTorch", (), {"inference_mode": staticmethod(contextlib.nullcontext)})()
        describer._process_vision_info = lambda messages, image_patch_size: ([], [])
        with tempfile.TemporaryDirectory() as temporary:
            frame = SampledFrame(500, "F1", Path(temporary) / "F1.jpg")
            self.assertIn("人物动作", describer.describe([frame]))


if __name__ == "__main__":
    unittest.main()
