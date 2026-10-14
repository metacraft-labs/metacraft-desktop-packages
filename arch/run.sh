#!/usr/bin/env bash
# Build (and optionally publish to the AUR) the Arch packages in this directory.
#
#   bash run.sh [deploy] [package...]
#
# With no package names every package directory is processed. `deploy` pushes
# the package's PKGBUILD, .SRCINFO and .gitignore to the matching AUR repository
# after a successful `makepkg -si`.
set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then
  echo "You need to be a regular user to run this script!" >&2
  exit 1
fi

mode=build
if [ "${1:-}" == "deploy" ]; then
  mode=deploy
  shift
fi

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

compile_file() {
  local pkg="$1"
  cd "$here/$pkg"
  echo -e "\x1b[32m--------------------------------\x1b[0m"
  echo -e "\x1b[32mCompiling: $pkg\x1b[0m"
  echo -e "\x1b[32m--------------------------------\x1b[0m"

  if [ "$mode" == "deploy" ]; then
    # Publish exactly the reviewed checksums: makepkg verifies them below.
    :
  else
    updpkgsums
  fi
  makepkg -si --noconfirm
  makepkg --printsrcinfo > .SRCINFO

  if [ "$mode" == "deploy" ]; then
    local aur
    aur="$(mktemp -d)"
    git clone "ssh://aur@aur.archlinux.org/$pkg.git" "$aur"
    git -C "$aur" checkout -B master
    cp PKGBUILD .SRCINFO "$aur"/
    if [ -f .gitignore ]; then cp .gitignore "$aur"/; fi
    git -C "$aur" add PKGBUILD .SRCINFO
    if [ -f "$aur/.gitignore" ]; then git -C "$aur" add .gitignore; fi
    if git -C "$aur" diff --cached --quiet; then
      echo "AUR $pkg is already up to date"
    else
      version="$(sed -n 's/^\tpkgver = //p' .SRCINFO)-$(sed -n 's/^\tpkgrel = //p' .SRCINFO)"
      git -C "$aur" commit -m "Update to $version"
      git -C "$aur" push origin master
    fi
    rm -rf "$aur"
  fi

  echo -e "\x1b[32m--------------------------------\x1b[0m"
  echo -e "\x1b[32mSuccessfully compiled $pkg!\x1b[0m"
  echo -e "\x1b[32m--------------------------------\x1b[0m"
}

if [ "$#" -eq 0 ]; then
  set -- codetracer codetracer-rr-backend
fi

for pkg in "$@"; do
  compile_file "$pkg"
done
