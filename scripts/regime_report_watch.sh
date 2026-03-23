#!/bin/zsh

set -euo pipefail

SCRIPT_SOURCE="${(%):-%N}"
SCRIPT_PATH="$(cd "$(dirname "$SCRIPT_SOURCE")" && pwd)/$(basename "$SCRIPT_SOURCE")"
ROOT_DIR="$(cd "$(dirname "$SCRIPT_PATH")/.." && pwd)"
RUNTIME_DIR="$ROOT_DIR/artifacts/runtime"
PID_FILE="$RUNTIME_DIR/regime_report_watch.pid"
STATE_FILE="$RUNTIME_DIR/regime_report_watch.state"
LOG_FILE="$RUNTIME_DIR/regime_report_watch.log"
POLL_SECONDS="${POLL_INTERVAL_SECONDS:-300}"

mkdir -p "$RUNTIME_DIR"

latest_report() {
  ls -1t "$ROOT_DIR"/artifacts/reports/alpha_combo_regime_switch_*.json 2>/dev/null | head -n 1 || true
}

is_running() {
  if [[ ! -f "$PID_FILE" ]]; then
    return 1
  fi
  local pid
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -z "$pid" ]]; then
    return 1
  fi
  kill -0 "$pid" 2>/dev/null
}

format_summary() {
  local report_path="$1"
  python3 - "$report_path" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text())
summary = ((data.get("mixture_research") or {}).get("oos_validation_summary") or {})
if not summary:
    print("summary=unavailable")
    raise SystemExit(0)

def pct(name: str) -> str:
    value = summary.get(name)
    if value is None:
        return "n/a"
    return f"{float(value):.2%}"

def num(name: str) -> str:
    value = summary.get(name)
    if value is None:
        return "n/a"
    return f"{float(value):.3f}"

print(
    "pass_rate="
    + pct("target_pass_rate")
    + " avg_cagr="
    + pct("avg_cagr")
    + " avg_max_dd="
    + pct("avg_max_dd")
    + " avg_sharpe="
    + num("avg_sharpe")
)
PY
}

notify_new_report() {
  local report_path="$1"
  local summary="$2"
  if ! command -v osascript >/dev/null 2>&1; then
    return 0
  fi
  local title="Quant regime report"
  local subtitle
  subtitle="$(basename "$report_path")"
  local body="${summary//\"/\'}"
  body="${body//$'\n'/ }"
  osascript -e "display notification \"$body\" with title \"$title\" subtitle \"$subtitle\"" >/dev/null 2>&1 || true
}

check_once() {
  local current_report previous_report summary
  current_report="$(latest_report)"
  previous_report="$(cat "$STATE_FILE" 2>/dev/null || true)"

  if [[ -n "$current_report" && ! -f "$STATE_FILE" ]]; then
    print -r -- "$current_report" > "$STATE_FILE"
    print -r -- "$(date '+%Y-%m-%d %H:%M:%S %Z') baseline:$current_report" >> "$LOG_FILE"
    return 0
  fi

  if [[ -n "$current_report" && "$current_report" != "$previous_report" ]]; then
    summary="$(format_summary "$current_report")"
    print -r -- "$current_report" > "$STATE_FILE"
    print -r -- "$(date '+%Y-%m-%d %H:%M:%S %Z') new_report:$current_report $summary" >> "$LOG_FILE"
    notify_new_report "$current_report" "$summary"
  fi
}

run_loop() {
  trap 'rm -f "$PID_FILE"; exit 0' INT TERM EXIT
  echo "$$" > "$PID_FILE"

  while true; do
    check_once
    sleep "$POLL_SECONDS"
  done
}

start_watch() {
  if is_running; then
    echo "already_running pid=$(cat "$PID_FILE")"
    exit 0
  fi

  nohup zsh "$SCRIPT_PATH" run </dev/null >> "$LOG_FILE" 2>&1 &!
  local pid=$!
  echo "$pid" > "$PID_FILE"
  echo "$(date '+%Y-%m-%d %H:%M:%S %Z') started pid=$pid interval=${POLL_SECONDS}s" >> "$LOG_FILE"
  echo "started pid=$pid"
}

stop_watch() {
  if ! is_running; then
    rm -f "$PID_FILE"
    echo "not_running"
    exit 0
  fi
  local pid
  pid="$(cat "$PID_FILE")"
  kill "$pid" >/dev/null 2>&1 || true
  rm -f "$PID_FILE"
  echo "$(date '+%Y-%m-%d %H:%M:%S %Z') stopped pid=$pid" >> "$LOG_FILE"
  echo "stopped pid=$pid"
}

status_watch() {
  local pid="none"
  local latest="none"
  local tracked="none"
  if [[ -f "$PID_FILE" ]]; then
    pid="$(cat "$PID_FILE" 2>/dev/null || echo none)"
  fi
  latest="$(latest_report)"
  tracked="$(cat "$STATE_FILE" 2>/dev/null || echo none)"
  if is_running; then
    echo "status=running pid=$pid latest=${latest:-none} tracked=${tracked:-none} log=$LOG_FILE"
  else
    echo "status=stopped latest=${latest:-none} tracked=${tracked:-none} log=$LOG_FILE"
  fi
}

case "${1:-start}" in
  start)
    start_watch
    ;;
  stop)
    stop_watch
    ;;
  status)
    status_watch
    ;;
  run)
    run_loop
    ;;
  check-once)
    check_once
    ;;
  *)
    echo "usage: $0 {start|stop|status|run|check-once}"
    exit 1
    ;;
esac
