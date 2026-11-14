#!/usr/bin/env bash
# Live view of a running Ollama simulation: one line per LLM call from Ollama's
# server log (time taken per call), plus warnings/errors from the run log.
#
# Usage: scripts/watch_ollama.sh [run-group] [seed]
#   scripts/watch_ollama.sh ollama-qwen3.5_9b__fish_baseline_concurrent 1
# Default group/seed: the most recently modified log under outputs/pilot_logs/.
# Ctrl-C to stop (the simulation keeps running).
set -uo pipefail
cd "$(dirname "$0")/.."

if [ $# -ge 1 ]; then
  RUNLOG="outputs/pilot_logs/$1/s${2:-1}.log"
else
  RUNLOG="$(ls -t outputs/pilot_logs/*/s*.log 2>/dev/null | head -1)"
fi
[ -f "${RUNLOG:-}" ] || { echo "no run log found"; exit 1; }
echo "run log: $RUNLOG"
echo "server log: ~/.ollama/logs/server.log (columns: time | status | duration | endpoint)"

# run-log problems (parse failures, retries, tracebacks) in the background
tail -n 0 -F "$RUNLOG" | grep --line-buffered -E "Exception:|Backing off|Traceback|Error" | sed 's/^/[run] /' &
PID=$!
trap 'kill $PID 2>/dev/null' EXIT

# every LLM call and any Ollama shutdown/error
tail -n 0 -F ~/.ollama/logs/server.log | grep --line-buffered -E 'api/chat|ERROR|panic|Listening on' \
  | sed -E 's/^\[GIN\] [0-9\/]+ - //; s/ \| 127\.0\.0\.1 \|//'
