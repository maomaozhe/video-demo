# Local Video MVP Implementation Plan

> 执行原则：每个行为先写失败测试，再实现最小代码；每个阶段在服务器用真实命令验证并记录结果。当前工作分支：`feat/mvp-pipeline`。

**Goal:** 离线输入一个视频，输出带时间戳和证据的中文事件时间线，并为反复出现的人分配匿名 ID。

**Architecture:** Windows 仓库是代码来源，服务器 HTTPS 拉取功能分支并运行 GPU 推理。视频理解与人物跟踪分别产出中间 JSON，最后由聚合模块校验时间和证据并生成结果。

**Tech Stack:** Python 3.11、FFmpeg、PyTorch CUDA、Qwen3-VL、RT-DETR、BoT-SORT、FastReID、faster-whisper；纯逻辑测试先用标准库 `unittest`。

---

## Task 1：服务器环境与 GPU 冒烟测试

**Files:** 更新 `docs/server-environment.md`、`docs/development-workflow.md`。

1. 记录 `nvidia-smi`、Python、FFmpeg、磁盘、Git 分支与实际网络可达性。
2. 安装独立 Python 3.11 虚拟环境，不修改系统 Python。
3. 固定 PyTorch/CUDA 包版本，运行 `torch.cuda.is_available()` 和小张量 GPU 运算。
4. 将实际命令、版本与故障处理写入环境文档。

**通过条件：** GPU 张量运算成功；系统 Python 和其他进程未受影响。

**当前状态：** Python 3.11.16 和虚拟环境已就绪；PyTorch CUDA 依赖仍在后台下载，GPU 张量测试待执行。

## Task 2：输入、时间戳与结果结构

**Files:** 创建 `pyproject.toml`、`src/video_demo/schema.py`、`src/video_demo/video.py`、`tests/test_video.py`、`tests/test_schema.py`。

1. 先写测试：缺失/损坏视频给明确错误；合法视频返回时长、尺寸；事件时间范围越界被拒绝。
2. 运行测试并确认因功能缺失而失败。
3. 实现 FFprobe 元数据读取、时间戳标准化及结果数据结构。
4. 运行全量测试；提交。

**通过条件：** 使用合成短视频即可在 Windows 或服务器验证纯逻辑，无须下载大模型。

**当前状态：** 已实现视频探测和事件时间/证据校验；`PYTHONPATH=src python -m unittest discover -s tests -v` 在 Windows Python 3.12 下通过 7 项测试。服务器 Python 3.11 复测待代码同步后执行。

## Task 3：视频描述的最小闭环

**Files:** 创建 `src/video_demo/vlm.py`、`src/video_demo/cli.py`、`tests/test_cli.py`，更新 `README.md`。

1. 先写 CLI 测试：有效视频生成 `result.json`、`summary.md`；模型返回错误时保留明确日志。
2. 运行测试并确认失败；用可替换的模型调用边界实现 CLI 与产物写入。
3. 在服务器安装 Qwen3-VL 依赖和权重，对 10–30 秒样本运行一次。
4. 检查时间戳、证据来源和中文描述；记录模型与参数；提交。

**通过条件：** 一个样本视频能从 CLI 离线生成可解析 JSON 与中文摘要。

## Task 4：人物跟踪与跨镜头关联

**Files:** 创建 `src/video_demo/tracking.py`、`src/video_demo/reid.py`、`tests/test_identity.py`。

1. 先写测试：同一轨迹保持 ID；时间上同时出现的两人不得合并；不确定匹配进入待复核。
2. 运行失败测试后实现轨迹数据结构、关联规则和阈值配置。
3. 接入人体检测、BoT-SORT 和 FastReID；用真实重复出镜视频评估误合并/误拆分。
4. 将局部轨迹映射到 `P1`、`P2` 等全局 ID；提交。

**通过条件：** 能导出轨迹证据和全局人物映射，并对不确定候选保留人工复核状态。

## Task 5：语音、汇总与验收

**Files:** 创建 `src/video_demo/asr.py`、`src/video_demo/report.py`、`tests/test_report.py`，更新两份使用文档。

1. 先写报告测试：摘要只引用已校验事件；无证据时不能写“已完成”。
2. 运行失败测试，接入 faster-whisper、事件校验和 Markdown 输出。
3. 在有/无语音样本上运行完整流程，检查峰值显存、耗时和产物。
4. 记录已知失败案例、人工复核结果与运行命令；提交。

**通过条件：** 满足 `docs/mvp-technical-spec.md` 的工程闭环验收项。

## 当前阻塞信息

- 需要一段有使用权限、包含人物反复出镜的短视频做效果验证。
- GitHub HTTPS 已在服务器使用；代码推送由 Windows 进行，服务器拉取同一提交。
