# Windows 开发 + L20 服务器调试流程

日期：2026-09-16  
适用范围：`video-demo` 的单视频离线 MVP。以下命令假设服务器运行 Linux；先用第 3 节确认系统，若不是 Linux，应调整环境搭建方式。技术需求见 [mvp-technical-spec.md](mvp-technical-spec.md)。

## 1. 推荐的工作方式

```text
Windows：写代码、提交 Git、运行不依赖 GPU 的单元测试
    │ Git 推送/拉取；少量样本用 SCP 上传
    ▼
Linux L20 服务器：存放模型和视频、运行 GPU 推理、调试完整流程
    │ JSON/Markdown/关键帧，用 SCP 下载或 VS Code Remote-SSH 查看
    ▼
Windows：人工核对事件与人物 ID，修正代码
```

源代码用 Git 同步；**视频、模型权重、生成结果和密钥不进 Git**。Windows 上的 `E:\GitHub\video-demo` 是独立 Git 仓库，其父目录 `E:\GitHub` 也有另一个仓库。对本项目执行 Git 命令时始终进入 `video-demo`，避免把其他项目的改动混入提交。`main` 保存规格基线，`feat/mvp-pipeline` 用于 MVP 代码开发；推送 GitHub 还需配置远程仓库地址。

开发工具建议用 VS Code 的 Remote-SSH：Windows 上操作编辑器，终端、Python 调试器和 GPU 进程运行在服务器。平时仍可在 Windows 工作目录编辑；选择其中一种副本为每次改动的来源，使用 Git 同步，避免本地和远端同时修改同一文件。[VS Code 官方说明](https://code.visualstudio.com/docs/remote/ssh)

## 2. 先处理登录凭据

服务器密码曾出现在聊天内容中。先在服务器或云平台控制台更换密码；项目文档、源码、`.env` 和终端历史中都不要保存该密码。之后为 Windows 开发机配置独立 SSH 密钥。

在 PowerShell 中生成密钥（交互式设置口令）：

```powershell
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\video_demo_ed25519" -C "video-demo-windows"
```

将公钥追加到服务器 `~/.ssh/authorized_keys`。首次操作会交互式输入已更换的服务器密码，**不要把密码写在命令行参数里**：

```powershell
Get-Content "$env:USERPROFILE\.ssh\video_demo_ed25519.pub" | ssh dylan@<服务器地址> 'umask 077; mkdir -p ~/.ssh; cat >> ~/.ssh/authorized_keys; chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys'
```

在 Windows 的 `~/.ssh/config` 配置别名，不写密码：

```sshconfig
Host video-l20
    HostName <服务器地址>
    User dylan
    Port 22
    IdentityFile ~/.ssh/video_demo_ed25519
    IdentitiesOnly yes
```

验证 `ssh video-l20` 使用密钥登录成功后，再在 VS Code 中执行 `Remote-SSH: Connect to Host...`，选择 `video-l20`。首次连接时核对服务器主机指纹。若计划关闭密码登录，应先确认密钥登录和应急控制台都可用，再由服务器管理员修改 SSH 配置。

## 3. 服务器只读体检

先登录运行以下命令，把输出用于确定依赖版本和模型大小：

```bash
uname -a
cat /etc/os-release
nvidia-smi
nvidia-smi --query-gpu=name,memory.total,memory.free,driver_version --format=csv
python3 --version
ffmpeg -version
df -h
free -h
docker --version
```

2026-09-16 已确认：Ubuntu 20.04.5、Python 3.8.10、FFmpeg 4.2.7、根分区约 259 GB 可用；`nvidia-smi` 显示 L20 有 46068 MiB 显存、当时无 GPU 进程，驱动 580.178.04。当前 `nvidia-smi` 的 CUDA 13.0 代表驱动支持的最高 CUDA 版本，不等于机器已安装 CUDA 13 Toolkit。新驱动可运行较旧 CUDA 运行时构建的程序，PyTorch 安装时选择其官方提供的匹配构建并用 `torch.cuda.is_available()` 实测。[NVIDIA CUDA 兼容性说明](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html)、[PyTorch 安装页](https://pytorch.org/get-started/locally/)

系统 Python 3.8 不要直接改动。项目推荐 Python 3.11 独立虚拟环境；例如可用 `uv python install 3.11` 和 `uv venv --python 3.11` 安装，不影响系统 Python。[uv Python 管理文档](https://docs.astral.sh/uv/concepts/python-versions/)

服务器环境先用 Python 虚拟环境跑通 MVP；确认模型和 CUDA 版本后再固定依赖，避免一开始同时排查 Docker、驱动、模型和代码。若后续改用 GPU 容器，按 [NVIDIA Container Toolkit 文档](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)配置并验证 `docker run --gpus all ... nvidia-smi`。

## 4. 仓库与目录约定

建议服务器目录：

```text
~/video-demo/             # 代码与小型配置，来自 Git
~/video-demo/data/samples/ # 有权限使用的小样本视频
~/video-demo/runs/         # 每次分析的 JSON、摘要、证据帧、日志
~/video-demo/models/       # 已下载的模型权重
```

Git 忽略已包括：`data/`、`runs/`、`models/`、`.env`、`__pycache__/`、`.venv/` 等。服务器上运行前先确认 `df -h`；视频、解码帧和模型缓存可能占用大量磁盘。不要将缓存放在 `/tmp/affine-l20-preflight-20260912/ram-shards`：用户提供的检查结果显示该 tmpfs 已使用 93%，而且其内容可能属于其他任务。

有 Git 远程仓库时：Windows 提交并推送，服务器在 `~/video-demo` 拉取同一提交，再运行分析。没有远程仓库时可临时用 `scp` 传输代码包；远程地址确定后配置 `origin`。首次推送只推 `main` 和功能分支，先检查 `git status`、`git diff --cached --stat`，确认没有视频、模型或秘密。

少量样本上传示例：

```powershell
scp "E:\GitHub\video-demo\data\example\sample.mp4" video-l20:~/video-demo/data/samples/
```

命令中的 `sample.mp4` 只是示例文件名；当前 `data/example` 目录没有样本文件。

## 5. 调试节奏

1. **本地快速测试**：Windows 上运行 JSON schema 校验、时间戳换算、事件去重、人物 ID 映射等纯逻辑测试；不在本机运行大模型。
2. **服务器模型冒烟测试**：先用 10–30 秒视频，单独确认 Qwen3-VL 能输出一个带时间点的事件，再确认检测与跟踪能够输出人物轨迹。
3. **完整链路测试**：只处理一个短视频，逐步生成中间文件；每一阶段失败时可复用已完成的解码帧/轨迹/转写，避免重复推理。
4. **远程断点调试**：用 VS Code Remote-SSH 打开服务器工作目录，在服务器 Python 环境设置断点。长任务放在 `tmux` 中执行并写日志，断线后可继续查看。
5. **结果复核**：下载或远程查看 `result.json`、`summary.md` 和证据帧，重点检查“同一人再次出现”和“任务已完成”的证据。

每次运行记录 Git 提交号、模型权重版本、输入文件哈希、采样率和阈值。调试时先使用固定短视频和固定参数，便于比较改动效果。

## 6. 首个可交付里程碑

先完成：`一个 10–30 秒本地样本 → 服务器 Qwen3-VL 推理 → 带时间点的事件 JSON → 中文摘要`。然后接人物检测、跟踪和跨镜头重识别。这个顺序能先确认 GPU、模型、解码和输出格式，避免人物算法尚未完成时整个项目没有可运行结果。

下一步需要服务器体检命令的输出，以及一段有权使用、包含人物反复出镜的样本视频。不要再发送密码、私钥或访问令牌。
