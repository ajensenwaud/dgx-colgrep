#!/usr/bin/env bash
# Serve colgrep-agent-2B with llama.cpp CUDA (OpenAI-compatible /v1/completions for `colgrep --agent`).
# Usage: serve_llamacpp.sh [start|stop]
# env: QUANT=Q8_0 HOST=0.0.0.0 PORT=8899 PARALLEL=4 CTX_PER_SLOT=16384 API_KEY= EXTRA="..."
set -uo pipefail
. "$(dirname "$0")/env.sh"
QUANT=${QUANT:-Q8_0}; HOST=${HOST:-0.0.0.0}; PORT=${PORT:-8899}; PARALLEL=${PARALLEL:-4}; CTX_PER_SLOT=${CTX_PER_SLOT:-16384}
BIN="$COLGREP_DIR/llama.cpp-$LLAMA_CPP_REL/build/bin/llama-server"
MODEL="$MODELS_DIR/colgrep-agent-2B/gguf/colgrep-agent-2B-$QUANT.gguf"
PIDF="$COLGREP_DIR/llama-server.pid"; LOG="$COLGREP_DIR/llama-server.log"
stop() { [ -f "$PIDF" ] && kill "$(cat "$PIDF")" 2>/dev/null; sleep 1; rm -f "$PIDF"; }
case "${1:-start}" in
  stop) stop; exit 0;;
esac
stop
mkdir -p "$COLGREP_DIR"
setsid nohup "$BIN" -m "$MODEL" --alias colgrep-agent-2B --host "$HOST" --port "$PORT" \
  --special -ngl 999 -fa on --parallel "$PARALLEL" -c $((PARALLEL*CTX_PER_SLOT)) \
  --cache-reuse 256 --no-webui --metrics ${API_KEY:+--api-key "$API_KEY"} ${EXTRA:-} > "$LOG" 2>&1 < /dev/null &
echo $! > "$PIDF"
for i in $(seq 60); do curl -sf "localhost:$PORT/health" >/dev/null && { echo "UP pid $(cat "$PIDF") quant=$QUANT port=$PORT"; exit 0; }; sleep 1; done
echo "FAILED"; tail -20 "$LOG"; exit 1
