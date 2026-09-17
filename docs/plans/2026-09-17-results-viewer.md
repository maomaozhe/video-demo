# Results Viewer Implementation Plan

**Goal:** 通过本机 URL 浏览服务器上每个视频的摘要、事件、JSON 和证据帧。

**Architecture:** Python 标准库 HTTP 服务从 `runs` 读取结果，仅监听服务器环回地址；Windows SSH 隧道映射到 `localhost:8765`。前端为同源静态资源，无额外构建依赖。

**Tech Stack:** Python 3.11 `http.server`、HTML/CSS/JavaScript、`unittest`。

---

## Task 1：只读结果索引和文件接口

**Files:** 创建 `src/video_demo/result_store.py`、`tests/test_result_store.py`。

1. 写失败测试：多次运行按输入 SHA 聚合；缺失文件或损坏 JSON 不出现在列表；只允许引用过的证据帧。
2. 运行测试确认缺失功能而失败。
3. 实现运行扫描、聚合和证据路径校验。
4. 运行相关测试和全量测试。

## Task 2：HTTP 服务

**Files:** 创建 `src/video_demo/web.py`、`tests/test_web.py`；修改 `pyproject.toml` 包数据配置。

1. 写失败测试：列表/详情/下载接口返回正确内容和 MIME；路径穿越与写请求被拒绝；监听地址固定环回。
2. 运行失败测试，再实现最小服务。
3. 运行测试确认通过。

## Task 3：页面

**Files:** 创建 `src/video_demo/web_assets/index.html`、`app.js`、`style.css`。

1. 根据测试 API 构建按视频和运行记录选择的只读页面。
2. 展示摘要、事件时间线、证据图和原始 JSON；提供三个文件下载链接。
3. 在浏览器检查桌面与窄屏布局、中文文本、无结果状态和错误提示。

## Task 4：部署与文档

**Files:** 更新 `README.md`、`docs/development-workflow.md`、`docs/server-environment.md`。

1. 本地全量测试并提交推送；服务器拉取、复测。
2. 在服务器以后台进程启动只监听 `127.0.0.1:8765` 的服务。
3. 在 Windows 建立 SSH 转发，访问 `http://localhost:8765`，核对真实 `sample-full` 数据。
4. 记录启动、重连、停止方法与实际验证结果。
