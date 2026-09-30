#!/usr/bin/env bash
# Check a publish request ($REPOSITORY, $TAG) before anything is downloaded.
# Shared by every job of publish-release.yaml, so the apt/RPM publisher and the
# Scoop bucket accept exactly the same callers.
set -euo pipefail
case "${REPOSITORY:-}" in
  metacraft-labs/*) ;;
  *) echo "::error::only metacraft-labs repositories publish here, got '${REPOSITORY:-}'"; exit 1 ;;
esac
grep -qxF "$REPOSITORY" publishers.txt \
  || { echo "::error::$REPOSITORY is not listed in publishers.txt"; exit 1; }
[[ "${TAG:-}" =~ ^v?[0-9][0-9A-Za-z.+~-]*$ ]] || { echo "::error::malformed tag '${TAG:-}'"; exit 1; }
