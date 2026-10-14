#!/usr/bin/env bash
# Detach HEAD at a commit and delete every ref so the agent can't browse future history.
# Usage: hide_refs.sh <repo> <commit>
set -euo pipefail
R="$1"; C="$2"
git -C "$R" checkout -q -- . 2>/dev/null || true
git -C "$R" clean -qfd
git -C "$R" checkout -q --detach "$C"
git -C "$R" for-each-ref --format='delete %(refname)' | git -C "$R" update-ref --no-deref --stdin
git -C "$R" reflog expire --expire=now --all
