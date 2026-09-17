# L20 服务器环境与验证记录

更新日期：2026-09-17。此页只记录已经在服务器上看到的事实和执行过的命令；登录密码、访问令牌和私钥不写入仓库。

## 系统清单

| 项目 | 实测结果 |
| --- | --- |
| 操作系统 | Ubuntu 20.04.5 LTS，Linux 5.4.0-186-generic，x86_64 |
| GPU | NVIDIA L20，`nvidia-smi` 报告总显存 46068 MiB |
| 驱动 | 580.178.04；`nvidia-smi` 显示 CUDA 13.0（驱动支持上限，非 Toolkit 安装版本） |
| CPU / 内存 | 用户提供 22 核；服务器 `free -h` 报告 117 GiB 总内存、约 82 GiB 可用（检查时） |
| 系统 Python | 3.8.10；未修改 |
| FFmpeg | 4.2.7，已安装 |
| 根分区 | 504 GB 总量，约 259 GB 可用（检查时） |
| 仓库 | `~/video-demo`，HTTPS 远端，`feat/mvp-pipeline` 分支 |
| 项目 Python | 已用 `uv 0.12.15` 安装独立 CPython 3.11.16，虚拟环境位于 `~/video-demo/.venv` |
| 项目 PyTorch | `torch 2.9.1+cu128`、`torchvision 0.24.1+cu128`；`torch.cuda.is_available()` 为 `True`，GPU 张量求和得到 4.0 |
| 视频模型依赖 | `transformers 4.57.6`、`qwen-vl-utils 0.0.14`、`accelerate 1.15.0` |

用户先前提供的 `df -h` 显示 `/tmp/affine-l20-preflight-20260912/ram-shards` 使用率为 93%。这是单独的 tmpfs 挂载；不在其中放模型或临时视频，也不清理可能属于其他任务的数据。

## 已完成检查

- Windows 到服务器的 TCP 22 端口可达；已通过交互式 SSH 登录验证。
- 服务器可访问 `astral.sh`、PyTorch CUDA 12.8 索引和 Hugging Face 的 Qwen3-VL 配置文件。
- `uv`、Python 3.11.16 和项目虚拟环境已安装，系统 Python 仍为 3.8.10。
- 服务器已拉取 `b082632`，在项目 Python 3.11 虚拟环境运行 `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v`，7 项测试通过。
- 服务器随后拉取 `9232f94`，同一命令复测通过 12 项；`PYTHONPATH=src .venv/bin/python -m video_demo.cli --help` 正常显示 `analyze` 子命令。
- 服务器再拉取 `0592107`，运行 `PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q` 通过 18 项测试；拉取 `ce8c7b5` 后复测仍通过 18 项。
- 已用项目代码探测样例 `data/example/xzg_314700.mp4`：207234 ms、1280×720、30 FPS、含音轨。该样例由用户主动提交到 Git，是此前“不提交原始视频”约定的一次例外。
- `models/Qwen3-VL-8B-Instruct` 有四个完整的 safetensors 分片，模型加载成功；目录中还有一个旧的 `.incomplete` 下载残留，未参与加载。
- 运行 `PYTHONPATH=src .venv/bin/python -m video_demo.cli analyze data/example/xzg_314700.mp4 --output runs/sample-smoke-v2 --model models/Qwen3-VL-8B-Instruct --max-segments 1` 成功处理首个 20 秒片段。产物位于 Git 忽略的 `runs/sample-smoke-v2/`，包括 4 张证据帧、`result.json`、`summary.md`、`manifest.json` 和 `run.log`。结果为一个 32 字中文描述，`complete=false`、`people=[]`，并明确提示人物关联未启用。
- 同一次首段推理用 `/usr/bin/time` 测得墙钟时间 95.45 秒、进程峰值 RSS 5877932 KiB。首次运行生成了被截断的逐帧描述；已在 `ce8c7b5` 收紧提示词并加入 token 上限检查后重跑成功。
- 完整 207.234 秒样例推理也已完成：11 个连续片段、44 张证据帧，984.68 秒，显存峰值 18403 MiB。结构和人工抽查见 [样例运行报告](sample-run-2026-09-17.md)。
- 服务器已拉取 `8902c42` 并运行 27 项测试通过。只读结果网页在 `127.0.0.1:8765` 监听，Windows 通过 SSH 本机隧道访问；首页、视频列表 API、真实证据帧均返回 HTTP 200。浏览器中已验证 `sample-full` 的 11 段与 44 帧、JSON 与文件下载入口，以及切换到 `sample-smoke-v2` 后显示 1 段与 4 帧。启动与连接命令见 [开发调试流程](development-workflow.md#结果网页与-ssh-隧道)。

## PyTorch 安装记录

初次使用未固定版本的 CUDA 12.8 索引，解析到 PyTorch 2.11.0，下载其 `cuda-toolkit==12.8.1` 依赖时超时。官方[历史版本安装页](https://pytorch.org/get-started/previous-versions/)提供 PyTorch 2.9.1 与 torchvision 0.24.1 的 CUDA 12.8 组合。固定该组合后，依赖解析不再包含 `cuda-toolkit`，但下载 `nvidia-curand-cu12` 时仍超时。对该文件的单独 1 MiB 范围请求成功，因此正在用较长 HTTP 超时验证是否为大文件请求超时。

提高 `UV_HTTP_TIMEOUT` 后部分依赖继续下载，但安装长时间没有完成，2026-09-16 人工中止该安装请求。随后检查确认：虚拟环境里当时没有 PyTorch；`~/.cache/uv` 当时有约 2.3 GB 下载缓存。下载测速显示 NVIDIA 包站约 1.2 MB/s。Docker 已安装，但当前 `dylan` 账号无权限访问 Docker daemon。随后使用 `UV_CONCURRENT_DOWNLOADS=1 UV_HTTP_TIMEOUT=300` 在后台继续安装 PyTorch 2.9.1 + torchvision 0.24.1，日志位于 `~/video-demo/runs/torch-install.log`。这份日志最终记录 859 MiB 的 torch wheel 连接超时；但 2026-09-17 实际检查项目虚拟环境时，PyTorch 已安装且 GPU 张量计算成功。以实测运行状态为准，不据该旧日志判断当前安装失败。系统驱动和系统 Python 均未修改。

## 下一步验证

1. 接入人物检测和跨镜头匹配后，用该样例的重复出镜人物验证匿名 ID。
2. 为“倒塌”“已完成”等结果性描述增加证据检查，并接入语音转写。
