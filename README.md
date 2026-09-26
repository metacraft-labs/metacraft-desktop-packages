# Metacraft Labs Desktop Packages
Desktop packages for Metacraft Labs. Current formats:

1. DEBs - Installation instructions at <https://deb.metacraft-labs.com>
1. RPMs - Installation instructions at <https://rpm.metacraft-labs.com>
1. Gentoo ebuilds - Installation instructions on the [metacraft-overlay](https://github.com/metacraft-labs/metacraft-overlay) repository
1. Arch PKGBUILDs - A list of packages can be seen on [our AUR page](https://aur.archlinux.org/packages?SeB=m&K=codetracer)

## Publishing a product release

There is one apt and one RPM repository for every Metacraft product,
signed with the organisation's key
(`3CA0 3287 4B65 1B0C F01D  FB67 7EAF 585F B9B5 9164`). A product builds its
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

The design is specified in metacraft-specs,
`infrastructure/package-distribution.md` §3 and §9.1.
