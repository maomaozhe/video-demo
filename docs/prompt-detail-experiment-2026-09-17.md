# 详细描述提示词实验

日期：2026-09-17。样例为 `data/example/xzg_314700.mp4` 的前 20 秒，模型仍为服务器本地 `Qwen3-VL-8B-Instruct`，仍只使用 2.5、7.5、12.5、17.5 秒的四张采样画面。运行产物只存放在服务器 `runs/`，不提交 Git。

## 改动

原提示词要求“一句不超过 80 个汉字”，只概括主要动作。现在不限制可见动作的数量、句数或字数，要求区分能确认的人物与动作、说明有证据的状态变化，并明确不确定性。模型生成的技术上限从 256 提高到 1024 token；达到上限仍会报错，避免把截断的描述当作完整结果。

首版详细提示词（提交 `8c8f193`）要求更多细节并减少重复；模型输出约 760 字，但按四张画面逐帧复述。第二版（提交 `2f9beec`）进一步要求按人物归纳、持续动作只写一次。输出约 840 字，已按人物分段，仍逐一复述四个采样时间点，部分动作和背景重复。两个结果分别保存在 `runs/sample-detailed-smoke/` 和 `runs/sample-detailed-v2/`，网页左侧可以切换查看。

这说明去掉字数限制确实增加了细节，但**仅靠提示词还不能可靠去重**。当前基线代码仍固定每 20 秒生成一条 `action` 文本；四张静态画面也无法证明采样间发生的过程或跨片段人物身份。后续若要更稳定地得到多个独立事件，需要调整输出结构、采样和相邻片段合并逻辑。

## 复现

这些验证直接调用 `video_demo.analyze.analyze_video` 基线函数。服务器当前另有尚未提交的完整流水线开发代码，CLI 的执行路径可能不同；不要用 CLI 输出直接与本实验比较。

```python
from pathlib import Path
from video_demo.analyze import analyze_video
from video_demo.vlm import QwenDescriber

analyze_video(
    Path("data/example/xzg_314700.mp4"),
    Path("runs/sample-detailed-v2"),
    QwenDescriber("models/Qwen3-VL-8B-Instruct"),
    max_segments=1,
)
```
