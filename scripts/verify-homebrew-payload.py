#!/usr/bin/env python3
"""Compare a real Homebrew install with every file in its verified release.

No mocks: metadata comes from the checked release archive, and the installed
directory is the real formula's versioned prefix. Receipt and origin checks
are performed by the caller through Homebrew's JSON interface.
"""
import argparse
import hashlib
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--metadata", type=Path, required=True)
parser.add_argument("--installed", type=Path, required=True)
args = parser.parse_args()
metadata = json.loads(args.metadata.read_text())
expected = metadata["payload"]
libexec = args.installed / "libexec"
# Homebrew's install_metafiles moves these root-level release documents from
# libexec to the formula prefix. Their bytes remain part of the verification.
documents = {name for name in expected if name in {"LICENSE", "NOTICE"}}
actual = {str(p.relative_to(libexec)) for p in libexec.rglob("*")
          if not p.is_dir() or p.is_symlink()}
expected_libexec = set(expected) - documents
assert actual == expected_libexec, {"missing": sorted(expected_libexec - actual),
                                   "extra": sorted(actual - expected_libexec)}
for name, entry in expected.items():
    path = (args.installed if name in documents else libexec) / name
    if "symlink" in entry:
        assert path.is_symlink() and str(path.readlink()) == entry["symlink"], name
    else:
        assert path.is_file() and not path.is_symlink(), name
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        assert digest == entry["sha256"], f"installed bytes changed: {name}"
print(f"PASS: {metadata['repository']} {metadata['version']}: {len(expected)} exact payload files")
