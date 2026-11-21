# 本地开发指南

适用应用版本 `adbb539`。选用 Linux 或 Windows 上的 WSL 2。准备 Python 3.12、Node.js 22、FFmpeg 和 Noto CJK 字体。练习环境使用自己的数据库与素材目录，发布流程另见[部署指南](deployment-guide.md)。

## 初始化

在仓库根目录运行：

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.lock
.venv/bin/python scripts/init-env.py
chmod 600 .env
set -a
. ./.env
set +a
export CSRF_TRUSTED_ORIGINS=http://127.0.0.1:5173
.venv/bin/python backend/manage.py migrate
.venv/bin/python backend/manage.py bootstrap
```

`init-env.py` 会生成稳定的本地密钥与初始管理员密码。`bootstrap` 会创建管理员和剧本模板，账号已存在时保留它当前的密码。

## 启动四个进程

**终端 1，指标探针。** 从仓库根目录启动。以下做法把固定部署路径换成当前仓库的相对路径。

```sh
sed 's|/opt/storyframe-studio/metrics/host-metrics.json|metrics/host-metrics.json|' \
  scripts/host-metrics.py > .venv/local-host-metrics.py
.venv/bin/python .venv/local-host-metrics.py
```

**终端 2，Web API。** 从仓库根目录运行：

```sh
set -a
. ./.env
set +a
export CSRF_TRUSTED_ORIGINS=http://127.0.0.1:5173
cd backend
../.venv/bin/python -m uvicorn config.asgi:application --host 127.0.0.1 --port 8011
```

**终端 3，Worker。** 同样从仓库根目录运行：

```sh
set -a
. ./.env
set +a
cd backend
../.venv/bin/python manage.py worker
```

**终端 4，前端。** 从仓库根目录运行：

```sh
cd frontend
npm ci
npm run dev -- --port 5173 --strictPort
```

打开 `http://127.0.0.1:5173`，用 `admin` 和练习专用密码登录。Vite 会把 `/api` 和 `/admin` 转发到 8011。另开终端请求 `curl http://127.0.0.1:8011/health/`，确认 `status` 为 `ok` 且 `worker` 为 `true`。

验收时上传一张样例图，建一个 5 秒分镜，使用本地合成验证字幕与下载。随后进入任务详情核对状态和日志。[样例素材](samples/subtitle-frame.png) · [画布流程](canvas-flow-guide.md)

## 回归和代码入口

在仓库根目录运行：

```sh
(cd backend && ../.venv/bin/python -m pytest -q)
npm --prefix frontend test
npm --prefix frontend run build
```

后端测试通过 fixture 设置密钥和临时素材。启动测试前可打开一份未加载生产 `.env` 的终端，并确保测试工作目录所在磁盘有至少 5 GiB 可用空间。供应商协议测试使用模拟响应。

从页面执行按钮读到 Django `canvas_run`，再看 `enqueue`、`claim` 和 Worker 调用的 `compose` 或供应商适配器。数据库变更应附迁移文件，媒体和网络改动应覆盖失败、边界与归属检查。[架构](architecture.md) · [测试与验收](test-report.md)
