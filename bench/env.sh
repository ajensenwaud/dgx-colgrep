# Shared, overridable settings for the shell tooling. Source it: `. "$(dirname "$0")/../env.sh"`.
# Every value can be set in the environment (or in bench/env.local.sh, git-ignored) to run anywhere.

DGX_ROOT="${DGX_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
[ -f "$DGX_ROOT/bench/env.local.sh" ] && . "$DGX_ROOT/bench/env.local.sh"

# Hermes Agent source checkout whose venv runs the hermes-agent tests, and the Hermes data root
# (profiles live in $DGX_HERMES_ROOT/profiles/<name>).
DGX_HERMES_AGENT_DIR="${DGX_HERMES_AGENT_DIR:-$HOME/.hermes/hermes-agent}"
DGX_HERMES_PYTHON="${DGX_HERMES_PYTHON:-$DGX_HERMES_AGENT_DIR/venv/bin/python}"
DGX_HERMES_ROOT="${DGX_HERMES_ROOT:-$HOME/.hermes}"
# Directory holding pytest + pytest-asyncio (installed with `uv pip install --target`), prepended to PYTHONPATH.
DGX_PYTEST_LIB="${DGX_PYTEST_LIB:-$DGX_ROOT/.pytest-lib}"
# colgrep CLI on the client.
DGX_COLGREP_BIN="${DGX_COLGREP_BIN:-$(command -v colgrep || echo "$DGX_ROOT/bin/colgrep")}"
# hermes-agent clone used as the benchmark task tree (created by bench/setup_task_repo.sh).
DGX_TASK_REPO="${DGX_TASK_REPO:-$DGX_ROOT/bench/work/hermes-agent}"
# next-plaid clone used for the colgrep --agent speed / quant ladder.
DGX_NEXT_PLAID_REPO="${DGX_NEXT_PLAID_REPO:-$DGX_ROOT/bench/work/next-plaid}"
# Spark that serves the agent model: ssh host and the path of this repo on it (relative to its home).
DGX_SPARK_HOST="${DGX_SPARK_HOST:-spark}"
DGX_SPARK_REPO="${DGX_SPARK_REPO:-dgx-colgrep}"

export DGX_ROOT DGX_HERMES_AGENT_DIR DGX_HERMES_PYTHON DGX_HERMES_ROOT DGX_PYTEST_LIB DGX_COLGREP_BIN DGX_TASK_REPO DGX_NEXT_PLAID_REPO DGX_SPARK_HOST DGX_SPARK_REPO
