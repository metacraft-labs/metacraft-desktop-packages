#!/usr/bin/env python3
"""Generate a macOS ARM64 formula from a checked, immutable release archive.

The tap keeps release metadata beside each formula. Publishing an older version
is a no-op; changing the archive for an existing version is refused. Every
installed payload file can be compared with the retained checksums.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import struct
import sys
import tarfile


class Refused(Exception):
    pass


def version_key(version):
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*", version):
        raise Refused("only plain release versions can enter the tap")
    return tuple(map(int, version.split(".")))


def checksum(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def native_arm64(data):
    if len(data) < 8:
        return False
    if struct.unpack("<II", data[:8]) == (0xFEEDFACF, 0x0100000C):
        return True
    magic, count = struct.unpack(">II", data[:8])
    if magic != 0xCAFEBABE or not 1 <= count <= 32 or len(data) < 8 + count * 20:
        return False
    # io-mon ships both arm64 and arm64e slices in its released shim. Require
    # every fat-header entry and the actual slice header to be ARM64.
    for index in range(count):
        cpu, _, offset, size, _ = struct.unpack_from(">IIIII", data, 8 + index * 20)
        if cpu != 0x0100000C or size < 8 or offset + size > len(data):
            return False
        if struct.unpack_from("<II", data, offset) != (0xFEEDFACF, cpu):
            return False
    return True


def inspect_archive(path, root, native_files):
    payload = {}
    try:
        with tarfile.open(path, "r:gz") as archive:
            for member in archive:
                name = PurePosixPath(member.name)
                if not name.parts or name.is_absolute() or ".." in name.parts or name.parts[0] != root:
                    raise Refused(f"unsafe archive member: {member.name}")
                if member.isdir():
                    continue
                relative = str(name.relative_to(root))
                if relative in payload or relative == ".":
                    raise Refused(f"duplicate or invalid member: {member.name}")
                if member.issym():
                    target = PurePosixPath(member.linkname)
                    if target.is_absolute() or ".." in target.parts:
                        raise Refused(f"unsafe symlink: {member.name}")
                    payload[relative] = {"symlink": member.linkname}
                elif member.isfile():
                    data = archive.extractfile(member).read()
                    payload[relative] = {"sha256": hashlib.sha256(data).hexdigest()}
                else:
                    raise Refused(f"unsupported archive member: {member.name}")
            for relative in native_files:
                member = archive.getmember(f"{root}/{relative}")
                data = archive.extractfile(member).read()
                if not native_arm64(data):
                    raise Refused(f"{relative} is not a native ARM64 Mach-O payload")
            if not payload:
                raise Refused("archive has no payload files")
    except (tarfile.TarError, KeyError, OSError) as error:
        raise Refused(f"invalid release archive: {error}") from error
    return payload


def formula(config, metadata):
    tests = {
        "gosti": '''    assert_match "qemu-boot", shell_output("#{bin}/gosti backends")
    assert_match "qemu-boot", shell_output("#{bin}/vm-harness backends")''',
        "runquota": '''    assert_match version.to_s, shell_output("#{bin}/runquota --version")
    assert_match version.to_s, shell_output("#{bin}/runquotad --version")''',
        "io-mon": '''    (testpath/"input.txt").write "release-input"
    (testpath/"probe.rb").write 'File.binwrite(ARGV[1], File.binread(ARGV[0]) + "-captured"); exit 7'
    shell_output("#{bin}/io-mon run --depfile #{testpath}/capture.rdep -- #{RbConfig.ruby} #{testpath}/probe.rb #{testpath}/input.txt #{testpath}/output.txt", 7)
    assert_equal "release-input-captured", (testpath/"output.txt").read
    evidence = JSON.parse(shell_output("#{bin}/io-mon inspect #{testpath}/capture.rdep --format json"))
    assert_equal "mcComplete", evidence.fetch("completeness")
    assert_equal 0, evidence.fetch("summary").fetch("eventLossCount")''',
    }
    if config["app"] not in tests:
        raise Refused("product needs a reviewed functional formula test")
    quote = json.dumps
    links = "\n".join(f"    bin.install_symlink libexec/{quote(path)}" for path in config["bin"])
    return f'''# Generated from verified release assets by homebrew-formula.py.
class {config["class_name"]} < Formula
  desc {quote(config["description"])}
  homepage {quote(config["homepage"])}
  url {quote(metadata["url"])}
  version {quote(metadata["version"])}
  sha256 {quote(metadata["sha256"])}
  license {quote(config["license"])}

  depends_on :macos
  depends_on arch: :arm64

  # Preserve the published payload, including its ad-hoc signatures and data.
  preserve_rpath
  skip_clean "libexec"

  def install
    libexec.install Dir["*"]
{links}
  end

  test do
{tests[config["app"]]}
  end
end
'''


def update(config_path, tag, release_dir, tap):
    config = json.loads(config_path.read_text())
    prefix = config.get("tag_prefix", "v")
    if not tag.startswith(prefix):
        raise Refused("tag does not match its configured prefix")
    version = tag[len(prefix):]
    current_key = version_key(version)
    app = config["app"]
    if not re.fullmatch(r"[a-z][a-z0-9-]*", app) or not re.fullmatch(r"[A-Z][A-Za-z0-9]*", config["class_name"]):
        raise Refused("invalid formula name")
    target = tap / "Formula" / f"{app}.rb"
    record = tap / "releases" / f"{app}.json"
    current = json.loads(record.read_text()) if record.exists() else None
    if target.exists() and current is None:
        raise Refused("existing formula has no release metadata")
    if current and version_key(current["version"]) > current_key:
        return "skipped", f"{app} already publishes {current['version']}"
    asset = config["asset"].replace("$version", version)
    if Path(asset).name != asset:
        raise Refused("asset must be a basename")
    archive = release_dir / asset
    sums = {}
    for line in (release_dir / "SHA256SUMS").read_text().splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *](.+)", line)
        if match:
            sums.setdefault(match[2], set()).add(match[1].lower())
    digest = checksum(archive)
    if sums.get(asset) != {digest}:
        raise Refused(f"{asset} does not match its release SHA256SUMS")
    if current and current["version"] == version and current["sha256"] != digest:
        raise Refused("a published version cannot change its archive bytes")
    root = config["extract_dir"].replace("$version", version)
    payload = inspect_archive(archive, root, config["native_files"])
    metadata = {
        "repository": config["repository"], "version": version, "asset": asset,
        "url": f"https://github.com/{config['repository']}/releases/download/{tag}/{asset}",
        "sha256": digest, "architecture": "arm64", "payload": payload,
    }
    rendered = formula(config, metadata)
    encoded = json.dumps(metadata, indent=2, sort_keys=True) + "\n"
    if target.exists() and target.read_text() == rendered and record.read_text() == encoded:
        return "unchanged", f"{app} already describes {version}"
    target.parent.mkdir(parents=True, exist_ok=True)
    record.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered)
    record.write_text(encoded)
    return "updated", f"{app} -> {version}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--tap", type=Path, required=True)
    args = parser.parse_args()
    try:
        status, detail = update(args.config, args.tag, args.release_dir, args.tap)
    except (Refused, OSError, ValueError) as error:
        print(f"homebrew-formula: refused: {error}", file=sys.stderr)
        return 1
    print(f"homebrew-formula: {status} {detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
