#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="$PROJECT_DIR/.local/postgres"
LOG_FILE="$PROJECT_DIR/.local/postgres.log"
if [[ -z "${PG_BIN:-}" ]]; then
  PG_BIN="$(brew --prefix postgresql@18)/bin"
fi

case "${1:-start}" in
  start)
    if [[ ! -f "$DATA_DIR/PG_VERSION" ]]; then
      echo "DB가 없습니다. 먼저 ./scripts/local-db.sh init 을 실행하세요." >&2
      exit 1
    fi
    if "$PG_BIN/pg_ctl" -D "$DATA_DIR" status >/dev/null 2>&1; then
      echo "프로젝트 DB가 이미 실행 중입니다."
      exit 0
    fi
    "$PG_BIN/pg_ctl" -D "$DATA_DIR" -l "$LOG_FILE" -w start
    ;;
  stop)
    "$PG_BIN/pg_ctl" -D "$DATA_DIR" -m fast -w stop
    ;;
  status)
    "$PG_BIN/pg_ctl" -D "$DATA_DIR" status
    ;;
  init)
    if [[ -e "$DATA_DIR" ]]; then
      echo "기존 DB 폴더가 있어 초기화하지 않습니다: $DATA_DIR" >&2
      exit 1
    fi
    if "$PG_BIN/pg_isready" -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
      echo "5432 포트의 다른 PostgreSQL을 먼저 중지하세요." >&2
      exit 1
    fi
    mkdir -p "$PROJECT_DIR/.local"
    chmod 700 "$PROJECT_DIR/.local"
    "$PG_BIN/initdb" -D "$DATA_DIR" -U "$(id -un)" --auth=trust --encoding=UTF8 --locale=en_US.UTF-8
    printf '\nlisten_addresses = '\''localhost'\''\nport = 5432\ntimezone = '\''UTC'\''\n' >> "$DATA_DIR/postgresql.conf"
    "$0" start
    "$PG_BIN/createuser" -h 127.0.0.1 --login bangjach_local
    "$PG_BIN/createdb" -h 127.0.0.1 --owner=bangjach_local bangjach
    ;;
  *)
    echo "Usage: $0 {init|start|stop|status}" >&2
    exit 2
    ;;
esac
