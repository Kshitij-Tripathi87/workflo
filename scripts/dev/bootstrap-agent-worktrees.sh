#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "Run this script from inside a Workflo Git checkout." >&2
  exit 2
}
cd "$REPO_ROOT"

REMOTE="${WORKFLO_REMOTE:-origin}"
git remote get-url "$REMOTE" >/dev/null
git fetch "$REMOTE" --prune

PARENT_DIR="$(cd "$REPO_ROOT/.." && pwd)"
WORKTREE_ROOT="${WORKFLO_WORKTREE_ROOT:-$PARENT_DIR/.workflo-worktrees}"
mkdir -p "$WORKTREE_ROOT"

declare -a SPECS=(
  "agent/deepseek-native-cli-runner|deepseek-native-cli-runner"
  "agent/glm-cli-connectors-distribution|glm-cli-connectors-distribution"
  "agent/minimax-sandbox-security-qa|minimax-sandbox-security-qa"
  "agent/gemini-dashboard-frontend|gemini-dashboard-frontend"
  "agent/gpt6-luna-backend-platform|gpt6-luna-backend-platform"
)

for spec in "${SPECS[@]}"; do
  branch="${spec%%|*}"
  folder="${spec#*|}"
  target="$WORKTREE_ROOT/$folder"

  if ! git show-ref --verify --quiet "refs/remotes/$REMOTE/$branch"; then
    echo "Missing remote branch: $REMOTE/$branch" >&2
    exit 3
  fi

  if [ -e "$target" ]; then
    if git -C "$target" rev-parse --show-toplevel >/dev/null 2>&1; then
      actual_root="$(git -C "$target" rev-parse --show-toplevel)"
      actual_branch="$(git -C "$target" branch --show-current)"
      if [ "$actual_root" = "$target" ] && [ "$actual_branch" = "$branch" ]; then
        echo "Already configured: $target ($branch)"
        continue
      fi
    fi
    echo "Refusing to overwrite non-matching existing path: $target" >&2
    exit 4
  fi

  if git show-ref --verify --quiet "refs/heads/$branch"; then
    local_sha="$(git rev-parse "refs/heads/$branch")"
    remote_sha="$(git rev-parse "refs/remotes/$REMOTE/$branch")"
    if [ "$local_sha" != "$remote_sha" ]; then
      echo "Local branch $branch is not at $REMOTE/$branch." >&2
      echo "Refusing to attach a stale/diverged branch. Preserve any local commits, then fast-forward or recreate it explicitly." >&2
      exit 5
    fi
    git worktree add "$target" "$branch"
  else
    git worktree add --track -b "$branch" "$target" "$REMOTE/$branch"
  fi
  echo "Created: $target ($branch)"
done

echo
git worktree list
