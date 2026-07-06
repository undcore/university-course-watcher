#!/usr/bin/env bash
#
# Durable watcher state via a dedicated orphan branch instead of a run_id-keyed
# GitHub Actions cache. Actions caches are immutable per key and evicted after
# ~7 days of no access, so long-lived "seen notice" state drifts. A branch is
# persisted indefinitely.
#
# Usage:
#   scripts/state_branch.sh restore <file> [<file> ...]   # read-only, safe in parallel jobs
#   scripts/state_branch.sh save    <file> [<file> ...]   # single-writer; replaces the branch
#
# The save path builds one orphan commit and force-pushes it, so the branch
# never accumulates history. Run save from a single serialized job (e.g. one
# guarded by a workflow concurrency group) to avoid concurrent writers.

set -euo pipefail

STATE_BRANCH="${STATE_BRANCH:-watcher-state}"
REMOTE="${STATE_REMOTE:-origin}"
GIT_AUTHOR_NAME_DEFAULT="github-actions[bot]"
GIT_AUTHOR_EMAIL_DEFAULT="41898282+github-actions[bot]@users.noreply.github.com"

action="${1:-}"
shift || true
files=("$@")

if [[ "$action" != "restore" && "$action" != "save" ]]; then
  echo "usage: state_branch.sh <restore|save> <file> [<file> ...]" >&2
  exit 2
fi

if [[ ${#files[@]} -eq 0 ]]; then
  echo "No state files specified; nothing to do."
  exit 0
fi

if git fetch --depth=1 "$REMOTE" "$STATE_BRANCH" 2>/dev/null; then
  has_branch=1
else
  has_branch=0
fi

if [[ "$action" == "restore" ]]; then
  if [[ "$has_branch" -eq 0 ]]; then
    echo "No $STATE_BRANCH branch yet; starting from empty state."
    exit 0
  fi
  for f in "${files[@]}"; do
    if git cat-file -e "FETCH_HEAD:$f" 2>/dev/null; then
      mkdir -p "$(dirname "$f")"
      git show "FETCH_HEAD:$f" >"$f"
      echo "Restored $f"
    else
      echo "No saved state for $f (skipped)."
    fi
  done
  exit 0
fi

# save
present=()
for f in "${files[@]}"; do
  if [[ -f "$f" ]]; then
    present+=("$f")
  else
    echo "State file missing, not saving: $f"
  fi
done

if [[ ${#present[@]} -eq 0 ]]; then
  echo "No state files present to save."
  exit 0
fi

repo_root="$(git rev-parse --show-toplevel)"
tmp="$(mktemp -d)"
cleanup() { git worktree remove --force "$tmp" >/dev/null 2>&1 || true; rm -rf "$tmp"; }
trap cleanup EXIT

git worktree add --detach --quiet "$tmp"
(
  cd "$tmp"
  git checkout --orphan "state-tmp-$$" --quiet
  git rm -rf --quiet . >/dev/null 2>&1 || true
)

for f in "${present[@]}"; do
  src="$repo_root/$f"
  mkdir -p "$tmp/$(dirname "$f")"
  cp "$src" "$tmp/$f"
done

pushed=0
(
  cd "$tmp"
  git add -A -f
  git \
    -c user.name="${GIT_AUTHOR_NAME:-$GIT_AUTHOR_NAME_DEFAULT}" \
    -c user.email="${GIT_AUTHOR_EMAIL:-$GIT_AUTHOR_EMAIL_DEFAULT}" \
    commit -m "Update watcher state [skip ci]" --quiet
  for attempt in 1 2 3 4; do
    if git push -f "$REMOTE" "HEAD:$STATE_BRANCH"; then
      exit 0
    fi
    echo "State push attempt ${attempt} failed; retrying." >&2
    sleep "$((attempt * 2))"
  done
  exit 1
) && pushed=1 || pushed=0

if [[ "$pushed" -ne 1 ]]; then
  echo "Failed to save watcher state to $STATE_BRANCH after retries." >&2
  exit 1
fi

echo "Saved ${#present[@]} state file(s) to $STATE_BRANCH."
