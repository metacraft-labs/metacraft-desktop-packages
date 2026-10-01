#!/usr/bin/env python3
"""Exercise scoop-manifest.py against real zip archives and SHA256SUMS files.

No mocks: every fixture is a real zip written to a temporary tree, and the
generator runs as a subprocess exactly as the publisher workflow runs it. An
optional --release-dir adds a real downloaded product release (its Windows zip
and SHA256SUMS) for the product config named by --config.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

root = Path(__file__).resolve().parent.parent
generator = root / "scripts/scoop-manifest.py"
failures = []


def check(condition, message):
    print(("ok   " if condition else "FAIL ") + message)
    if not condition:
        failures.append(message)


def run(config, tag, release, bucket):
    result = subprocess.run([sys.executable, str(generator), "--config", str(config),
                             "--tag", tag, "--release-dir", str(release),
                             "--bucket", str(bucket)], text=True, capture_output=True)
    return result.returncode, (result.stdout + result.stderr).strip()


def release(tmp, name, version, members, sums=True, suffix=""):
    """A release directory with one Windows zip and (optionally) SHA256SUMS."""
    directory = tmp / f"rel-{version}{suffix}"
    directory.mkdir()
    asset = directory / f"{name}-{version}-windows-x86_64.zip"
    with zipfile.ZipFile(asset, "w", zipfile.ZIP_DEFLATED) as zf:
        for member in members:
            zf.writestr(f"{name}-{version}-windows-x86_64/{member}", f"{member} {version}{suffix}\n")
    digest = hashlib.sha256(asset.read_bytes()).hexdigest()
    if sums:
        (directory / "SHA256SUMS").write_text(
            f"{'0' * 64}  {name}_{version}-1_amd64.deb\n{digest} *{asset.name}\n")
    return directory, asset, digest


def fixture_tests(tmp):
    config = tmp / "demo.json"
    config.write_text(json.dumps({
        "repository": "metacraft-labs/demo", "app": "demo", "description": "Demo tool",
        "homepage": "https://example.invalid", "license": "MIT", "tag_prefix": "v",
        "architecture": {"64bit": {"asset": "demo-$version-windows-x86_64.zip",
                                   "extract_dir": "demo-$version-windows-x86_64"}},
        "bin": ["bin\\demo.exe"]}))
    bucket = tmp / "bucket"
    good = ["bin/demo.exe", "lib/demo.dll"]
    target = bucket / "demo.json"

    rel, asset, digest = release(tmp, "demo", "1.2.0", good)
    code, out = run(config, "v1.2.0", rel, bucket)
    check(code == 0 and "updated" in out, f"first publish writes the manifest ({out})")
    manifest = json.loads(target.read_text())
    arch = manifest["architecture"]["64bit"]
    check(manifest["version"] == "1.2.0", "manifest version comes from the tag")
    check(arch["hash"] == digest, "manifest hash is the archive's sha256")
    check(arch["url"] == "https://github.com/metacraft-labs/demo/releases/download/v1.2.0/"
                         "demo-1.2.0-windows-x86_64.zip", "manifest url names the release asset")
    check(arch["extract_dir"] == "demo-1.2.0-windows-x86_64", "extract_dir strips the top directory")
    check(manifest["bin"] == ["bin\\demo.exe"], "bin shims the configured executables")
    check(manifest["autoupdate"]["architecture"]["64bit"]["url"].endswith(
        "/v$version/demo-$version-windows-x86_64.zip"), "autoupdate url is templated")
    check(manifest["autoupdate"]["hash"] == {"url": "$baseurl/SHA256SUMS"},
          "autoupdate hashes come from the release's SHA256SUMS")
    first = target.read_bytes()

    code, out = run(config, "v1.2.0", rel, bucket)
    check(code == 0 and "unchanged" in out and target.read_bytes() == first,
          f"re-publishing the same release is a byte-identical no-op ({out})")

    with asset.open("ab") as stream:
        stream.write(b"tampered")
    code, out = run(config, "v1.2.0", rel, bucket)
    check(code != 0 and "SHA256SUMS says" in out and target.read_bytes() == first,
          f"a tampered archive is refused and the bucket is untouched ({out})")

    rel2, _, _ = release(tmp, "demo", "1.2.0", good, suffix="-rebuilt")
    code, out = run(config, "v1.2.0", rel2, bucket)
    check(code != 0 and "refusing to replace" in out and target.read_bytes() == first,
          f"different bytes for a published version are refused ({out})")

    rel3, _, _ = release(tmp, "demo", "1.3.0", good, sums=False)
    (rel3 / "SHA256SUMS").write_text(f"{'1' * 64}  something-else.zip\n")
    code, out = run(config, "v1.3.0", rel3, bucket)
    check(code != 0 and "not listed in SHA256SUMS" in out, f"an unlisted archive is refused ({out})")

    rel4, _, _ = release(tmp, "demo", "1.4.0", ["lib/demo.dll"])
    code, out = run(config, "v1.4.0", rel4, bucket)
    check(code != 0 and "does not contain bin" in out and target.read_bytes() == first,
          f"an archive without the configured bin is refused ({out})")

    rel5, _, digest5 = release(tmp, "demo", "1.10.0", good)
    code, out = run(config, "v1.10.0", rel5, bucket)
    check(code == 0 and "updated" in out
          and json.loads(target.read_text())["architecture"]["64bit"]["hash"] == digest5,
          f"a newer release (1.10.0 > 1.2.0, numerically) replaces the manifest ({out})")
    newest = target.read_bytes()

    code, out = run(config, "v1.2.0", rel, bucket)
    check(code == 0 and "skipped" in out and target.read_bytes() == newest,
          f"backfilling an older tag never downgrades the bucket ({out})")

    empty = tmp / "linux-only"
    empty.mkdir()
    (empty / "SHA256SUMS").write_text(f"{'2' * 64}  demo_2.0.0-1_amd64.deb\n")
    code, out = run(config, "v2.0.0", empty, bucket)
    check(code == 0 and "skipped" in out and target.read_bytes() == newest,
          f"a release without a Windows archive leaves the bucket alone ({out})")

    code, out = run(config, "v2.0.0-rc1", empty, bucket)
    check(code != 0 and "plain release version" in out, f"a pre-release tag is refused ({out})")

    code, out = run(config, "2.0.0", empty, bucket)
    check(code != 0 and "does not start with" in out, f"a tag without the prefix is refused ({out})")

    corrupt = tmp / "rel-corrupt"
    corrupt.mkdir()
    bad = corrupt / "demo-3.0.0-windows-x86_64.zip"
    bad.write_bytes(b"PK\x03\x04 not really a zip")
    (corrupt / "SHA256SUMS").write_text(
        f"{hashlib.sha256(bad.read_bytes()).hexdigest()}  {bad.name}\n")
    code, out = run(config, "v3.0.0", corrupt, bucket)
    check(code != 0 and "not a readable zip" in out and target.read_bytes() == newest,
          f"an archive that is listed but unreadable is refused ({out})")


def config_tests():
    publishers = set((root / "publishers.txt").read_text().split())
    configs = sorted((root / "scoop").glob("*.json"))
    check(bool(configs), "scoop/ holds at least one product config")
    apps = set()
    for path in configs:
        config = json.loads(path.read_text())
        missing = {"repository", "app", "description", "homepage", "license",
                   "architecture", "bin"} - set(config)
        check(not missing, f"{path.name} has every required key {sorted(missing) or ''}")
        check(config.get("repository") in publishers, f"{path.name}: repository is in publishers.txt")
        check(path.stem == config.get("repository", "").split("/")[-1],
              f"{path.name} is named after its repository")
        check(config.get("app") not in apps, f"{path.name}: app name is unique")
        apps.add(config.get("app"))
    for path in sorted((root / "bucket").glob("*.json")):
        manifest = json.loads(path.read_text())
        check({"version", "architecture", "bin"} <= set(manifest),
              f"bucket/{path.name} parses and has version, architecture and bin")


def real_release_test(tmp, config, release_dir):
    bucket = tmp / "real-bucket"
    config_data = json.loads(config.read_text())
    zips = sorted(release_dir.glob("*-windows-*.zip"))
    check(bool(zips), f"{release_dir} holds a Windows zip")
    if not zips:
        return
    asset_template = config_data["architecture"]["64bit"]["asset"]
    head, tail = asset_template.split("$version")
    versions = [match.group(1) for path in zips
                if (match := re.fullmatch(re.escape(head) + r"([0-9]+(?:\.[0-9]+)*)" +
                                         re.escape(tail), path.name))]
    check(len(versions) == 1, "release holds exactly one configured 64-bit archive")
    if len(versions) != 1:
        return
    version = versions[0]
    tag = config_data.get("tag_prefix", "") + version
    code, out = run(config, tag, release_dir, bucket)
    check(code == 0 and "updated" in out, f"real {zips[0].name} produces a manifest ({out})")
    code, out = run(config, tag, release_dir, bucket)
    check(code == 0 and "unchanged" in out, f"real release re-run is a no-op ({out})")
    tampered = tmp / "real-tampered"
    shutil.copytree(release_dir, tampered)
    with (tampered / zips[0].name).open("r+b") as stream:
        stream.seek(1000)
        byte = stream.read(1)
        stream.seek(1000)
        stream.write(bytes([byte[0] ^ 0xFF]))
    code, out = run(config, tag, tampered, tmp / "real-bucket-2")
    check(code != 0 and "SHA256SUMS says" in out and not (tmp / "real-bucket-2").exists(),
          f"real release with one flipped byte is refused ({out})")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path)
    parser.add_argument("--config", type=Path, default=root / "scoop/reprobuild.json")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="scoop-test-") as tmp:
        tmp = Path(tmp)
        fixture_tests(tmp)
        config_tests()
        if args.release_dir:
            real_release_test(tmp, args.config, args.release_dir)
    print(f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
