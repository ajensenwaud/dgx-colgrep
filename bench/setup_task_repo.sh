#!/usr/bin/env bash
# Create the hermes-agent task tree used by the coding A/B and the question benchmark, then index it.
#   DGX_TASK_REPO (default bench/work/hermes-agent), HERMES_AGENT_GIT (default upstream URL).
# Future commits (including the upstream fixes the tasks are graded against) must not be visible to
# the agent under test: stage.sh detaches HEAD at the task's parent commit and deletes every ref, so
# `git log --all` shows only the task commit's own history. gc is disabled so other task commits stay
# checkout-able. (Unreachable objects remain in the pack; `git fsck --unreachable` could still find them.)
set -euo pipefail
. "$(dirname "$0")/env.sh"
SRC="${HERMES_AGENT_GIT:-https://github.com/NousResearch/hermes-agent.git}"
if [ ! -d "$DGX_TASK_REPO/.git" ]; then
  mkdir -p "$(dirname "$DGX_TASK_REPO")"
  git clone --no-checkout "$SRC" "$DGX_TASK_REPO"
fi
git -C "$DGX_TASK_REPO" config gc.auto 0
for c in 3a8d95a93bdc 0b33ee88e4; do git -C "$DGX_TASK_REPO" cat-file -e "$c^{commit}"; done
"$(dirname "$0")/hermes-task2/stage.sh" "$DGX_TASK_REPO"
echo "indexing $DGX_TASK_REPO with colgrep (CPU: about 1-1.5 h for ~8k files; one-off)"
( cd "$DGX_TASK_REPO" && "$DGX_COLGREP_BIN" init -y )
