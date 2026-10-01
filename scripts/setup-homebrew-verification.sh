#!/usr/bin/env bash
# Use a private prefix on hosted and shared runners, leaving their Brew alone.
# macOS Homebrew sandboxes require the prefix and build directory outside /tmp.
set -euo pipefail
: "${GITHUB_RUN_ID:?}" "${GITHUB_RUN_ATTEMPT:?}" "${GITHUB_JOB:?}" "${GITHUB_ENV:?}"
test_root="$HOME/.cache/metacraft-homebrew-verification/$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT-$GITHUB_JOB"
[ ! -e "$test_root" ] || { echo "::error::verification directory already exists: $test_root"; exit 1; }
mkdir -p "$test_root/prefix" "$test_root/tmp" "$test_root/cache"
echo "HOMEBREW_VERIFY_ROOT=$test_root" >> "$GITHUB_ENV"
git -C "$test_root/prefix" init -q
git -C "$test_root/prefix" remote add origin https://github.com/Homebrew/brew
git -C "$test_root/prefix" fetch --depth=1 origin d6ca35509427ed7b4e37445054fa343ab90755ec
git -C "$test_root/prefix" checkout --detach FETCH_HEAD
{
  echo "HOMEBREW_VERIFY_BREW=$test_root/prefix/bin/brew"
  echo "HOMEBREW_TEMP=$test_root/tmp"
  echo "HOMEBREW_CACHE=$test_root/cache"
  echo 'HOMEBREW_NO_AUTO_UPDATE=1'
  echo 'HOMEBREW_NO_ANALYTICS=1'
  echo 'HOMEBREW_NO_INSTALL_FROM_API=1'
  echo 'HOMEBREW_NO_INSTALL_CLEANUP=1'
} >> "$GITHUB_ENV"
