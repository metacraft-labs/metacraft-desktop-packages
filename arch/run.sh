#!/usr/bin/env bash

if [ "$(whoami)" == "root" ]; then
  echo "You need to be a regular user to run this script!"
  exit
fi 

compile_file() {
  cd "$1" || exit
  echo -e "\x1b[32m--------------------------------\x1b[0m"
  echo -e "\x1b[32mCompiling: $1\x1b[0m"
  echo -e "\x1b[32m--------------------------------\x1b[0m"

  sed -i "s/sha256sums=(.*/sha256sums=()/g" PKGBUILD
  sha=$(makepkg -g)
  REAL_SHA=""
  for hash in "$(printf ${sha})"; do
    REAL_SHA="${REAL_SHA}'${sha}' "
  done
	    
  sed -i "s/sha256sums=()/sha256sums=(${REAL_SHA})/g" PKGBUILD
 
  makepkg -si --noconfirm || exit
  makepkg --printsrcinfo > .SRCINFO || exit

  if [ "$2" == "deploy" ]; then
    git init
    git remote add origin ssh://aur@aur.archlinux.org/"$1"
    git fetch origin
		
    git add . && git commit -m "Automatic"
    git checkout master
    git diff master main | git apply --cached
    git commit -m "Automatic update"
    git push origin HEAD:master
  fi

  cd ../ || exit

  echo -e "\x1b[32m--------------------------------\x1b[0m"
  echo -e "\x1b[32mSuccessfully compiled $1!"
  echo -e "\x1b[32m--------------------------------\x1b[0m"
}

export -f compile_file

compile_file codetracer "$1"
