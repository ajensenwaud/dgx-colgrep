#!/usr/bin/env bash
# Grade task 2 with the fix commit's hidden tests (hidden_tests/, copied in only now, pristine).
#   target: the 3 tests bf7c716648 added; behavioural subset = the 2 that don't patch a helper name
#   regression: any other failure in those two files not in known_env_failures.txt (isolated retry = flaky)
# Last line: "PASS target=3/3 behavioural=2/2 regressions=0" or "FAIL ...".
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
. "$HERE/../env.sh"
R="${1:-$DGX_TASK_REPO}"
FILES=(tests/agent/test_credential_pool.py tests/run_agent/test_env_credential_turn_refresh.py)
BEHAV=(tests/agent/test_credential_pool.py::test_stale_credential_id_prefers_api_key_hint
       tests/run_agent/test_env_credential_turn_refresh.py::TestLeavesNonEnvStateAlone::test_first_look_does_not_stomp_rotated_pool_key)
IMPL=(tests/run_agent/test_env_credential_turn_refresh.py::TestLeavesNonEnvStateAlone::test_adopted_key_rebinds_pool_entry_id)
for f in "${FILES[@]}"; do cp "$HERE/hidden_tests/$f" "$R/$f"; done
pyt() {
  local tmph; tmph=$(mktemp -d)
  env -C "$R" PYTHONPATH="$R:$DGX_PYTEST_LIB" HERMES_HOME="$tmph" timeout 900 \
    "$DGX_HERMES_PYTHON" -m pytest -q -p no:cacheprovider -o addopts="" -rfE "$@" 2>&1
  rm -rf "$tmph"
}
fails() { grep -E '^(FAILED|ERROR) ' | sed 's/ - .*//; s/^ERROR /FAILED /' | sort -u; }
npass() { tail -1 | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+' || echo 0; }
b=$(pyt "${BEHAV[@]}" | npass); i=$(pyt "${IMPL[@]}" | npass)
pyt "${FILES[@]}" | fails > "$HERE/.last_failures.txt"
regress=$(grep -vxF -f "$HERE/known_env_failures.txt" "$HERE/.last_failures.txt" \
          | grep -vE 'prefers_api_key_hint|does_not_stomp_rotated_pool_key|rebinds_pool_entry_id' \
          | tee "$HERE/.last_regressions.txt" | grep -c . || true)
if [ "$regress" -gt 0 ]; then
  mapfile -t again < <(sed 's/^FAILED //' "$HERE/.last_regressions.txt")
  pyt "${again[@]}" | fails > "$HERE/.last_regressions_retry.txt"
  flaky=$(grep -vxF -f "$HERE/.last_regressions_retry.txt" "$HERE/.last_regressions.txt" || true)
  [ -n "$flaky" ] && echo "$flaky" | sed 's/^FAILED /FLAKY (passed on retry) /' | tee -a "$HERE/flaky.log"
  regress=$(grep -c . "$HERE/.last_regressions_retry.txt" || true)
fi
# Remove the hidden tests again so the shared tree is not left with them.
git -C "$R" checkout -q -- "${FILES[@]}"
t=$((b + i))
v=FAIL; [ "$t" -eq 3 ] && [ "$regress" -eq 0 ] && v=PASS
echo "$v target=$t/3 behavioural=$b/2 regressions=$regress"
