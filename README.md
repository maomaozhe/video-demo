# video-demo

本地视频理解 MVP。当前已实现输入校验、按固定时间片抽取证据帧、调用本地 Qwen3-VL 生成保守的中文描述，并写出 JSON、Markdown 与运行清单。人物轨迹的保守关联规则已有独立实现，但人体检测和外观向量尚未接入；语音转写和细粒度任务状态仍在后续阶段。

## 服务器准备

在 `~/video-demo` 的 Python 3.11 虚拟环境安装 PyTorch CUDA 版本（见 [`docs/server-environment.md`](docs/server-environment.md)），然后安装模型依赖：

```bash
uv pip install --python .venv/bin/python -e . 'transformers>=4.57,<5' accelerate 'qwen-vl-utils>=0.0.14'
```

向 `--model` 传模型仓库 ID 时，首次运行会下载 Qwen3-VL 权重；也可预先下载到本地并传模型目录。服务器已验证的目录为 `models/Qwen3-VL-8B-Instruct`。不要把权重、运行产物或新的原始视频提交到 Git。

## 冒烟测试

先用一个 20 秒片段验证加载与输出：

```bash
PYTHONPATH=src .venv/bin/python -m video_demo.cli analyze data/example/xzg_314700.mp4 \
  --output runs/sample-smoke --model models/Qwen3-VL-8B-Instruct --max-segments 1
```

成功后去掉 `--max-segments 1` 处理整个视频。默认每 20 秒抽取 4 帧；可用 `--segment-seconds` 和 `--frames-per-segment` 调整。使用 `--max-segments` 时结果标记 `complete=false`，不能视作整段视频结论。

输出包含 `result.json`、`summary.md`、`manifest.json`、`run.log` 和 `evidence/*.jpg`。当前事件是一段采样帧的描述，`person_id` 为 `null`，`people` 为空；`review_required=true`，需人工核对细节。L20 上已成功处理完整样例，耗时和已发现的描述质量问题见 [`docs/sample-run-2026-09-17.md`](docs/sample-run-2026-09-17.md)。

## 测试

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

详细设计见 [`docs/mvp-technical-spec.md`](docs/mvp-technical-spec.md)，实施状态见 [`docs/plans/2026-09-16-mvp-implementation.md`](docs/plans/2026-09-16-mvp-implementation.md)。
