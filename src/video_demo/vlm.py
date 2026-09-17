"""Lazy local Qwen3-VL adapter. Dependencies and weights are installed separately."""

import json
from pathlib import Path

from .analyze import SampledFrame


class QwenDescriber:
    def __init__(self, model_id: str = "models/Qwen3-VL-8B-Instruct") -> None:
        if not Path(model_id).is_dir():
            raise RuntimeError(f"Local Qwen3-VL model directory is missing: {model_id}")
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
            "综合这些按时间排序的采样画面，用简体中文尽可能准确、详细地描述片段中可见的内容。"
            "场景只介绍一次；按能区分的人物归纳各自可见的动作、操作的物体，以及有证据的前后变化。"
            "有多少不同动作就描述多少，不限制动作数量、句数或字数。"
            "持续动作只写一次，不要按采样画面逐帧复述，不要反复描写相同位置和静态背景。"
            "可以用衣着或位置区分人物；不能确认跨画面是同一人时，不要强行关联。"
            "只陈述画面直接支持的事实；不要推断准备做什么、动机、姓名、任务完成状态或采样间未显示的过程。"
            "动作、人物身份或结果看不清时，明确说明无法判断。"
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

    def extract(self, frames: list[SampledFrame], tracks: list[dict],
                transcript: list[dict], tasks: list[str]) -> list[dict]:
        """Request scene-local candidates; final validation is outside the model."""
        context = {"frames": [{"frame_id": f.frame_id, "timestamp_ms": f.timestamp_ms}
                              for f in frames],
                   "local_tracks": [{"track_id": t["track_id"], "frame_ids": t["frame_ids"]}
                                    for t in tracks], "transcript": transcript, "tasks": tasks}
        instruction = ("只根据下面编号画面和语音输出 JSON 数组。每项字段：start_ms,end_ms,"
                       "actor_track_id,action,object,task_type,status,evidence_frame_ids,"
                       "evidence_text_span,uncertainty_reason,completion_evidence。"
                       "最多输出3条最主要且不同的事件，每条最多引用2个关键帧。"
                       "使用紧凑单行JSON，不要缩进、解释或列出全部画面；无值用null。"
                       "人物只能使用给出的局部 track_id；不确定时为 null。"
                       "状态只用观察到、进行中、已完成、无法判断；完成必须描述画面中明确的结果或引用明确语音。"
                       "每项引用真实 frame_id，时间在输入画面范围内。不要编造被采样遗漏的过程。"
                       "无可观察事件时输出 []。上下文：" + json.dumps(context, ensure_ascii=False))
        content = [{"type": "text", "text": instruction}]
        for frame in frames:
            content.extend([{"type": "text", "text": f"{frame.frame_id} {frame.timestamp_ms} ms"},
                            {"type": "image", "image": frame.path.resolve().as_uri(),
                             "resized_height": 288, "resized_width": 512}])
        messages = [{"role": "user", "content": content}]
        prompt = self._processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        images, videos = self._process_vision_info(messages, image_patch_size=16)
        inputs = self._processor(text=[prompt], images=images, videos=videos,
                                 padding=True, do_resize=False,
                                 return_tensors="pt").to(self._model.device)
        with self._torch.inference_mode():
            output = self._model.generate(**inputs, max_new_tokens=768, do_sample=False)
        raw = self._processor.batch_decode(output[:, inputs.input_ids.shape[1]:],
                                            skip_special_tokens=True)[0].strip()
        if raw.startswith("```json"):
            raw = raw[7:].split("```", 1)[0].strip()
        try:
            candidates = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Model did not return valid event JSON: {raw[:300]}") from exc
        if not isinstance(candidates, list) or any(not isinstance(x, dict) for x in candidates):
            raise RuntimeError("Model event output must be a JSON array of objects")
        return candidates
