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
            "按视频时间顺序观察这些采样画面，用简体中文尽可能准确、具体地描述片段中可见的内容。"
            "写出能区分的每个人物分别做了什么、操作了什么物体，以及画面前后可确认的动作或物体状态变化；"
            "有多少不同的可见动作就描述多少，不限制句数或字数。"
            "同一动作持续出现时合并描述，避免反复概括场景或堆砌相似句子。"
            "只根据画面提供的证据陈述事实；对身份、动作先后或结果不确定时明确说无法判断。"
            "不要猜测姓名、动机、任务完成状态或采样画面之间未显示的过程。"
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
            generated = self._model.generate(**inputs, max_new_tokens=1024, do_sample=False)
        output_ids = generated[:, inputs.input_ids.shape[1]:]
        if output_ids.shape[1] >= 1024:
            raise RuntimeError("Model description reached the output token limit")
        return self._processor.batch_decode(
            output_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )[0]
