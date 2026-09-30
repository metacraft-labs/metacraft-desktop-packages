#!/usr/bin/env python3
"""Validate the supported queue setting before linting with older actionlint."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
publisher = root / ".github/workflows/publish-release.yaml"
source = publisher.read_text()
# GitHub added this on 2026-05-07; actionlint 1.7.12 predates it.
# https://github.blog/changelog/2026-05-07-github-actions-concurrency-groups-now-allow-larger-queues/
expected = "concurrency:\n  group: org-package-repositories\n  cancel-in-progress: false\n  queue: max\n"
assert source.count(expected) == 1, "publisher must retain the shared serial queue"
assert source.count("queue:") == 1, "unexpected additional queue setting"
with tempfile.TemporaryDirectory(prefix="publisher-lint-") as temporary:
    normalized = Path(temporary) / publisher.name
    normalized.write_text(source.replace("  queue: max\n", "", 1))
    subprocess.run(["actionlint", str(normalized),
                    str(root / ".github/workflows/test-package-publisher.yaml")], check=True)
