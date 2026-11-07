#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
if ! docker info >/dev/null 2>&1; then
 docker() { sudo -n /usr/bin/docker "$@"; }
fi
node -e "if(Number(process.versions.node.split('.')[0])<22){console.error('Node22+ required; adjust PATH before deploying');process.exit(1)}"
test -f .env || { echo "Create .env with stable keys first"; exit 1; }
mkdir -p runtime metrics
(
 set -a
 . ./.env
 set +a
 DATA_DIR="$PWD/runtime" .venv/bin/python backend/manage.py collectstatic --noinput
)
npm --prefix frontend ci
NODE_OPTIONS=--max-old-space-size=512 npm --prefix frontend run build
docker compose build web
docker compose stop worker
docker compose run --rm --no-deps web python manage.py migrate --noinput
docker compose run --rm --no-deps web python manage.py bootstrap
docker compose up -d --no-build
for i in $(seq 1 30); do
 if curl -fsS http://127.0.0.1:8011/health/; then exit 0; fi
 sleep 2
done
docker compose logs --tail 30
exit 1
