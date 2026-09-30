#!/usr/bin/env python3
"""Validate reprepro's indices and create apt's immutable by-hash paths.

The caller signs the augmented Release after this succeeds. Reprepro 5.4.8
does not export these paths itself. SHA256 and SHA512 cover both apt clients'
digest choices; the original index files remain for older clients.
"""
import hashlib
from pathlib import Path, PurePosixPath
import shutil
import sys


def prepare(directory):
    release = directory / "Release"
    source = release.read_text()
    algorithm = None
    count = 0
    for line in source.splitlines():
        if not line.startswith(" "):
            algorithm = line[:-1] if line in ("SHA256:", "SHA512:") else None
        elif algorithm:
            expected, size, name = line.split()
            relative = PurePosixPath(name)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"unsafe index path: {name}")
            index = directory / relative
            content = index.read_bytes()
            actual = hashlib.new(algorithm.lower(), content).hexdigest()
            if actual != expected or len(content) != int(size):
                raise ValueError(f"index does not match Release: {name}")
            target = index.parent / "by-hash" / algorithm / actual
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.read_bytes() != content:
                raise ValueError(f"conflicting immutable index: {target}")
            shutil.copyfile(index, target)
            count += 1
    if count == 0:
        raise ValueError("Release has no strong index checksums")
    lines = [line for line in source.splitlines() if not line.startswith("Acquire-By-Hash:")]
    release.write_text("Acquire-By-Hash: yes\n" + "\n".join(lines) + "\n")
    print(f"apt: validated {count} immutable index references")


if __name__ == "__main__":
    prepare(Path(sys.argv[1]))
