#!/usr/bin/env bash
set -euo pipefail

: "${GH_TOKEN:?GH_TOKEN is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"

BASE_BRANCH="${PROTECTED_BASE_BRANCH:-main}"
BRANCH_PREFIX="${PROTECTED_BRANCH_PREFIX:-automation/protected-main}"
COMMIT_MESSAGE="${PROTECTED_COMMIT_MESSAGE:-Automated protected-main update}"
PR_TITLE="${PROTECTED_PR_TITLE:-$COMMIT_MESSAGE}"
PR_BODY="${PROTECTED_PR_BODY:-Automated update routed through a pull request so protected main never receives a direct push.}"

if (($# == 0)); then
  echo "::error::protected_main_pr.sh requires at least one path to commit."
  exit 2
fi

if git diff --quiet -- "$@"; then
  echo "No protected-main changes to submit."
  exit 0
fi

git config user.name github-actions[bot]
git config user.email 41898282+github-actions[bot]@users.noreply.github.com
git add -- "$@"
git commit -m "$COMMIT_MESSAGE"
commit_sha="$(git rev-parse HEAD)"
branch="${BRANCH_PREFIX}/${GITHUB_RUN_ID:-manual}-${GITHUB_RUN_ATTEMPT:-1}"

git push origin "HEAD:refs/heads/${branch}"

if ! pr_url="$(gh pr create \
  --repo "$GITHUB_REPOSITORY" \
  --base "$BASE_BRANCH" \
  --head "$branch" \
  --title "$PR_TITLE" \
  --body "$PR_BODY")"; then
  echo "::error::Unable to create the protected-main pull request. In Settings > Actions > General, enable 'Allow GitHub Actions to create and approve pull requests', then rerun this workflow."
  exit 1
fi

echo "Created protected-main PR: $pr_url"

if ! gh pr merge "$pr_url" --repo "$GITHUB_REPOSITORY" --merge --delete-branch; then
  echo "::error::Protected-main PR could not be merged. Leave the PR open for inspection; do not fall back to a direct push."
  exit 1
fi

git fetch origin "$BASE_BRANCH"
if ! git merge-base --is-ancestor "$commit_sha" "origin/$BASE_BRANCH"; then
  echo "::error::Protected-main PR reported merged but the committed update is not reachable from origin/$BASE_BRANCH."
  exit 1
fi

echo "Protected-main update merged through PR: $pr_url"
