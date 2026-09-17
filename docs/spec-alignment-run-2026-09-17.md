# MVP 规格对齐运行报告（2026-09-17）

## 命令与产物

服务器：`dylan@101.47.18.72`，仓库 `~/video-demo`，L20。输入为服务器本地 `data/example/xzg_314700.mp4`（207.234 秒，1280×720，30 FPS，含音轨）。输出目录：`~/video-demo/runs/spec-full/`。

```bash
cd ~/video-demo
PYTHONPATH=src .venv/bin/python -m video_demo.cli analyze data/example/xzg_314700.mp4 \
  --output runs/spec-full --model models/Qwen3-VL-8B-Instruct \
  --detector models/rtdetr-l.pt --asr-model models/faster-whisper-small \
  --reid-repository models/fast-reid \
  --reid-config models/fast-reid/configs/Market1501/bagtricks_R50.yml \
  --reid-weights models/market_bot_R50.pth
```

退出码为 0。产物：`result.json`、`summary.md`、`tracks.json`、`frames.json`、`manifest.json`、`run.log`、`events.partial.json` 和 `evidence/*.jpg`。音轨没有可信语音，因此没有 `transcript.json`。原始结果和轨迹备份为 `result.json.before-reconcile` 与 `tracks.json.before-reconcile`。

## 实测结果

| 项目 | 结果 |
| --- | ---: |
| 镜头 / 重叠片段 | 2 / 12，全部处理 |
| 约 1 FPS 证据帧 | 207 |
| RT-DETR/BoT-SORT 局部轨迹 | 82 |
| FastReID 外观向量 | 82 条轨迹均取得 |
| 结构化事件 | 34（33 条 `进行中`、1 条 `无法判断`） |
| 待复核外观候选 | 336（同镜头与跨镜头分别保留最相关候选） |
| 可信语音片段 | 0 |
| 原运行墙钟 / manifest 计时 | 18:49.31 / 1121.47 秒 |
| PyTorch 峰值显存分配 | 18673.4 MiB（不等于整卡显存峰值） |
| 进程峰值 RSS | 5955788 KiB |
| 产物字节数 | 26647522（含更正前备份） |

模型及依赖：Qwen3-VL-8B-Instruct、RT-DETR-L、FastReID Market1501 BoT(R50)、faster-whisper-small；PyTorch 2.9.1+cu128、transformers 4.57.6、ultralytics 8.4.154、PySceneDetect 0.7.1、faster-whisper 1.2.1。权重 SHA256、FastReID 源码提交、运行参数和 Python 版本保存在 `manifest.json`；主要权重哈希另见 [服务器环境记录](server-environment.md)。

## 审计与更正

初次结构审计发现 15 条已绑定人物的事件各包含一张人物未出现在对应跟踪帧中的证据图。用 `scripts/reconcile_run.py` 保留原始 JSON 备份、移除这 15 张引用、将未校准的人物事件标为待复核，并把 3005 个外观相似候选筛为 336 个最相关候选；更正原因和时间记录在 `manifest.json` 与 `run.log`。图片本身未删除。

```bash
PYTHONPATH=src .venv/bin/python scripts/reconcile_run.py runs/spec-full
.venv/bin/python scripts/validate_run.py runs/spec-full
```

最终审计输出 `complete=true`、`errors=[]`：34 条事件时间均落在 207234 ms 内，引用的图像文件与 `frames.json` 一致；绑定 P 编号的每一张事件证据帧都包含相应局部轨迹；中文摘要与校验后的事件列表一致。最新代码又对首段执行一次未更正的直接运行 `runs/spec-smoke-v4/`：3 条事件、11 条轨迹、13 个待复核候选、144.88 秒，结构审计 `errors=[]`，三个事件均原生标记待复核；由于只处理首段，`complete=false` 是预期结果。Windows 最新 40 项单元测试通过。验证脚本核对结构和可追溯性，不评价“搭建”“推倒”等动作的视觉语义真伪。

## 效果限制与下一步

- 82 条轨迹明显是人物重复进出和跟踪碎片，不能解释为 82 个真实人物。未取得独立标注阈值，全部 P 编号与关联事件标记为待复核；跨镜头只给相似候选，没有自动合并。
- 该样例音轨上的 Whisper 初始结果出现重复/乱码；静音概率与解码质量过滤后无可信转写。需要含真实中文/英文语音的授权视频验证召回率，不能用本样例声称 ASR 准确。
- 模型声称“已完成”时自动降级为 `无法判断`；当前证据校验保证帧位置与人物出现，不保证帧内容足以证明每个动作。需人工抽看事件证据，尤其是结果性动作。
- [技术规格](mvp-technical-spec.md)要求至少 20 段授权标注视频，分离阈值校准和评估样本，报告事件精确率/召回率、时间误差、人物错合并/错拆分、完成证据支持率。当前只有一个工程样例，没有这些效果指标。
