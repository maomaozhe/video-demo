"""Lazy local Qwen3-VL adapter. Dependencies and weights are installed separately."""

from .analyze import SampledFrame


class QwenDescriber:
    def __init__(self, model_id: str = "Qwen/Qwen3-VL-8B-Instruct") -> None:
        try:
            import torch
            from transformers import AutoModelForImageTextToText, AutoProcessor
            from qwen_vl_utils import process_vision_info
        except ImportError as exc:
            raise RuntimeError(
                "Qwen3-VL dependencies are missing. Install torch, transformers>=4.57, "
                "accelerate and qwen-vl-utils in the project virtual environment."
            ) from exc

        self.model_id = model_id
        self._torch = torch
        self._process_vision_info = process_vision_info
        self._processor = AutoProcessor.from_pretrained(model_id)
        self._model = AutoModelForImageTextToText.from_pretrained(
            model_id, dtype=torch.bfloat16, device_map="auto"
        ).eval()

    def describe(self, frames: list[SampledFrame]) -> str:
        content = [{"type": "text", "text": (
            "按时间顺序观察这些采样画面。用简体中文简短描述能直接看见的人物动作、物体和变化。"
            "只描述有画面证据的事实；看不清时明确说无法判断。"
            "不要猜测人物姓名、动机、任务完成状态或未显示的过程。"
        )}]
        for frame in frames:
            content.extend([
                {"type": "text", "text": f"视频时间 {frame.timestamp_ms / 1000:.3f} 秒："},
                {"type": "image", "image": frame.path.resolve().as_uri()},
            ])
        messages = [{"role": "user", "content": content}]
        prompt = self._processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        images, videos = self._process_vision_info(messages, image_patch_size=16)
        inputs = self._processor(
            text=[prompt], images=images, videos=videos, padding=True, return_tensors="pt"
        ).to(self._model.device)
        with self._torch.inference_mode():
            generated = self._model.generate(**inputs, max_new_tokens=256, do_sample=False)
        output_ids = generated[:, inputs.input_ids.shape[1]:]
        return self._processor.batch_decode(
            output_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )[0]
