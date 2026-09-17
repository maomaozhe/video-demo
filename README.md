# video-demo

本地视频理解 MVP。按镜头与重叠时间片采样，使用 RT-DETR/BoT-SORT 跟踪、FastReID 提取外观向量、faster-whisper 转写，以及 Qwen3-VL 生成带帧证据的事件候选。后处理负责匿名人物 ID、时间和证据校验、中文时间线。跨镜头匹配阈值必须先在授权标注集上校准；未给阈值时只提供待复核候选。

## 服务器准备

在 `~/video-demo` 的 Python 3.11 虚拟环境安装 PyTorch CUDA 版本（见 [`docs/server-environment.md`](docs/server-environment.md)），然后安装模型依赖：

```bash
uv pip install --python .venv/bin/python -e '.[inference]' lap
```

PyTorch CUDA 版本另按服务器文档安装。运行前准备本地 Qwen3-VL、RT-DETR、faster-whisper 权重。FastReID 官方仓库和匹配的配置、权重可单独放在 `models/` 下；其源代码依赖 `yacs termcolor tabulate scikit-learn`。服务器已准备 `models/Qwen3-VL-8B-Instruct`、`models/rtdetr-l.pt`、`models/faster-whisper-small`、`models/fast-reid` 和 `models/market_bot_R50.pth`。运行时都传本地路径，不依赖云服务。不要把权重、运行产物或新的原始视频提交到 Git。

## 冒烟测试

先用一个 20 秒片段验证加载与输出：

```bash
PYTHONPATH=src .venv/bin/python -m video_demo.cli analyze data/example/xzg_314700.mp4 \
  --output runs/spec-smoke --model models/Qwen3-VL-8B-Instruct \
  --detector models/rtdetr-l.pt --asr-model models/faster-whisper-small \
  --reid-repository models/fast-reid \
  --reid-config models/fast-reid/configs/Market1501/bagtricks_R50.yml \
  --reid-weights models/market_bot_R50.pth --max-segments 1
```

成功后去掉 `--max-segments 1` 处理整个视频。默认镜头内 20 秒片段、2 秒重叠，事件采样约 1 FPS、跟踪约 3 FPS。可用 `--segment-seconds` 调整片长，`--task-config tasks.yaml` 传入 `tasks:` 字符串列表。使用 `--max-segments` 时结果标记 `complete=false`，不能视作整段视频结论。

输出包含 `result.json`、`summary.md`、`tracks.json`、`frames.json`、`manifest.json`、`run.log`、`evidence/*.jpg`；有可信语音时另有 `transcript.json`。处理过程中保存 `events.partial.json`。未校准 FastReID 阈值时不自动合并跨镜头轨迹，`P1` 等只表示当前局部轨迹并附待复核状态。完整规格对齐样例及效果限制见 [`docs/spec-alignment-run-2026-09-17.md`](docs/spec-alignment-run-2026-09-17.md)。

完整分析还会生成 `narrative.md`（全片综合描述和逐段细节）与 `narrative.json`（逐段文字及采样帧编号）。已有完整运行可复用已保存的帧追加生成：`PYTHONPATH=src .venv/bin/python -m video_demo.cli narrate --run runs/spec-full --model models/Qwen3-VL-8B-Instruct`。详细报告是模型对采样画面的描述，衣着、动作和跨片段身份仍需人工核对；原有 `summary.md` 保留为校验事件的摘要。

完整运行后可用 `PYTHONPATH=src .venv/bin/python scripts/validate_run.py runs/spec-full` 检查时间、人物轨迹、证据帧和摘要是否一致。此检查是结构审计，不替代人工核对动作或人物身份。

## 在网页查看结果

服务器 `~/video-demo/runs/` 下的多次运行可在只读网页中查看。页面按输入视频汇总运行记录，展示摘要、时间线、证据帧、原始 JSON、运行参数和文件下载；优先打开最新的完整运行。先在服务器启动服务：

```bash
cd ~/video-demo
PYTHONPATH=src .venv/bin/python -m video_demo.web --runs-dir runs --port 8765
```

保持该终端运行。在 Windows 的另一个 PowerShell 窗口建立 SSH 隧道（交互式输入 SSH 密码或使用已配置的密钥）：

```powershell
ssh -N -L 127.0.0.1:8765:127.0.0.1:8765 dylan@101.47.18.72
```

保持隧道窗口运行，然后在 Windows 浏览器打开 **http://127.0.0.1:8765/**。服务器仅监听本机回环地址，网页不会直接暴露在公网。关闭隧道窗口后，需要重新运行上面的 `ssh` 命令才能访问。当前服务器已启动结果服务并有 `sample-full` 完整样例可查看；服务进程若停止，需在服务器重新执行启动命令。详见 [`docs/development-workflow.md`](docs/development-workflow.md)。

## 测试

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

详细设计见 [`docs/mvp-technical-spec.md`](docs/mvp-technical-spec.md)，实施状态见 [`docs/plans/2026-09-16-mvp-implementation.md`](docs/plans/2026-09-16-mvp-implementation.md)。
