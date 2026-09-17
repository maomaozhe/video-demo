# 临时公网查看结果页

更新日期：2026-09-17。

服务器上的结果服务仍只监听 `127.0.0.1:8765`。由于云侧网络规则阻止外部访问新开的 8766 端口，当前由服务器上的 Caddy 在 `:8766` 执行整站 HTTP Basic 验证，再由 Cloudflare Quick Tunnel 提供临时公网 HTTPS 地址。请求链路为：浏览器 → Cloudflare → `cloudflared` → Caddy → 本机结果服务。Cloudflare 会经手页面和证据帧数据；不要把这条临时入口当作长期生产部署。

配置和日志位于服务器用户目录，均不入 Git：

| 用途 | 路径 |
| --- | --- |
| Caddy 配置，含用户名和密码哈希 | `~/.config/video-demo-viewer/Caddyfile` |
| Caddy 日志 | `~/.local/state/video-demo-viewer/caddy.log` |
| Tunnel 日志，含当前随机 URL | `~/.local/state/video-demo-viewer/tunnel.log` |

验证方式：公网地址未带认证时应返回 `401`；使用正确用户名和密码后首页及 `/api/videos` 应返回 `200`。入口必须覆盖页面、JSON、Markdown 和证据图片，不应只保护首页。**密码不写入仓库或命令行历史。**

若进程停止，可在服务器分别启动：

```bash
cd ~/video-demo
PYTHONPATH=src .venv/bin/python -m video_demo.web --runs-dir runs --port 8765
caddy run --config ~/.config/video-demo-viewer/Caddyfile --adapter caddyfile
cloudflared tunnel --url http://127.0.0.1:8766
```

以上三条命令各需一个终端，或交由进程管理器维护。Quick Tunnel 重启后会生成**新的随机 URL**，可从 `tunnel.log` 查找；服务没有固定地址或可用性保证。若需要稳定公网地址，应在云安全组开放入口端口并配置正式 HTTPS 域名，或使用有账号的命名 Tunnel。不要直接将结果服务绑定到公网。
