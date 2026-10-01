# Metacraft Labs Desktop Packages
Desktop packages for Metacraft Labs. Current formats:

1. DEBs - Installation instructions at <https://deb.metacraft-labs.com>
1. RPMs - Installation instructions at <https://rpm.metacraft-labs.com>
1. Gentoo ebuilds - Installation instructions on the [metacraft-overlay](https://github.com/metacraft-labs/metacraft-overlay) repository
1. Arch PKGBUILDs - A list of packages can be seen on [our AUR page](https://aur.archlinux.org/packages?SeB=m&K=codetracer)
1. Scoop manifests (Windows) - this repository is the organisation's Scoop bucket:

   ```powershell
   scoop bucket add metacraft https://github.com/metacraft-labs/metacraft-desktop-packages
   scoop install metacraft/reprobuild
   ```

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

CodeTracer publishes this way too. Its `.deb`/`.rpm` used to be built here
from recipes by `rpm-and-deb.yaml`, which rebuilt the indices from that run's
packages alone; that workflow and its `rpm/SPECS` recipes are retired. The
Arch PKGBUILD and the Gentoo ebuild are still recipes here.

Apt publishes SHA256/SHA512 by-hash indices before its signed entrypoint.
Earlier hashed apt and RPM metadata remain available for clients that still
hold a previous signed entrypoint. Mutable entrypoints request revalidation;
immutable indices can be cached without mixing releases.

Publication and live installation checks use the shared `CI_RUNNER_MODE`
selector. This public repository defaults to standard `ubuntu-24.04`; an
org/repository override selects the existing `[self-hosted, linux, x64]`
fallback. Publication provisions Nix explicitly. Signing credentials remain
managed by infra's Terraform secret projection, and all publishing runs share
the same serialized concurrency group.

### The Scoop bucket

[`bucket/`](bucket) is the organisation's Scoop bucket; Scoop reads manifests
from `bucket/` on the default branch. The same `publish-release` dispatch
fills it: when the product has a config in [`scoop/`](scoop)
(`scoop/<repository>.json`: app name, description, the Windows zip's name,
its top-level directory and the executables to shim) and the release is not
a pre-release, the `scoop` job verifies the zip against the release's
`SHA256SUMS`, checks that it contains the configured executables, and writes
`bucket/<app>.json` (`scripts/scoop-manifest.py`).

`dev` accepts changes only through pull requests, so the job opens a
`scoop/<app>-<version>-<run>-<attempt>` PR and merges the expected head with
a normal merge commit. Each attempt uses a new branch and an ordinary push.
A re-run for the same
release is a no-op, a different zip for a published version is refused, and
publishing an older tag never downgrades a manifest. A product joins by
adding its config here; nothing else changes on its side.

[`verify-scoop-bucket.yaml`](.github/workflows/verify-scoop-bucket.yaml)
installs through Scoop on Windows: on pull requests from a manifest generated
from a real release, and when dispatched from the live bucket (optionally
also running a product's `irm <url> | iex` installer).

[`verify-tool-scoop.yaml`](.github/workflows/verify-tool-scoop.yaml) exercises
Gosti, io-mon and RunQuota through Scoop on Windows x64, and Gosti and RunQuota
on native Windows ARM64. It compares every installed file to the release zip,
checks native PE architecture and released CLI commands, and runs a real io-mon
capture with complete dependency records and exact child exit propagation.
PRs use generated manifests; dispatch checks the published org bucket.

### The Homebrew tap

The shared macOS tap is `metacraft-labs/homebrew-metacraft`:

```sh
brew tap metacraft-labs/metacraft
brew install metacraft-labs/metacraft/gosti metacraft-labs/metacraft/io-mon metacraft-labs/metacraft/runquota
```

The first releases support native macOS ARM64. Configs in [`homebrew/`](homebrew)
select each immutable release archive and its commands. The same serialized
`publish-release` workflow verifies SHA256SUMS and Mach-O architecture, generates
the formula and per-file metadata, installs it through Homebrew on native macOS,
and checks every installed payload file and the formula's functional behavior.
Homebrew may move license documents into the package prefix; their bytes are
checked there. Executables and libraries retain their released bytes.

The publisher uses a short-lived App token scoped to the tap, then promotes
through ordinary pull requests into `dev` and its public default branch `stable`.
Terraform owns the repository and branch protections. Publication never rewrites
history: retries use unique branches, older releases cannot downgrade formulas,
and a published version cannot acquire different archive bytes.

[`verify-tool-homebrew.yaml`](.github/workflows/verify-tool-homebrew.yaml)
tests all three products using generated candidates on PRs and the public tap
when dispatched. It also checks package receipts, tap revision, native
architecture, command links and io-mon's complete capture of a real child.

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
Debian 11 uses signed Debian snapshots from 2026-08-31 for its test
prerequisites, because its live security index names removed packages after
LTS ended. The Metacraft repository is always read live.

The check uses the committed repository trust key, downloads all required Linux
architectures through apt/dnf, compares their packages with the GitHub release,
and compares every installed payload file with the verified release archive.
RPM comparison uses its payload digest because repository signing changes
the package bytes. ARM64 package metadata and downloads are checked here;
native ARM64 execution remains a mandatory producer release check.
The approved first releases of Gosti, io-mon and RunQuota (0.1.0) target
Linux x86_64 only. Later versions require both architecture checks again.
Logs and resolved container image digests are retained as workflow artifacts.
