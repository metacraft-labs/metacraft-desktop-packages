# Metacraft Labs Desktop Packages
Desktop packages for Metacraft Labs. Current formats:

1. DEBs - Installation instructions at <https://deb.metacraft-labs.com>
1. RPMs - Installation instructions at <https://rpm.metacraft-labs.com>
1. Gentoo ebuilds - Installation instructions on the [metacraft-overlay](https://github.com/metacraft-labs/metacraft-overlay) repository
1. Arch PKGBUILDs - A list of packages can be seen on [our AUR page](https://aur.archlinux.org/packages?SeB=m&K=codetracer)

## Publishing a product release

There is one apt and one RPM repository for every Metacraft product,
signed with the organisation's key
(`22F8 0A4A 65B0 8E36 AEA8  9F57 E127 BF3A C4CE 1719`,
"Metacraft Labs Package Repositories", expires 2028-09-27). A product builds its
`.deb` and `.rpm` from its release payload, attaches them to its GitHub
Release beside `SHA256SUMS`, and after the Release is published sends a
`repository_dispatch` of type `publish-release` with
`{"repository": "metacraft-labs/<product>", "tag": "<tag>"}`.

[`publish-release.yaml`](.github/workflows/publish-release.yaml) then
verifies the packages against the Release's `SHA256SUMS` and adds them to
both repositories (`scripts/publish-into-repositories.sh`). It regenerates
and signs the indices over every package already published, so publishing
one product never removes another. Runs are serialized and never cancelled.
A product must be listed in [`publishers.txt`](publishers.txt).

Publication and live installation checks use the shared `CI_RUNNER_MODE`
selector. This public repository defaults to standard `ubuntu-24.04`; an
org/repository override selects the existing `[self-hosted, linux, x64]`
fallback. Publication provisions Nix explicitly. Signing credentials remain
managed by infra's Terraform secret projection, and all publishing runs share
the same serialized concurrency group.

### The trust anchor

[`keys/`](keys) holds the organisation's public key, committed once and
uploaded verbatim to both hosts on every publish. Its bytes do not change,
so installers pin them by digest:

| Published at | SHA-256 |
|---|---|
| `https://{deb,rpm}.metacraft-labs.com/keys/metacraft-labs-archive-keyring.gpg` | `e738c80f2d7bf230b868f5f140acecef20904333c6892e8f17670fa11483e9dc` |
| `https://{deb,rpm}.metacraft-labs.com/keys/metacraft-labs-archive-keyring.asc` | `aa89db2215ce0b33e029b8302d4d94fac742b92d279f178437abe10d9b54c988` |

The `.asc` is also served at the paths existing users already have:
`deb.metacraft-labs.com/keys/public.asc` and `rpm.metacraft-labs.com/rpmkey.pub`.
The publisher refuses to sign with any key other than the one in `keys/`.
Changing it is a key rotation, so every installer's pinned digest changes
in the same release.

The design is specified in metacraft-specs,
`infrastructure/package-distribution.md` §3 and §9.1.

## Verify published tool packages

After publishing Gosti, io-mon or RunQuota, dispatch
`verify-tool-release.yaml` with the product name and version (without `v`).
It installs that exact version from the public apt/RPM repositories in
Debian 11, Ubuntu 24.04 and AlmaLinux 9 containers on native Linux x86_64.

The check uses the committed repository trust key, downloads all required Linux
architectures through apt/dnf, compares their packages with the GitHub release,
and compares every installed payload file with the verified release archive.
RPM comparison uses its payload digest because repository signing changes
the package bytes. ARM64 package metadata and downloads are checked here;
native ARM64 execution remains a mandatory producer release check.
The approved first releases of Gosti, io-mon and RunQuota (0.1.0) target
Linux x86_64 only. Later versions require both architecture checks again.
Logs and resolved container image digests are retained as workflow artifacts.
