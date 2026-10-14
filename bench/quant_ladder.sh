#!/usr/bin/env bash
# Quality/speed ladder: restart the Spark server per quant (over ssh) and run the file-level gold set.
# Usage: quant_ladder.sh "Q8_0 BF16 Q4_K_M-local ..." [label-suffix]
# Uses DGX_SPARK_HOST / DGX_SPARK_REPO / DGX_NEXT_PLAID_REPO from bench/env.sh.
set -uo pipefail
cd "$(dirname "$0")/.."
. bench/env.sh
QUANTS=${1:?quants}; SUFFIX=${2:-}
for q in $QUANTS; do
  timeout 120 ssh -n "$DGX_SPARK_HOST" "cd $DGX_SPARK_REPO && QUANT=$q EXTRA='${EXTRA:-}' spark/serve_llamacpp.sh start" </dev/null | tail -1
  python3 bench/agent_speed.py --label "gold-$q$SUFFIX" --repo "$DGX_NEXT_PLAID_REPO" \
    --questions bench/gold_nextplaid.jsonl --out results/gold.jsonl | tail -2
done
