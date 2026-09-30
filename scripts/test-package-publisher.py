#!/usr/bin/env python3
"""Exercise real deb/rpm archives, repository tools and a disposable signing key.

No mocks: the fixtures are valid packages with small text payloads. An optional
release directory adds the exact downloaded product deb/rpm files to the test.
Everything, including the GnuPG home and RPM database, stays in a temporary tree.
"""
import argparse
import gzip
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def run(*args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path, action="append", default=[])
    parser.add_argument("--publisher", type=Path,
                        default=Path(__file__).with_name("publish-into-repositories.sh"))
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="package-test-", dir="/tmp") as root:
        root = Path(root)
        incoming, deb_repo, rpm_repo = (root / p for p in ("incoming", "deb", "rpm"))
        for path in (incoming, deb_repo / "pool", rpm_repo):
            path.mkdir(parents=True)
        key_home = root / "gnupg"
        key_home.mkdir(mode=0o700)
        env = dict(os.environ, GNUPGHOME=str(key_home))
        try:
            run("gpg", "--batch", "--pinentry-mode", "loopback", "--passphrase", "",
                "--quick-generate-key", "Publisher test <publisher@example.invalid>",
                "rsa2048", "sign", "0", env=env)
            keys = run("gpg", "--batch", "--with-colons", "--list-secret-keys",
                       env=env, capture_output=True).stdout
            fingerprint = next(line.split(":")[9] for line in keys.splitlines()
                               if line.startswith("fpr:"))

            def deb(name, version, arch, metadata=""):
                tree = root / f"{name}-{version}-{arch}"
                (tree / "DEBIAN").mkdir(parents=True)
                (tree / "DEBIAN/control").write_text(
                    f"Package: {name}\nVersion: {version}\nArchitecture: {arch}\n"
                    "Maintainer: Publisher test <publisher@example.invalid>\n"
                    f"Description: Real package import fixture\n{metadata}")
                payload = tree / f"usr/share/{name}/payload"
                payload.parent.mkdir(parents=True)
                payload.write_text(f"{name} {version} {arch}\n")
                target = incoming / f"{name}_{version}_{arch}.deb"
                run("dpkg-deb", "--build", "--root-owner-group", str(tree), str(target))
                return target

            old = deb("publisher-dual", "9.0-1", "amd64")
            old_pool = deb_repo / "pool/main/p/publisher-dual" / old.name
            old_pool.parent.mkdir(parents=True)
            shutil.copy2(old, old_pool)
            deb("publisher-dual", "1:1.0-1", "amd64")
            deb("publisher-dual", "1:1.0-1", "arm64")
            deb("publisher-all", "1.0-1", "all", "Section: devel\nPriority: extra\n")
            for directory in args.release_dir:
                for pattern in ("*.deb", "*.rpm"):
                    for package in directory.glob(pattern):
                        shutil.copy2(package, incoming / package.name)

            spec = root / "publisher.spec"
            spec.write_text("""Name: publisher-test
Version: 1.0
Release: 1
Summary: Real RPM import fixture
License: MIT
BuildArch: noarch
%description
Exercises the real repository publisher.
%install
mkdir -p %{buildroot}/usr/share/publisher-test
echo payload > %{buildroot}/usr/share/publisher-test/payload
%files
/usr/share/publisher-test/payload
""")
            run("rpmbuild", "--define", f"_topdir {root / 'rpmbuild'}",
                "--define", f"_dbpath {root / 'rpmdb'}", "-bb", str(spec))
            for package in (root / "rpmbuild/RPMS").glob("*/*.rpm"):
                shutil.copy2(package, incoming / package.name)
            before = {p.name: sha(p) for p in incoming.iterdir()}

            command = ["bash", str(args.publisher.resolve()), "--incoming", str(incoming),
                       "--deb-dir", str(deb_repo), "--rpm-dir", str(rpm_repo),
                       "--key-id", fingerprint]
            run(*command, env=env)
            assert before == {p.name: sha(p) for p in incoming.iterdir()}, "input changed"
            assert sha(old_pool) == before[old.name], "older archive disappeared"

            def entries(arch):
                text = gzip.decompress((deb_repo / f"dists/stable/main/binary-{arch}/Packages.gz")
                                       .read_bytes()).decode()
                return {record["Package"]: record for stanza in text.strip().split("\n\n")
                        if stanza for record in [dict(line.split(": ", 1) for line in
                                                      stanza.splitlines() if ": " in line)]}

            for arch in ("amd64", "arm64"):
                indexed = entries(arch)
                dual = indexed["publisher-dual"]
                assert dual["Architecture"] == arch
                assert dual["Version"] == "1:1.0-1", dual
                assert dual["Section"] == "utils" and dual["Priority"] == "optional"
                assert indexed["publisher-all"]["Section"] == "devel"
                assert indexed["publisher-all"]["Priority"] == "extra"
                for record in indexed.values():
                    path = deb_repo / record["Filename"]
                    assert sha(path) == record["SHA256"], path

            run("gpg", "--batch", "--verify", str(deb_repo / "dists/stable/InRelease"), env=env)
            run("gpg", "--batch", "--verify", str(rpm_repo / "repodata/repomd.xml.asc"),
                str(rpm_repo / "repodata/repomd.xml"), env=env)
            public_key = root / "public.asc"
            public_key.write_text(run("gpg", "--armor", "--export", fingerprint,
                                      env=env, capture_output=True).stdout)
            rpm_db = str(root / "verify-rpmdb")
            run("rpm", "--dbpath", rpm_db, "--import", str(public_key))
            for package in (rpm_repo / "RPMS").glob("*/*.rpm"):
                run("rpmkeys", "--dbpath", rpm_db, "--checksig", str(package))

            pooled = {str(p.relative_to(root)): sha(p) for pattern in
                      ("deb/pool/**/*.deb", "rpm/RPMS/**/*.rpm") for p in root.glob(pattern)}
            run(*command, env=env)
            assert all(sha(root / p) == digest for p, digest in pooled.items()), "retry changed packages"
            # Same identity with changed bytes must fail, leaving published files intact.
            changed = incoming / "publisher-all_1.0-1_all.deb"
            tree = root / "publisher-all-1.0-1-all"
            (tree / "usr/share/publisher-all/payload").write_text("changed payload\n")
            run("dpkg-deb", "--build", "--root-owner-group", str(tree), str(changed))
            result = subprocess.run(command, env=env, text=True, capture_output=True)
            assert result.returncode != 0 and "refusing" in result.stderr, result
            assert all(sha(root / p) == digest for p, digest in pooled.items()), "rejection changed packages"
            print("PASS: metadata defaults, both architectures, Debian epochs, signatures, immutable retry and rejection")
        finally:
            subprocess.run(["gpgconf", "--kill", "all"], env=env, check=False)


if __name__ == "__main__":
    main()
