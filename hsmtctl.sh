#!/usr/bin/env bash
set -u

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$PROJECT/.env"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

PYTHON="${HSMT_PYTHON:-python}"
HOST="${HSMT_WEB_HOST:-0.0.0.0}"
PORT="${HSMT_WEB_PORT:-8004}"
RUNTIME="$PROJECT/runtime"
LOG_DIR="$RUNTIME/logs"
PID_FILE="$RUNTIME/hsmt-ai.pid"
LOG_FILE="$LOG_DIR/hsmt-ai.log"

mkdir -p "$RUNTIME/jobs" "$LOG_DIR"

get_pid() {
  [[ -f "$PID_FILE" ]] || return 1
  local pid
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  [[ -n "$pid" ]] || return 1
  if kill -0 "$pid" 2>/dev/null; then
    printf '%s' "$pid"
    return 0
  fi
  rm -f "$PID_FILE"
  return 1
}

start_app() {
  local pid
  if pid="$(get_pid)"; then
    echo "App đang chạy. PID=$pid, URL=http://$HOST:$PORT"
    return 0
  fi
  cd "$PROJECT"
  : > "$LOG_FILE"
  nohup "$PYTHON" -m uvicorn app:app \
    --host "$HOST" --port "$PORT" --workers 1 \
    >> "$LOG_FILE" 2>&1 &
  pid=$!
  echo "$pid" > "$PID_FILE"
  sleep 3
  if kill -0 "$pid" 2>/dev/null; then
    echo "Đã chạy app. PID=$pid, port=$PORT"
    echo "Log: $LOG_FILE"
  else
    echo "Khởi động thất bại:"
    rm -f "$PID_FILE"
    tail -n 100 "$LOG_FILE"
    return 1
  fi
}

stop_app() {
  local pid
  if ! pid="$(get_pid)"; then
    echo "App không chạy."
    return 0
  fi
  kill "$pid" 2>/dev/null || true
  for _ in $(seq 1 20); do
    if ! kill -0 "$pid" 2>/dev/null; then
      rm -f "$PID_FILE"
      echo "Đã dừng app."
      return 0
    fi
    sleep 1
  done
  kill -9 "$pid" 2>/dev/null || true
  rm -f "$PID_FILE"
  echo "Đã dừng cưỡng bức app."
}

status_app() {
  local pid
  if pid="$(get_pid)"; then
    echo "ĐANG CHẠY - PID=$pid - port=$PORT"
    ps -fp "$pid" || true
    ss -lnt 2>/dev/null | grep ":$PORT" || true
  else
    echo "ĐÃ DỪNG"
    return 1
  fi
}

case "${1:-}" in
  start) start_app ;;
  stop) stop_app ;;
  restart) stop_app; sleep 1; start_app ;;
  status) status_app ;;
  logs) touch "$LOG_FILE"; tail -n 200 -f "$LOG_FILE" ;;
  log) touch "$LOG_FILE"; tail -n 200 "$LOG_FILE" ;;
  *) echo "Dùng: $0 {start|stop|restart|status|logs|log}"; exit 1 ;;
esac
