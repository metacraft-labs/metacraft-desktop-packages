#!/usr/bin/env python3
"""Compare every released file with the real package manager's installed tree.

No mocks: reads a downloaded release zip and the directory reported by Scoop.
Checks PE machine types as well as complete payload bytes, including DLLs and
data files. Package-manager bookkeeping may add files outside that payload.
"""
import argparse
import hashlib
from pathlib import Path
import struct
import zipfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--archive", type=Path, required=True)
parser.add_argument("--extract-dir", required=True)
parser.add_argument("--installed-root", type=Path, required=True)
parser.add_argument("--architecture", choices=["64bit", "arm64"], required=True)
args = parser.parse_args()
root = args.installed_root.resolve()
prefix = args.extract_dir + "/"
count = 0
executables = 0
with zipfile.ZipFile(args.archive) as archive:
    for member in archive.infolist():
        if member.is_dir():
            continue
        assert member.filename.startswith(prefix), member.filename
        path = (root / member.filename[len(prefix):]).resolve()
        assert path.is_relative_to(root), member.filename
        expected = archive.read(member)
        actual = path.read_bytes()
        assert hashlib.sha256(actual).digest() == hashlib.sha256(expected).digest(), path
        count += 1
        if path.suffix.lower() in (".exe", ".dll"):
            assert actual[:2] == b"MZ", path
            offset = struct.unpack_from("<I", actual, 0x3c)[0]
            assert actual[offset:offset + 4] == b"PE\x00\x00", path
            machine = struct.unpack_from("<H", actual, offset + 4)[0]
            assert machine == {"64bit": 0x8664, "arm64": 0xaa64}[args.architecture], (path, machine)
            executables += 1
assert count and executables, "The installed payload must include real executables"
print(f"PASS: {count} released files match; {executables} PE files are {args.architecture}")
