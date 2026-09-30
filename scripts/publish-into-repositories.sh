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
# Rebuild from what is published plus what is new, feeding reprepro only the
# NEWEST version of each package. A suite carries one version per package,
# and reprepro refuses to include an older version after a newer one, so
# the pool's older files (the live pool keeps every codetracer version) are
# left where they are, unreferenced, and never re-included. A deb present
# in both sets is the same bytes (checked above).
existing_debs=("$deb_dir"/pool/*/*/*/*.deb)
newest_debs=()
while IFS=$'\t' read -r _name _path; do
  newest_debs+=("$_path")
done < <(
  for deb in "${existing_debs[@]}" "${new_debs[@]}"; do
    printf '%s\t%s\t%s\n' "$(dpkg-deb -f "$deb" Package)" "$(dpkg-deb -f "$deb" Version)" "$deb"
  done | sort -t$'\t' -k1,1 -k2,2V | awk -F'\t' '{last[$1]=$3} END {for (n in last) print n "\t" last[n]}'
)
for deb in "${newest_debs[@]}"; do
  reprepro -b "$work" --keepunreferencedfiles includedeb stable "$deb"
done
if [ ${#existing_debs[@]} -gt 0 ] || [ ${#new_debs[@]} -gt 0 ]; then
  rm -rf "$deb_dir/dists"
  cp -r "$work/dists" "$deb_dir/dists"
  mkdir -p "$deb_dir/pool"
  cp -rn "$work/pool/." "$deb_dir/pool/"
fi

# Every PACKAGE in the pool must be in the index: that is the property
# earlier publishers lacked (each rebuilt the index from its own run and
# dropped the other products). Compared by package NAME, not by file: a
# suite carries one version of each package, so older versions stay in the
# pool unreferenced (the live pool holds five codetracer versions) and the
# index lists only the newest. Also require the index to carry the newest
# pooled version of each name.
# name<TAB>version of every pooled .deb, and of every index entry.
pool_nv="$(find "$deb_dir/pool" -name '*.deb' | while read -r f; do printf '%s\t%s\n' "$(dpkg-deb -f "$f" Package)" "$(dpkg-deb -f "$f" Version)"; done)"
index_nv="$(zcat "$deb_dir"/dists/stable/main/binary-*/Packages.gz 2>/dev/null | awk '/^Package: /{n=$2} /^Version: /{print n "\t" $2}')"
pool_names="$(printf '%s\n' "$pool_nv" | cut -f1 | sort -u)"
index_names="$(printf '%s\n' "$index_nv" | cut -f1 | sort -u)"
if [ "$pool_names" != "$index_names" ]; then
  echo "apt index is missing packages that are in the pool:" >&2
  comm -23 <(printf '%s\n' "$pool_names") <(printf '%s\n' "$index_names") >&2
  exit 1
fi
# The index must carry the newest pooled version of each package.
newest_pool="$(printf '%s\n' "$pool_nv" | sort -t"$(printf '\t')" -k1,1 -k2,2V | awk -F'\t' '{v[$1]=$2} END {for (n in v) print n "\t" v[n]}' | sort)"
newest_index="$(printf '%s\n' "$index_nv" | sort -t"$(printf '\t')" -k1,1 -k2,2V | awk -F'\t' '{v[$1]=$2} END {for (n in v) print n "\t" v[n]}' | sort)"
if [ "$newest_pool" != "$newest_index" ]; then
  echo "apt index does not carry the newest pooled version of each package:" >&2
  diff <(printf '%s\n' "$newest_pool") <(printf '%s\n' "$newest_index") >&2 || true
  exit 1
fi
echo "apt: $(printf '%s\n' "$index_names" | grep -c .) package(s) indexed at their newest versions: $(printf '%s\n' "$newest_index" | tr '\t\n' '= ')"

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
