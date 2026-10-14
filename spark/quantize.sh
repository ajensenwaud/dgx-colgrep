#!/usr/bin/env bash
# Make the comparison quants from the BF16 GGUF (no imatrix), as used in the quant ladder.
set -euo pipefail
. "$(dirname "$0")/env.sh"
Q="$COLGREP_DIR/llama.cpp-$LLAMA_CPP_REL/build/bin/llama-quantize"
D="$MODELS_DIR/colgrep-agent-2B/gguf"
for t in ${QUANTS:-Q6_K Q5_K_M Q4_K_M IQ4_XS Q4_0}; do
  [ -s "$D/colgrep-agent-2B-$t-local.gguf" ] || "$Q" "$D/colgrep-agent-2B-BF16.gguf" "$D/colgrep-agent-2B-$t-local.gguf" "$t" > /dev/null
  echo "made $t"
done
