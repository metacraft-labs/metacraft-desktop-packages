#!/usr/bin/env bash
# The caller has generated and installed the candidate from real release assets.
# Publish through protected dev and stable, with ordinary merge commits only.
set -euo pipefail
cd "$1"
export GH_REPO=metacraft-labs/homebrew-metacraft
: "${APP:?}" "${TAG:?}" "${REPOSITORY:?}" "${GITHUB_RUN_ID:?}" "${GITHUB_RUN_ATTEMPT:?}"
base=$(git rev-parse HEAD)
git add -- "Formula/$APP.rb" "releases/$APP.json"
if ! git diff --cached --quiet; then
  branch="homebrew/$APP-${TAG#v}-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"
  git -c user.name='github-actions[bot]' \
      -c user.email='41898282+github-actions[bot]@users.noreply.github.com' \
    commit -m "homebrew: $APP ${TAG#v}"
  tested=$(git rev-parse HEAD)
  git fetch origin dev stable
  [ "$(git rev-parse origin/dev)" = "$base" ] \
    || { echo '::error::tap dev changed during verification; rerun against its new head'; exit 1; }
  git push origin "HEAD:refs/heads/$branch"
  body=$(mktemp)
  cat > "$body" <<EOF
Install $REPOSITORY $TAG from its immutable GitHub release archive.

The publisher verified SHA256SUMS and native ARM64 Mach-O payloads, installed
the candidate with Homebrew, compared every payload file, checked its receipt
and command links, and ran the formula's functional test on native macOS ARM64.

Source: https://github.com/$REPOSITORY/releases/tag/$TAG
Run: $GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID
EOF
  gh pr create --base dev --head "$branch" --title "homebrew: $APP ${TAG#v}" --body-file "$body"
  rm "$body"
  merged=false
  for attempt in 1 2 3 4 5 6; do
    if gh pr merge "$branch" --merge --match-head-commit "$tested" --delete-branch; then merged=true; break; fi
    echo "merge attempt $attempt pending"
    sleep 15
  done
  [ "$merged" = true ] || { echo '::error::tap dev promotion failed'; exit 1; }
  git fetch origin dev stable
  git diff --exit-code "$tested^{tree}" 'origin/dev^{tree}'
else
  git fetch origin dev stable
  [ "$(git rev-parse origin/dev)" = "$base" ] \
    || { echo '::error::tap dev changed during verification; rerun against its new head'; exit 1; }
fi

# Also resume an interrupted dev -> stable promotion on an unchanged retry.
if git merge-base --is-ancestor origin/dev origin/stable; then
  echo 'Homebrew stable already contains the verified formulas'
  exit 0
fi
expected=$(git rev-parse origin/dev)
body=$(mktemp)
cat > "$body" <<EOF
Publish the verified formulas on the public Homebrew tap's default branch.

The formula for $APP on dev at $expected passed real Homebrew installation,
payload comparison, receipt/origin checks and its functional test in the publisher.
Run: $GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID
EOF
if [ -z "$(gh pr list --base stable --head dev --state open --json number -q '.[].number')" ]; then
  gh pr create --base stable --head dev --title "Publish Homebrew formulas: $APP ${TAG#v}" --body-file "$body"
fi
rm "$body"
merged=false
for attempt in 1 2 3 4 5 6; do
  if gh pr merge dev --merge --match-head-commit "$expected"; then merged=true; break; fi
  echo "stable merge attempt $attempt pending"
  sleep 15
done
[ "$merged" = true ] || { echo '::error::tap stable promotion failed'; exit 1; }
git fetch origin stable
git diff --exit-code "$expected^{tree}" 'origin/stable^{tree}'
echo "Published Homebrew stable at $(git rev-parse origin/stable)"
