# 部署指南

示例项目路径为 `/opt/storyframe-studio`，示例域名为 `studio.example.com`，请替换为自己的路径和域名。只启动一个 Worker，不横向扩容 SQLite 任务队列。

## 环境与配置

1. 安装 Docker Compose、Python 3.12、Node.js 22+、Nginx。
2. 创建 `.venv` 并安装 `requirements.lock`；执行 `scripts/init-env.py` 生成稳定的 `.env`，不要重复生成已投入使用的 `ENCRYPTION_KEY`。
3. 创建 `runtime/`、`metrics/`，让容器 UID 1000 可读写；按实际账号调整所有权，不使用全局可写权限。
4. 调整 `scripts/host-metrics.py` 和 `scripts/drama-host-metrics.service` 的路径、用户与权限，将服务安装到 systemd 并启动。确认 `metrics/host-metrics.json` 持续更新。
5. 根据实际域名设置 `.env`、Compose 中的 `ALLOWED_HOSTS`、`CSRF_TRUSTED_ORIGINS`，以及 `PUBLIC_ORIGIN`。

指标目录只读挂载；不要单独挂载指标文件，否则原子替换后容器可能继续读取旧文件。

## 启动

按 `scripts/deploy.sh` 执行前端安装与构建、容器构建、迁移和管理员初始化，再启动 `web`、`worker`。脚本需要本机 Docker 或免密码 sudo 权限。

更新服务前检查是否有活动生成任务，等待结束后再部署。生产更新前应备份数据库、素材和 `.env`。

后端只监听 `127.0.0.1:8011`。使用 `nginx/studio.conf` 建立回环 `8010` 入口，或根据 `nginx/public-https.conf` 配置自己的公网域名和证书。检查 `nginx -t` 后再重新加载。

不要把 `runtime/media` 配成公开静态目录。签名素材仅通过专用接口短期访问。使用公网 HTTPS 时配置 `HTTPS_ENABLED=true`，并保持入口保护及账号认证。

Nginx 公网静态目录指向宿主机 `frontend/dist`；项目上级目录需要允许 Nginx 遍历，静态文件应只读可访问。部署到已有服务器时使用独立站点和端口，保留其他应用。

## 资源限制

Web 和 Worker 使用各自的内存与 CPU 限制；运行镜像只读，仅 `runtime` 与临时目录可写。`metrics` 目录只读。

容器构建的镜像源可按网络环境替换，不是业务依赖。

## 备份恢复

`sh scripts/backup.sh /absolute/new-backup-directory` 会暂停本项目服务，使数据库与素材处于同一备份窗口，并在退出时重新启动。该操作会产生短暂停机，执行前确认没有生成任务。

`sh scripts/restore.sh backup-directory new-isolated-target` 校验摘要、解包并检查 SQLite 完整性。恢复目标必须不存在，避免覆盖现有运行数据。

恢复时必须使用原有加密密钥。项目没有自动离机备份、自动主备切换或固定 RPO/RTO 承诺。
