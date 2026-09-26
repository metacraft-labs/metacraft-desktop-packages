#!/usr/bin/env bash
# Import the repository signing key into $GNUPGHOME and preset its passphrase
# in gpg-agent, so reprepro (through gpgme), rpmsign and gpg all sign
# unattended. Reads the armoured key from $SIGNING_KEY and the passphrase
# (possibly empty) from $SIGNING_KEY_PASS. Prints the primary fingerprint.
set -euo pipefail
: "${GNUPGHOME:?GNUPGHOME must point at a fresh home, never ~/.gnupg}"
: "${SIGNING_KEY:?SIGNING_KEY is empty}"
install -d -m 700 "$GNUPGHOME"
echo allow-preset-passphrase > "$GNUPGHOME/gpg-agent.conf"
gpgconf --kill gpg-agent 2>/dev/null || true
printf '%s' "$SIGNING_KEY" \
  | gpg --batch --quiet --pinentry-mode loopback --passphrase "${SIGNING_KEY_PASS:-}" --import
if [ -n "${SIGNING_KEY_PASS:-}" ]; then
  hex="$(printf '%s' "$SIGNING_KEY_PASS" | od -An -tx1 | tr -d ' \n' | tr a-f A-F)"
  gpg --batch --with-colons --with-keygrip --list-secret-keys \
    | awk -F: '$1=="grp"{print $10}' \
    | while read -r grip; do
        gpg-connect-agent "PRESET_PASSPHRASE $grip -1 $hex" /bye >/dev/null
      done
fi
gpg --batch --with-colons --list-secret-keys | awk -F: '$1=="fpr"{print $10; exit}'
