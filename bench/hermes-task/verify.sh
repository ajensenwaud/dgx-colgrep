#!/usr/bin/env bash
# Grade the reasoning-roundtrip task against pristine copies of the fix commit's tests (hidden_tests/).
#   target     : the 9 tests the fix commit added must pass
#   regression : any other failure in the three test files that does not also occur with the
#                upstream fix applied in this environment (known_env_failures.txt); a failure that
#                passes on an isolated re-run is logged to flaky.log and not counted
# Last line: "PASS target=9/9 regressions=0" or "FAIL target=k/9 regressions=n".
# Usage: verify.sh [repo_dir]
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
. "$HERE/../env.sh"
R="${1:-$DGX_TASK_REPO}"
FILES=(tests/hermes_state/test_reasoning_roundtrip.py tests/cli/test_branch_command.py tests/test_tui_gateway_server.py)
TARGET=(tests/hermes_state/test_reasoning_roundtrip.py
        tests/cli/test_branch_command.py::TestBranchPreservesReasoningFields
        tests/test_tui_gateway_server.py::test_persist_branch_seed_keeps_reasoning_fields
        tests/test_tui_gateway_server.py::test_session_branch_keeps_reasoning_fields)
for f in "${FILES[@]}"; do cp "$HERE/hidden_tests/$f" "$R/$f"; done
pyt() {
  local tmph; tmph=$(mktemp -d)
  env -C "$R" PYTHONPATH="$R:$DGX_PYTEST_LIB" HERMES_HOME="$tmph" timeout 900 \
    "$DGX_HERMES_PYTHON" -m pytest -q -p no:cacheprovider -o addopts="" -rfE "$@" 2>&1
  rm -rf "$tmph"
}
fails() { grep -E '^(FAILED|ERROR) ' | sed 's/ - .*//; s/^ERROR /FAILED /' | sort -u; }
t_out=$(pyt "${TARGET[@]}")
t_pass=$(echo "$t_out" | tail -1 | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+' || true)
t_pass=${t_pass:-0}
echo "$t_out" | fails
pyt "${FILES[@]}" | fails > "$HERE/.last_failures.txt"
regress=$(grep -vxF -f "$HERE/known_env_failures.txt" "$HERE/.last_failures.txt" \
          | grep -vE 'test_reasoning_roundtrip\.py|TestBranchPreservesReasoningFields|_keeps_reasoning_fields' \
          | tee "$HERE/.last_regressions.txt" | grep -c . || true)
if [ "$regress" -gt 0 ]; then
  mapfile -t again < <(sed 's/^FAILED //' "$HERE/.last_regressions.txt")
  pyt "${again[@]}" | fails > "$HERE/.last_regressions_retry.txt"
  flaky=$(grep -vxF -f "$HERE/.last_regressions_retry.txt" "$HERE/.last_regressions.txt" || true)
  [ -n "$flaky" ] && echo "$flaky" | sed 's/^FAILED /FLAKY (passed on retry) /' | tee -a "$HERE/flaky.log"
  regress=$(grep -c . "$HERE/.last_regressions_retry.txt" || true)
fi
echo "full-file failures: $(grep -c . "$HERE/.last_failures.txt" || true)"
if [ "$t_pass" -eq 9 ] && [ "$regress" -eq 0 ]; then
  echo "PASS target=$t_pass/9 regressions=$regress"
else
  echo "FAIL target=$t_pass/9 regressions=$regress"
fi
