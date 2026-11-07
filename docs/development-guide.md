# 开发指南

Python3.12，Node22；SQLite、FFmpeg、Noto CJK字体。后端依赖锁定requirements.lock，前端使用package-lock.json并npm ci。开发工具Black和Prettier作为格式化工具，TypeScript严格模式构建校验。

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock
.venv/bin/python scripts/init-env.py
set -a; . ./.env; set +a
mkdir -p runtime metrics
python3 scripts/host-metrics.py
```
探针在单独终端运行，现有脚本默认适配服务器固定路径，换目录时需修改target。另一个终端加载.env：
```sh
export CSRF_TRUSTED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
cd backend
../.venv/bin/python manage.py migrate
../.venv/bin/python manage.py bootstrap
../.venv/bin/uvicorn config.asgi:application --host 127.0.0.1 --port 8011
```
第三个终端同样加载.env并运行`cd backend && ../.venv/bin/python manage.py worker`。第四个终端`cd frontend && npm ci && npm run dev`。浏览器localhost:5173，开发代理到8011。
bootstrap仅在账号不存在时使用ADMIN_PASSWORD创建管理员，重复运行不会重置密码。新增创作者通过Django Admin，Profile在首次访问时创建。

测试：在backend运行../.venv/bin/pytest -q，在frontend运行npm test；生产构建npm run build。测试使用隔离数据库和临时素材，AI适配器使用合成fixture，不消耗真实供应商额度。
核心代码：validation负责分镜和图验证；queue负责准入/认领；video负责媒体子进程与取消；gateway固定TLS地址和额度/审计；worker串行执行任务。不要在Web进程启动后台线程执行任务。
提交使用feat/fix/test/docs前缀。数据库变更附迁移和恢复说明；所有网络/媒体路径包含超时、边界和归属测试。
