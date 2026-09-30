#!/usr/bin/env python3
"""Write or refresh one product's manifest in the organisation's Scoop bucket.

    scoop-manifest.py --config scoop/<product>.json --tag TAG \
        --release-dir DIR --bucket bucket/

--release-dir holds what was downloaded from the product's GitHub Release: its
Windows archive(s) and SHA256SUMS. Nothing else is trusted: an archive must be
listed in SHA256SUMS with the hash it actually has, and it must contain the
extract_dir and every bin the config names, so a manifest is only ever written
for an archive Scoop will be able to install.

The config (scoop/<product>.json) is the product's Scoop description:

    repository   owner/name of the GitHub repository that publishes releases
    app          manifest name, i.e. `scoop install <app>`
    description, homepage, license
    tag_prefix   what precedes the version in the tag ("v" for v1.2.3)
    architecture {"64bit": {"asset": "...$version...", "extract_dir": "..."}}
    bin          paths inside extract_dir to shim onto PATH (Scoop's `bin`)

Outcomes, printed as the last line (`scoop-manifest: <outcome> ...`):

    updated    bucket/<app>.json was written (new, newer, or config changed)
    unchanged  the manifest already says exactly this; nothing written
    skipped    the release has none of the configured assets, or the bucket
               already carries a NEWER version (a backfill of an older tag
               never downgrades what `scoop install` gets)

A release that re-publishes an already-published version with different bytes
is an error, as for the apt and RPM repositories: a published version is never
overwritten (package-distribution.md §9).
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

SCOOP_ARCHES = ("64bit", "32bit", "arm64")
VERSION_RE = re.compile(r"^[0-9]+(\.[0-9]+)*$")


class Refused(Exception):
    pass


def version_key(version):
    return tuple(int(part) for part in version.split("."))


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_sums(path):
    sums = {}
    for line in path.read_text().splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *](.+)", line.strip())
        if match:
            sums.setdefault(match.group(2), set()).add(match.group(1).lower())
    return sums


def check_layout(archive, extract_dir, bins):
    try:
        with zipfile.ZipFile(archive) as zf:
            names = set(zf.namelist())
            bad = zf.testzip()
    except zipfile.BadZipFile as error:
        raise Refused(f"{archive.name} is not a readable zip: {error}")
    if bad is not None:
        raise Refused(f"{archive.name}: member {bad} fails its CRC check")
    prefix = f"{extract_dir}/" if extract_dir else ""
    if prefix and not any(n.startswith(prefix) for n in names):
        raise Refused(f"{archive.name} has no top-level directory {extract_dir}/")
    for entry in bins:
        target = entry[0] if isinstance(entry, list) else entry
        member = prefix + target.replace("\\", "/")
        if member not in names:
            raise Refused(f"{archive.name} does not contain bin {target} (looked for {member})")


def build(config, version, release_dir, sums):
    repo = config["repository"]
    tag = config.get("tag_prefix", "") + version
    architecture, autoupdate_arch, present, missing = {}, {}, [], []
    for arch, spec in config["architecture"].items():
        if arch not in SCOOP_ARCHES:
            raise Refused(f"unknown Scoop architecture {arch!r}")
        asset = spec["asset"].replace("$version", version)
        (present if (release_dir / asset).is_file() else missing).append(asset)
    if not present:
        return None, f"release has none of {', '.join(missing)}"
    if missing:
        raise Refused(f"release has {', '.join(present)} but not {', '.join(missing)}")

    for arch, spec in config["architecture"].items():
        asset = spec["asset"].replace("$version", version)
        path = release_dir / asset
        listed = sums.get(asset)
        if not listed:
            raise Refused(f"{asset} is not listed in SHA256SUMS")
        actual = sha256(path)
        if listed != {actual}:
            raise Refused(f"{asset} has sha256 {actual}, SHA256SUMS says {', '.join(sorted(listed))}")
        extract_dir = spec.get("extract_dir", "").replace("$version", version)
        check_layout(path, extract_dir, config["bin"])
        entry = {"url": f"https://github.com/{repo}/releases/download/{tag}/{asset}",
                 "hash": actual}
        auto = {"url": f"https://github.com/{repo}/releases/download/"
                       f"{config.get('tag_prefix', '')}$version/{spec['asset']}"}
        if extract_dir:
            entry["extract_dir"] = extract_dir
            auto["extract_dir"] = spec["extract_dir"]
        architecture[arch] = entry
        autoupdate_arch[arch] = auto

    manifest = {
        "version": version,
        "description": config["description"],
        "homepage": config["homepage"],
        "license": config["license"],
        "architecture": architecture,
        "bin": config["bin"],
        # Scoop's github checkver reads the latest (non-prerelease) release.
        "checkver": {"github": f"https://github.com/{repo}"},
        "autoupdate": {
            "architecture": autoupdate_arch,
            # Every release carries SHA256SUMS, so `scoop install app@x.y.z`
            # verifies against the release's own sums instead of hashing
            # whatever it downloaded.
            "hash": {"url": "$baseurl/SHA256SUMS"},
        },
    }
    return manifest, None


def render(manifest):
    return json.dumps(manifest, indent=4, ensure_ascii=False) + "\n"


def update(config_path, tag, release_dir, bucket):
    config = json.loads(config_path.read_text())
    prefix = config.get("tag_prefix", "")
    if not tag.startswith(prefix):
        raise Refused(f"tag {tag!r} does not start with {prefix!r}")
    version = tag[len(prefix):]
    if not VERSION_RE.fullmatch(version):
        raise Refused(f"{version!r} is not a plain release version; Scoop gets releases only")
    sums_path = release_dir / "SHA256SUMS"

    target = bucket / f"{config['app']}.json"
    current = None
    if target.exists():
        current = json.loads(target.read_text())
        if version_key(current["version"]) > version_key(version):
            return "skipped", f"{target} already has newer {current['version']}"

    if not any((release_dir / s["asset"].replace("$version", version)).is_file()
               for s in config["architecture"].values()):
        return "skipped", "release has no Windows archive for Scoop"
    if not sums_path.is_file():
        raise Refused("release has no SHA256SUMS")
    manifest, why = build(config, version, release_dir, read_sums(sums_path))
    if manifest is None:
        return "skipped", why

    if current is not None and current["version"] == version:
        for arch, entry in manifest["architecture"].items():
            old = current.get("architecture", {}).get(arch, {}).get("hash")
            if old is not None and old != entry["hash"]:
                raise Refused(f"{config['app']} {version} is already published with "
                              f"{arch} hash {old}; refusing to replace it with {entry['hash']}")
    text = render(manifest)
    if target.exists() and target.read_text() == text:
        return "unchanged", f"{target} already describes {version}"
    bucket.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    return "updated", f"{target} -> {version}"


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--bucket", type=Path, required=True)
    args = parser.parse_args()
    try:
        outcome, detail = update(args.config, args.tag, args.release_dir, args.bucket)
    except Refused as error:
        print(f"scoop-manifest: refused: {error}", file=sys.stderr)
        return 1
    print(f"scoop-manifest: {outcome} {detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
