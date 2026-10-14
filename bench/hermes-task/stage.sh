#!/usr/bin/env bash
# Reset the task tree to the buggy parent of f2d03c1f2a and stage the failing tests from hidden_tests/.
# The roundtrip test's module docstring narrates the bug and the fix site (an answer key), so it is
# cut to its one-line purpose; the assertions are the spec.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
. "$HERE/../env.sh"
R="${1:-$DGX_TASK_REPO}"
"$HERE/../hide_refs.sh" "$R" 3a8d95a93bdc
for f in tests/hermes_state/test_reasoning_roundtrip.py tests/cli/test_branch_command.py tests/test_tui_gateway_server.py; do
  cp "$HERE/hidden_tests/$f" "$R/$f"
done
python3 - "$R/tests/hermes_state/test_reasoning_roundtrip.py" <<'PY'
import re, sys
p = sys.argv[1]
s = open(p).read()
s = re.sub(r'\A"""Round-trip tests for the structured reasoning columns\..*?"""', '"""Round-trip tests for the structured reasoning columns."""', s, count=1, flags=re.S)
open(p, "w").write(s)
PY
git -C "$R" status --short
