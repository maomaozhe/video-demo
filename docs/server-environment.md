# L20 服务器环境与验证记录

更新日期：2026-09-16。此页只记录已经在服务器上看到的事实和执行过的命令；登录密码、访问令牌和私钥不写入仓库。

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

用户先前提供的 `df -h` 显示 `/tmp/affine-l20-preflight-20260912/ram-shards` 使用率为 93%。这是单独的 tmpfs 挂载；不在其中放模型或临时视频，也不清理可能属于其他任务的数据。

## 已完成检查

- Windows 到服务器的 TCP 22 端口可达；已通过交互式 SSH 登录验证。
- 服务器可访问 `astral.sh`、PyTorch CUDA 12.8 索引和 Hugging Face 的 Qwen3-VL 配置文件。
- `uv`、Python 3.11.16 和项目虚拟环境已安装，系统 Python 仍为 3.8.10。
- 当前仓库只含文档及 `.gitignore`，尚无 MVP 可执行代码；模型权重尚未下载。

## PyTorch 安装记录

初次使用未固定版本的 CUDA 12.8 索引，解析到 PyTorch 2.11.0，下载其 `cuda-toolkit==12.8.1` 依赖时超时。官方[历史版本安装页](https://pytorch.org/get-started/previous-versions/)提供 PyTorch 2.9.1 与 torchvision 0.24.1 的 CUDA 12.8 组合。固定该组合后，依赖解析不再包含 `cuda-toolkit`，但下载 `nvidia-curand-cu12` 时仍超时。对该文件的单独 1 MiB 范围请求成功，因此正在用较长 HTTP 超时验证是否为大文件请求超时。

提高 `UV_HTTP_TIMEOUT` 后部分依赖继续下载，但安装长时间没有完成，2026-09-16 人工中止该安装请求。随后检查确认：虚拟环境里**没有安装 PyTorch**，没有残留的 `uv pip install` 进程；`~/.cache/uv` 有约 2.3 GB 下载缓存。不能据此声称 GPU 推理已可用。下一次尝试需限制并行下载或改用可验证的镜像/容器，并在安装后运行 GPU 张量测试。安装过程未修改系统驱动和系统 Python。

## 下一步验证

1. 解决 CUDA 依赖包下载停滞；PyTorch 安装成功后执行 GPU 小张量运算，记录 `torch.__version__`、`torch.version.cuda`、`torch.cuda.is_available()` 和设备名。
2. 安装 Qwen3-VL 最小依赖并下载指定模型权重到项目或用户目录下的持久缓存。
3. 用有使用权限的短视频做视频理解冒烟测试，并记录时间、显存、输出。
4. 接入人物检测和跨镜头匹配后，用重复出镜样本验证人物 ID。
