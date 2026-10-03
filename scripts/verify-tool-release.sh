#!/usr/bin/env bash
# Verify public metadata and install in clean distributions. The producer's
# release workflow separately requires native execution on every declared architecture.
set -euo pipefail
product="${1:?product required}"
version="${2:?version required}"
case "$product" in
  gosti|io-mon) package="metacraft-$product" ;;
  runquota) package=runquota ;;
  *) echo 'unsupported product' >&2; exit 1 ;;
esac
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || exit 1
# Explicit release scope: Linux ARM64 remains deferred for 0.1.0 and 0.1.1,
# plus Gosti 0.1.2 because its 0.1.1 is already published (shared release
# specification, 2026-10-03). Do not infer support from uploaded assets.
# Every other product/version pair requires both architectures.
deb_architectures='amd64 arm64'
rpm_architectures='x86_64 aarch64'
if [ "$version" = 0.1.0 ] || [ "$version" = 0.1.1 ] || [ "$product:$version" = gosti:0.1.2 ]; then
  deb_architectures=amd64
  rpm_architectures=x86_64
fi
[ "$(uname -m)" = x86_64 ] || { echo 'installation gate requires native x86_64' >&2; exit 1; }
work="$(mktemp -d "$PWD/repository-check.XXXXXX")"
trap 'rm -rf "$work"' EXIT
mkdir -p test-logs
cp keys/metacraft-labs-archive-keyring.{gpg,asc} "$work/"
cp scripts/verify-io-mon-install.py "$work/"
gh release download "v$version" -R "metacraft-labs/$product" -D "$work" \
  -p SHA256SUMS -p "$product-$version-linux-x86_64.tar.gz" -p '*.deb' -p '*.rpm'
(cd "$work" && sha256sum --check --ignore-missing SHA256SUMS)
cat > "$work/check-payload.py" <<'PY'
import hashlib, os, pathlib, tarfile
product, version = os.environ['PRODUCT'], os.environ['VERSION']
stem = f'{product}-{version}-linux-x86_64'
count = 0
with tarfile.open(f'/payload/{stem}.tar.gz') as archive:
    for item in archive:
        relative = pathlib.PurePosixPath(item.name).relative_to(stem)
        assert '..' not in relative.parts
        installed = pathlib.Path('/usr/lib') / product / relative
        if item.isfile():
            expected = hashlib.sha256(archive.extractfile(item).read()).digest()
            assert hashlib.sha256(installed.read_bytes()).digest() == expected, str(installed)
            count += 1
        elif item.issym():
            assert installed.is_symlink() and os.readlink(installed) == item.linkname, str(installed)
assert count > 0
print(f'{product} {version}: all {count} installed payload files match the release archive')
PY
for image in debian:11 ubuntu:24.04 almalinux:9; do
  docker pull "$image"
  docker image inspect --format '{{index .RepoDigests 0}}' "$image" >> test-logs/repository-images.txt
  log="test-logs/repository-${product}-${image//:/-}.log"
  # The container expands these variables, after Docker supplies its environment.
  # shellcheck disable=SC2016
  if ! docker run --rm -v "$work:/payload:ro" \
    -e PRODUCT="$product" -e PACKAGE="$package" -e VERSION="$version" \
    -e DEB_ARCHITECTURES="$deb_architectures" -e RPM_ARCHITECTURES="$rpm_architectures" \
    "$image" bash -euo pipefail -c '
      mkdir -p /tmp/packages
      cd /tmp/packages
      if command -v apt-get >/dev/null; then
        if ( . /etc/os-release; [ "$ID:$VERSION_ID" = debian:11 ] ); then
          # Bullseye LTS ended on 2026-08-31. Its live security index names
          # deleted files; retain this compatibility target with signed,
          # fixed snapshot prerequisites. Only those historical sources
          # ignore Valid-Until. The Metacraft feed below remains live.
          rm -f /etc/apt/sources.list.d/debian.sources
          printf "%s\n" \
            "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian/20260831T000000Z/ bullseye main" \
            "deb [check-valid-until=no] http://snapshot.debian.org/archive/debian-security/20260831T000000Z/ bullseye-security main" \
            > /etc/apt/sources.list
          cat /etc/apt/sources.list
        fi
        apt-get update -qq
        apt-get install -y --no-install-recommends ca-certificates python3 libstdc++6
        cp /payload/metacraft-labs-archive-keyring.gpg /usr/share/keyrings/metacraft-labs.gpg
        chmod 644 /usr/share/keyrings/metacraft-labs.gpg
        if [[ " $DEB_ARCHITECTURES " == *" arm64 "* ]]; then dpkg --add-architecture arm64; fi
        echo "deb [signed-by=/usr/share/keyrings/metacraft-labs.gpg] https://deb.metacraft-labs.com stable main" > /etc/apt/sources.list.d/metacraft-labs.list
        # Host distro ARM mirrors may differ (Ubuntu uses ports). Only
        # refresh our dual-architecture source; retain the base amd64 indices.
        apt-get update -o Dir::Etc::sourcelist=/etc/apt/sources.list.d/metacraft-labs.list \
          -o Dir::Etc::sourceparts=- -o APT::Get::List-Cleanup=0
        for arch in $DEB_ARCHITECTURES; do
          apt-get download "$PACKAGE:$arch=$VERSION-1"
          deb="${PACKAGE}_${VERSION}-1_${arch}.deb"
          test -s "$deb"
          test "$(dpkg-deb -f "$deb" Architecture)" = "$arch"
          test "$(dpkg-deb -f "$deb" Version)" = "$VERSION-1"
          expected="$(sha256sum "/payload/$deb" | cut -d " " -f 1)"
          echo "$expected  $deb" | sha256sum -c -
        done
        apt-get install -y "$PACKAGE:amd64=$VERSION-1"
      else
        dnf install -y ca-certificates python3 libstdc++ dnf-plugins-core
        printf "[metacraft]\nname=Metacraft Labs\nbaseurl=https://rpm.metacraft-labs.com\nenabled=1\ngpgcheck=1\nrepo_gpgcheck=1\ngpgkey=file:///payload/metacraft-labs-archive-keyring.asc\n" > /etc/yum.repos.d/metacraft.repo
        rpm --import /payload/metacraft-labs-archive-keyring.asc
        for arch in $RPM_ARCHITECTURES; do
          dnf -y --forcearch="$arch" --disablerepo="*" --enablerepo=metacraft download "$PACKAGE-$VERSION-1.$arch"
          rpmfile="$PACKAGE-$VERSION-1.$arch.rpm"
          test -s "$rpmfile"
          rpmkeys --checksig "$rpmfile"
          # Signing changes RPM bytes; compare the complete payload digest.
          test "$(rpm -qp --qf "%{PAYLOADDIGEST}" "$rpmfile")" = "$(rpm -qp --nosignature --qf "%{PAYLOADDIGEST}" "/payload/$rpmfile")"
          test "$(rpm -qp --qf "%{ARCH}" "$rpmfile")" = "$arch"
        done
        dnf install -y "$PACKAGE-$VERSION-1.x86_64"
      fi
      python3 /payload/check-payload.py
      if [ "$PRODUCT" = io-mon ]; then
        python3 /payload/verify-io-mon-install.py
      else
        "/usr/bin/$PRODUCT" --help >/dev/null
      fi
    ' > "$log" 2>&1; then
    tail -100 "$log" >&2
    exit 1
  fi
  echo "Verified $product $version: $image installation and repository architectures $rpm_architectures"
done
