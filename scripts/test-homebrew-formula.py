#!/usr/bin/env python3
"""Exercise publication refusals with real release archives and filesystem writes.

No mocks. The caller supplies an actual downloaded release. Negative controls
corrupt that archive or its checksums; a successful publication must survive
repetition and reject a changed payload under an already-published version.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--config", type=Path, required=True)
parser.add_argument("--release-dir", type=Path, required=True)
parser.add_argument("--tag", default="v0.1.0")
args = parser.parse_args()
config = json.loads(args.config.read_text())
version = args.tag.removeprefix(config.get("tag_prefix", "v"))
asset = config["asset"].replace("$version", version)
root = config["extract_dir"].replace("$version", version)
generator = Path(__file__).with_name("homebrew-formula.py")
checks = 0

with tempfile.TemporaryDirectory(prefix="homebrew-release-controls-") as directory:
    work = Path(directory)
    release, tap = work / "release", work / "tap"
    release.mkdir()
    archive = release / asset
    pristine = (args.release_dir / asset).read_bytes()
    sums = (args.release_dir / "SHA256SUMS").read_text()

    def reset():
        archive.write_bytes(pristine)
        (release / "SHA256SUMS").write_text(sums)

    def digest_archive():
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        (release / "SHA256SUMS").write_text(f"{digest}  {asset}\n")

    def run(expected, tag=args.tag, destination=tap):
        global checks
        command = [sys.executable, str(generator), "--config", str(args.config.resolve()),
                   "--tag", tag, "--release-dir", str(release), "--tap", str(destination)]
        result = subprocess.run(command, text=True, capture_output=True, timeout=60)
        assert (result.returncode == 0) == (expected != "refused"), result
        assert "homebrew-formula: " + expected in result.stdout + result.stderr, result
        checks += 1

    reset()
    run("updated")
    before = {str(p.relative_to(tap)): p.read_bytes() for p in tap.rglob("*") if p.is_file()}
    run("unchanged")
    run("skipped", "v0.0.0")
    run("refused", args.tag + "-rc1")
    archive.write_bytes(pristine + b"corruption")
    run("refused")
    digest_archive()
    run("refused")
    reset()
    (release / "SHA256SUMS").unlink()
    run("refused")
    reset()
    with (release / "SHA256SUMS").open("a") as stream:
        stream.write(f"{'0' * 64}  {asset}\n")
    run("refused")
    reset()

    # Keep a valid gzip/tar and matching checksum, but change the actual CPU.
    with tarfile.open(fileobj=io.BytesIO(pristine), mode="r:gz") as source:
        with tarfile.open(archive, "w:gz") as target:
            for member in source:
                data = source.extractfile(member).read() if member.isfile() else None
                if member.name == root + "/" + config["native_files"][0]:
                    data = data[:4] + bytes.fromhex("07000001") + data[8:]
                target.addfile(member, io.BytesIO(data) if data is not None else None)
    digest_archive()
    run("refused", destination=work / "wrong-architecture")
    reset()
    run("unchanged")
    after = {str(p.relative_to(tap)): p.read_bytes() for p in tap.rglob("*") if p.is_file()}
    assert after == before, "a refusal or no-op changed the published tap"
    checks += 1
print(f"PASS: {config['app']} {checks} real release publication checks")
