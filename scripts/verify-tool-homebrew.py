#!/usr/bin/env python3
"""Install real release formulas, then check their origin, files and behavior.

No mocks. Use a clean native macOS ARM64 Homebrew prefix. With --live the tap
is cloned from its public default branch; --tap-path tests a prepared candidate.
Otherwise a candidate is generated from the three public v0.1.0 releases.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
source = parser.add_mutually_exclusive_group()
source.add_argument("--live", action="store_true")
source.add_argument("--tap-path", type=Path)
parser.add_argument("--products", nargs="+", choices=["gosti", "io-mon", "runquota"],
                    default=["gosti", "io-mon", "runquota"])
parser.add_argument("--brew", default="brew")
args = parser.parse_args()
assert platform.system() == "Darwin" and platform.machine() == "arm64", "native macOS ARM64 required"
root = Path(__file__).resolve().parent.parent
tap_name = "metacraft-labs/metacraft"
tap_url = "https://github.com/metacraft-labs/homebrew-metacraft"
env = dict(os.environ, HOMEBREW_NO_AUTO_UPDATE="1", HOMEBREW_NO_ANALYTICS="1",
           HOMEBREW_NO_INSTALL_FROM_API="1", HOMEBREW_NO_INSTALL_CLEANUP="1")


def run(command, **kwargs):
    return subprocess.run([str(arg) for arg in command], check=True, text=True, env=env, **kwargs)


def output(command):
    return run(command, stdout=subprocess.PIPE).stdout.strip()


def brew(*command):
    return [args.brew, *command]


assert tap_name not in output(brew("tap")).splitlines(), "use a clean prefix; existing tap left untouched"
installed = set(output(brew("list", "--formula", "-1")).splitlines())
assert not installed.intersection(args.products), "use a clean prefix; existing packages left untouched"

with tempfile.TemporaryDirectory(prefix="tool-homebrew-") as temporary:
    work = Path(temporary)
    tap = args.tap_path.resolve() if args.tap_path else work / "tap"
    if args.live:
        run(brew("tap", tap_name, tap_url))
        tap = Path(output(brew("--repository", tap_name)))
        remote = output(["git", "-C", tap, "remote", "get-url", "origin"])
        assert remote.removesuffix(".git") == tap_url, remote
        assert output(["git", "-C", tap, "branch", "--show-current"]) == "stable"
    elif not args.tap_path:
        tap.mkdir()
    for app in args.products:
        config = root / "homebrew" / f"{app}.json"
        settings = json.loads(config.read_text())
        record = tap / "releases" / f"{app}.json"
        version = json.loads(record.read_text())["version"] if record.exists() else "0.1.0"
        tag = settings["tag_prefix"] + version
        asset = settings["asset"].replace("$version", version)
        release = work / app
        release.mkdir()
        run(["gh", "release", "download", tag, "-R", settings["repository"],
             "-D", release, "-p", asset, "-p", "SHA256SUMS"])
        destination = tap
        if args.live or args.tap_path:
            # Regenerate independently: the public/candidate metadata must
            # describe the actual immutable release, not merely itself.
            destination = work / f"expected-{app}"
        run([sys.executable, root / "scripts/homebrew-formula.py", "--config", config,
             "--tag", tag, "--release-dir", release, "--tap", destination])
        if destination != tap:
            for relative in (f"Formula/{app}.rb", f"releases/{app}.json"):
                assert (tap / relative).read_bytes() == (destination / relative).read_bytes(), relative
    if not args.live:
        # Commit only in a private copy, leaving the caller's checkout intact.
        candidate = work / "candidate"
        import shutil
        shutil.copytree(tap, candidate, ignore=shutil.ignore_patterns(".git"))
        run(["git", "init", "-q", "-b", "stable", candidate])
        run(["git", "-C", candidate, "add", "Formula", "releases"])
        run(["git", "-C", candidate, "-c", "user.name=Package verification",
             "-c", "user.email=package-verification@users.noreply.github.com",
             "-c", "commit.gpgsign=false", "commit", "-qm", "Verify release formulas"])
        run(brew("tap", tap_name, candidate))
        tap = Path(output(brew("--repository", tap_name)))
        assert output(["git", "-C", tap, "remote", "get-url", "origin"]) == str(candidate)
    head = output(["git", "-C", tap, "rev-parse", "HEAD"])
    formulas = [f"{tap_name}/{app}" for app in args.products]
    run(brew("install", *formulas))
    for app, formula in zip(args.products, formulas):
        metadata = json.loads((tap / "releases" / f"{app}.json").read_text())
        prefix = Path(output(brew("--prefix", formula))).resolve()
        receipt = json.loads((prefix / "INSTALL_RECEIPT.json").read_text())
        assert receipt["source"]["tap"] == tap_name, receipt
        assert receipt["source"]["tap_git_head"] == head, receipt
        assert receipt["source"]["versions"]["stable"] == metadata["version"], receipt
        assert receipt["arch"] == "arm64", receipt
        run([sys.executable, root / "scripts/verify-homebrew-payload.py",
             "--metadata", tap / "releases" / f"{app}.json", "--installed", prefix])
        settings = json.loads((root / "homebrew" / f"{app}.json").read_text())
        brew_prefix = Path(output(brew("--prefix")))
        for binary in settings["bin"]:
            command = brew_prefix / "bin" / Path(binary).name
            expected_command = prefix / "libexec" / binary
            assert command.is_symlink() and command.resolve() == expected_command.resolve(), command
        run(brew("test", formula))
        print(f"PASS: {app} {metadata['version']} from {tap_name}@{head}", flush=True)
