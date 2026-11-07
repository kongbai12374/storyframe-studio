#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
test "$#" -eq 1 || { echo "Usage: sh scripts/backup.sh /absolute/new-backup-directory"; exit 1; }
test ! -e "$1" || { echo "Backup directory already exists"; exit 1; }
mkdir -m 700 "$1"
docker compose stop web worker
trap 'docker compose up -d --no-build' EXIT
tar -czf "$1/runtime.tar.gz" runtime
(cd "$1" && sha256sum runtime.tar.gz > manifest.sha256)
echo "Consistent stopped-service backup complete. Back up .env separately in a secure location."
