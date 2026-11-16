#!/bin/bash
# 每日一致备份：停服快照 + 校验 + 保留策略 + 关键配置副本
# 由 drama-backup.timer 以 root 身份调用
set -uo pipefail

APP=/home/admin/drama-platform
DEST=/home/admin/backups
KEEP=7
TS=$(date +%Y%m%d-%H%M)
TARGET="$DEST/$TS"

log() { echo "[$(date '+%F %T')] $*"; }

mkdir -p "$DEST"
chmod 700 "$DEST"
cd "$APP" || exit 1

# 有活动任务时跳过，避免把生成中的任务打断
ACTIVE=$(docker compose exec -T web python manage.py shell -c \
  "from core.models import Job; print(Job.objects.exclude(status__in=['succeeded','failed','cancelled','interrupted']).count())" \
  2>/dev/null | tail -1)
if [ "${ACTIVE:-0}" != "0" ]; then
    log "存在 ${ACTIVE} 个活动任务，跳过本次备份"
    exit 0
fi

if [ -e "$TARGET" ]; then
    log "$TARGET 已存在，退出"
    exit 0
fi

sh scripts/backup.sh "$TARGET" || { log "备份失败"; exit 1; }

# 校验
if ! ( cd "$TARGET" && sha256sum -c manifest.sha256 ); then
    log "校验失败：$TARGET"
    exit 1
fi
if ! tar -tzf "$TARGET/runtime.tar.gz" > /dev/null 2>&1; then
    log "压缩包不可读：$TARGET"
    exit 1
fi

# 恢复时需要：加密密钥在 .env 里，nginx 站点配置也一样要留
cp -a "$APP/.env" "$TARGET/env.backup" 2>/dev/null && chmod 600 "$TARGET/env.backup"
cp -a /etc/nginx/sites-available/drama-public "$TARGET/" 2>/dev/null
cp -a /etc/nginx/sites-available/drama-http "$TARGET/" 2>/dev/null
chmod 600 "$TARGET"/*.conf 2>/dev/null

# 归属给 admin，便于用普通账号拉取离线副本（目录仍 700，其他用户不可读）
chown -R admin:admin "$TARGET"
chmod 700 "$TARGET"

# 保留最近 KEEP 份
ls -1d "$DEST"/2* 2>/dev/null | sort | head -n -"$KEEP" | xargs -r rm -rf

SIZE=$(du -sh "$TARGET" | cut -f1)
COUNT=$(ls -1d "$DEST"/2* 2>/dev/null | wc -l)
log "备份完成：$TARGET（$SIZE），当前保留 $COUNT 份"
