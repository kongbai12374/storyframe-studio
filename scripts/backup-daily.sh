#!/bin/bash
# 每日一致备份：停服快照 + 校验 + 保留策略 + 关键配置副本
# 由 drama-backup.timer 以 root 身份调用
set -euo pipefail
umask 077

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
if ! ACTIVE=$(docker compose exec -T web python manage.py shell -c \
  "from core.models import Job; print(Job.objects.exclude(status__in=['succeeded','failed','cancelled','interrupted']).count())" | tail -1); then
    log "活动任务查询失败，本次备份已中止"
    exit 1
fi
if [[ ! $ACTIVE =~ ^[0-9]+$ ]]; then
    log "活动任务数无效，本次备份已中止"
    exit 1
fi
if [[ $ACTIVE != 0 ]]; then
    log "存在 ${ACTIVE} 个活动任务，跳过本次备份"
    exit 0
fi

if [ -e "$TARGET" ]; then
    log "$TARGET 已存在，退出"
    exit 0
fi

# 完成归档与校验后再发布，失败时留下隐藏暂存目录供排查。
STAGING=$(mktemp -d "$DEST/.pending-$TS-XXXXXX")
SNAPSHOT="$STAGING/snapshot"
sh scripts/backup.sh "$SNAPSHOT"
install -m 600 "$APP/.env" "$SNAPSHOT/env.backup"
for site in drama-public drama-http; do
    install -m 600 "/etc/nginx/sites-available/$site" "$SNAPSHOT/$site"
done
(
    cd "$SNAPSHOT"
    sha256sum env.backup drama-public drama-http >> manifest.sha256
    sha256sum -c manifest.sha256
    tar -tzf runtime.tar.gz >/dev/null
)
chown -R admin:admin "$SNAPSHOT"
mv -T "$SNAPSHOT" "$TARGET"
rmdir "$STAGING"

# 仅轮换按日期命名的备份目录。
mapfile -t snapshots < <(find "$DEST" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | grep -Ex '[0-9]{8}-[0-9]{4}' | sort)
for ((i=0; i<${#snapshots[@]}-KEEP; i++)); do
    rm -rf -- "$DEST/${snapshots[i]}"
done

SIZE=$(du -sh "$TARGET" | cut -f1)
COUNT=$(ls -1d "$DEST"/2* 2>/dev/null | wc -l)
log "备份完成：$TARGET（$SIZE），当前保留 $COUNT 份"
