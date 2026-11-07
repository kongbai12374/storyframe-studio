#!/bin/sh
set -eu
test "$#" -eq 2 || { echo "Usage: sh scripts/restore.sh backup-directory new-isolated-target"; exit 1; }
test ! -e "$2" || { echo "Target must not exist; production is never overwritten"; exit 1; }
(cd "$1" && sha256sum -c manifest.sha256)
mkdir -m 700 "$2"
python3 - "$1/runtime.tar.gz" "$2" <<'PY'
import sys,tarfile
with tarfile.open(sys.argv[1]) as archive:archive.extractall(sys.argv[2],filter='data')
PY
python3 - "$2/runtime/db.sqlite3" <<'PY'
import sqlite3,sys
db=sqlite3.connect(sys.argv[1]);assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok';print('Restored isolated database verified')
PY
echo "Isolated restore complete. Verify media and keys before a planned production switch."
