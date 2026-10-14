#!/usr/bin/env bash
# Reset the task tree to the buggy parent of bf7c716648. No tests are staged: the agent gets a
# behaviour-level bug report only; the fix commit's tests (hidden_tests/) are copied in at grading.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
. "$HERE/../env.sh"
R="${1:-$DGX_TASK_REPO}"
"$HERE/../hide_refs.sh" "$R" 0b33ee88e4
git -C "$R" status --short
