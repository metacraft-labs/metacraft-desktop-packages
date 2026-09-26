#!/usr/bin/env bash
# Add a product release's packages to the organisation's apt and RPM
# repositories, and regenerate and sign the indices over everything in them.
#
#   publish-into-repositories.sh --incoming DIR --deb-dir DIR --rpm-dir DIR \
#       --key-id FPR
#
# DIR arguments are local trees. --deb-dir and --rpm-dir hold the CURRENT
# contents of the published repositories, as synced down from their buckets:
# `pool/` for apt and `RPMS/` for RPM. Those package files are the source of
# truth. The indices are regenerated from them on every run, so a publish only
# ever adds packages. reprepro's own database is not trusted across runs,
# because earlier publishers never kept it; it is rebuilt here from `pool/`.
#
# --incoming holds the new *.deb and *.rpm files (already checksum-verified by
# the caller). The signing key must already be in $GNUPGHOME.
#
# A version already in the repository with DIFFERENT bytes is an error: a
# published version is never overwritten (package-distribution.md §9). Byte-
# identical re-publication is a no-op, so a retried publish is safe.
#
# It does not write the public key. That is keys/ in this repository,
# committed once and uploaded verbatim, so its bytes never change and
# installers can pin its SHA-256.
#
# After it runs, the trees are ready to upload. Upload packages before indices
# (`pool/` then `dists/`, `RPMS/` then `repodata/`) so no index ever names a
# file the bucket does not have yet.
set -euo pipefail

incoming='' deb_dir='' rpm_dir='' key_id=''
while [ $# -gt 0 ]; do
  case "$1" in
    --incoming) incoming="$2"; shift 2 ;;
    --deb-dir)  deb_dir="$2"; shift 2 ;;
    --rpm-dir)  rpm_dir="$2"; shift 2 ;;
    --key-id)   key_id="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
for v in incoming deb_dir rpm_dir key_id; do
  [ -n "${!v}" ] || { echo "--${v//_/-} is required" >&2; exit 2; }
done
[ -n "${GNUPGHOME:-}" ] || { echo "GNUPGHOME must point at a prepared home, never ~/.gnupg" >&2; exit 2; }
gpg --batch --list-secret-keys "$key_id" >/dev/null

here="$(cd "$(dirname "$0")/.." && pwd)"
shopt -s nullglob

# ── apt ──────────────────────────────────────────────────────────────────────
new_debs=("$incoming"/*.deb)
for deb in "${new_debs[@]}"; do
  pkg="$(dpkg-deb -f "$deb" Package)"
  dest="$deb_dir/pool/main/${pkg:0:1}/$pkg/$(basename "$deb")"
  if [ -f "$dest" ]; then
    cmp -s "$deb" "$dest" || { echo "refusing to overwrite published $dest with different bytes" >&2; exit 1; }
  fi
done

# reprepro works in a scratch base; only dists/ and pool/ are copied back.
work="$(mktemp -d)"; trap 'rm -rf "$work"' EXIT
mkdir -p "$work/conf"
sed "s/^#\?SignWith:.*/SignWith: $key_id/" "$here/debian/conf/distributions" > "$work/conf/distributions"
echo verbose > "$work/conf/options"
# Rebuild from what is published, then add what is new. A deb present in both
# is the same bytes (checked above), and reprepro accepts it once.
existing_debs=("$deb_dir"/pool/*/*/*/*.deb)
for deb in "${existing_debs[@]}" "${new_debs[@]}"; do
  reprepro -b "$work" --keepunreferencedfiles includedeb stable "$deb"
done
if [ ${#existing_debs[@]} -gt 0 ] || [ ${#new_debs[@]} -gt 0 ]; then
  rm -rf "$deb_dir/dists"
  cp -r "$work/dists" "$deb_dir/dists"
  mkdir -p "$deb_dir/pool"
  cp -rn "$work/pool/." "$deb_dir/pool/"
fi

# The index must list every package that is in the pool: that is the
# property earlier publishers lacked.
listed="$(zcat "$deb_dir"/dists/stable/main/binary-*/Packages.gz 2>/dev/null | grep -c '^Filename:' || true)"
pooled="$(find "$deb_dir/pool" -name '*.deb' | wc -l)"
[ "$listed" -eq "$pooled" ] || { echo "apt index lists $listed packages but pool holds $pooled" >&2; exit 1; }
echo "apt: $listed package(s) indexed"

# ── RPM ──────────────────────────────────────────────────────────────────────
new_rpms=("$incoming"/*.rpm)
mkdir -p "$rpm_dir/RPMS"
mkdir -p "$work/home" "$work/rpmdb"
# rpm -qp only reads the package, but still opens a database; give it an
# empty one rather than the host's (a CI runner may have none at all).
rpmq() { rpm --dbpath "$work/rpmdb" --nosignature "$@"; }
cat > "$work/home/.rpmmacros" <<MACROS
%_gpg_name $key_id
%__gpg $(command -v gpg)
%_dbpath $work/rpmdb
MACROS
for rpm in "${new_rpms[@]}"; do
  arch="$(rpmq -qp --qf '%{ARCH}' "$rpm")"
  mkdir -p "$rpm_dir/RPMS/$arch"
  dest="$rpm_dir/RPMS/$arch/$(basename "$rpm")"
  signed="$work/$(basename "$rpm")"
  cp "$rpm" "$signed"
  HOME="$work/home" rpmsign --addsign "$signed" >/dev/null
  if [ -f "$dest" ]; then
    # Signing is not deterministic, so compare the payload digest, not bytes.
    [ "$(rpmq -qp --qf '%{PAYLOADDIGEST}' "$dest")" = "$(rpmq -qp --qf '%{PAYLOADDIGEST}' "$signed")" ] \
      || { echo "refusing to overwrite published $dest with a different payload" >&2; exit 1; }
    continue
  fi
  mv "$signed" "$dest"
done
createrepo_c --quiet "$rpm_dir"
rm -f "$rpm_dir/repodata/repomd.xml.asc"
gpg --batch --yes --detach-sign --armor -u "$key_id" "$rpm_dir/repodata/repomd.xml"
echo "rpm: $(find "$rpm_dir/RPMS" -name '*.rpm' | wc -l) package(s) indexed"
