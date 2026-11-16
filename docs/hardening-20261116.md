# 2026-11-16 线上加固记录

对公网部署（https://8.133.224.94/）做了一轮只读体检，随后实施的改动、验证方式与回滚方法记录在这里。

## 一、体检发现

| 项目 | 发现 |
|---|---|
| Django 后台 | `/admin/` 对公网开放，且仍在使用初始管理员口令 → 一个弱口令等于整个数据库 |
| 传输层 | 无 HSTS；HTTP(80) 未跳转到 HTTPS，裸 IP 访问落到别的默认站点 |
| HTTP/2 | 未启用（ALPN 协商为 http/1.1） |
| 版本暴露 | `Server: nginx/1.24.0 (Ubuntu)` |
| 健康检查 | `/health/` 匿名可读，暴露 worker 存活状态 |
| 静态资源 | 只缓存 7 天（文件名已带内容 hash，可长缓存） |
| favicon | 缺失，`/favicon.ico` 被 SPA fallback 返回 index.html |
| 点文件 | SPA fallback 把 `/.env`、`/.git/config` 也返回 200 |
| 错误结构 | `?limit=abc` 返回裸数组 `["分页参数无效"]`，其余接口都是 `{"detail": ...}`，前端封装只读 `detail`，此类错误会显示成 `0: 分页参数无效` |

另核对：证书自动续期（`drama-cert-renew.timer`，每日四次，webroot 方式，ACME 走 80 端口）工作正常。

## 二、改动

### 1. nginx

- `drama-public.conf`
  - `listen 443 ssl http2`（启用 HTTP/2）
  - `server_tokens off`
  - `add_header Strict-Transport-Security "max-age=31536000" always`
  - `location ^~ /admin/`、`location = /admin` → `return 404`（需要后台时走回环入口 + SSH 隧道）
  - `location = /health/` → 仅 `127.0.0.1 / ::1`，其余 403
  - `location /assets/` → `expires 1y`
  - `location = /favicon.ico` → 直出图标
  - `location ~ /\.(?!well-known)` → `deny all`
  - `charset utf-8`
  - 保留 `/demo/` 演示站（HSTS 生效后浏览器会把它的 http 访问升级到 https，因此在 443 上补了同名转发）
- 新增 `drama-http.conf`：`listen 80`，只保留 ACME 校验路径，其余 `301` 到 HTTPS

备份：改动前配置归档在服务器 `/home/admin/nginx-backup-<时间戳>/`。

### 2. 后端

`backend/core/views.py`：14 处裸字符串 `raise ValidationError("…")` 统一为 `raise ValidationError({"detail": "…"})`，与鉴权失败、404 等接口的错误结构保持一致。

DRF 的 `ValidationError` 会把非 dict/list 的细节强制包成列表，所以此前这些错误返回的是 `["…"]`。

### 3. 前端

- 新增 `frontend/public/favicon.ico`、`favicon.png`
- `frontend/index.html` 增加 `<link rel="icon" href="/favicon.ico">`

## 三、验证

从公网侧做了 21 项只读断言，全部通过：HTTP→HTTPS 跳转、ACME 路径不被跳转、HSTS / X-Frame-Options / CSP / server_tokens、`/admin/` 404、`/health/` 403、点文件 403、SPA 首页与子路由正常、API 匿名 403、favicon 200、静态资源 200 且 `max-age=31536000`、`/demo/` 200、ALPN 协商为 `h2`。

后端用 Django 测试客户端验证（不需要口令）：

```
GET /api/jobs/?limit=abc  -> 400 {"detail":"分页参数无效"}
GET /api/jobs/?limit=0    -> 200 limit=1
GET /api/jobs/            -> 200 total=17
```

测试套件：容器内 `pytest tests` 结果 `73 passed, 18 failed`，与改动前镜像 **完全一致**（失败项来自测试容器 `/tmp` 为 32MB tmpfs，触发 `core.queue.resource_check()` 的 5GB 磁盘下限，属环境约束，不是代码回归）。

## 四、回滚

```bash
# nginx
sudo cp -a /home/admin/nginx-backup-<时间戳>/drama-public.conf /etc/nginx/sites-available/drama-public
sudo rm -f /etc/nginx/sites-enabled/drama-http
sudo nginx -t && sudo systemctl reload nginx

# 后端 / 容器
sudo docker tag drama-studio:pre-hardening drama-studio:local
cd /home/admin/drama-platform && sudo docker compose up -d web worker
```

后端源码改动前的副本在 `/home/admin/drama-backup-<时间戳>/views.py`。

## 五、未做 / 待办

- **自建修改密码页面**：前端只有 `auth/login`、`auth/logout`、`auth/me`，改密仍需进 Django 后台（现已不对公网开放，走 SSH 隧道）。
- **登录限流**：未做无损验证（担心按 IP 限流把自己锁住），建议换一台机器连续输错 5 次确认是否 429。
- **自动离机备份**：`scripts/backup.sh` 需要确认是否已进 cron，且备份应落到另一台机器或对象存储。
- **HTTP/3 / OCSP stapling**：需要域名与更完整的证书链配置，当前为 IP 证书（Let's Encrypt shortlived profile）。

## 六、演示账号（面向招聘方）

公网可访问的只读体验账号，凭据直接写在登录页：

- 账号 `demo` / 密码 `mirror2026`
- 预置内容：1 个画布（「3 元全流程 · 白发红瞳人物短片」，8 节点，revision 87）、2 个剧本、5 个素材、2 条已成功任务（含可直接下载的成片）
- 额度 300MB / API 次数 20；**没有配置任何供应商**，因此不具备生成能力，不会产生费用
- 数据是 admin 工作区的独立副本，两端互不影响

重建方式（先在 Django 后台删掉 demo 用户，会级联清空其数据）：

```bash
sudo docker compose run --rm --no-deps -T \
  -v $PWD/scripts/clone-demo-user.py:/app/clone_demo.py:ro \
  --entrypoint python web /app/clone_demo.py --commit
```

## 七、备份

- `drama-backup.timer`：每日 03:40（随机延迟 5 分钟，`Persistent=true`）执行 `scripts/backup-daily.sh`
- 内容：停服一致快照 `runtime.tar.gz`（含 SQLite 与媒体）+ `manifest.sha256` + `.env`（恢复必需的加密密钥）+ 两份 nginx 站点配置
- 保留 7 份；日志 `/var/log/drama-backup.log`；**检测到活动任务时自动跳过**，避免打断生成
- 校验：备份后立即 `sha256sum -c` + `tar -tzf` 可读性检查
- 离线副本：Windows 计划任务「镜序备份拉取」每日 12:30 把最新一份拉回本机（保留 3 份，同样校验摘要）

手动触发一次：

```bash
sudo systemctl start drama-backup.service
systemctl status drama-backup.service
```
