#!/usr/bin/env bash
# Download a release binary, check it against a pinned SHA-256, install it.
#
#   install-tool.sh <name> <url> <sha256> [file-inside-tar.gz]
#
# The checksum is pinned in the workflow, so a changed or replaced release
# asset fails the build instead of running.
set -euo pipefail

name="$1" url="$2" sha256="$3" member="${4:-}"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

curl -fsSL --retry 3 -o "$tmp/download" "$url"
echo "${sha256}  $tmp/download" | sha256sum --check --strict

if [ -n "$member" ]; then
    tar -xzf "$tmp/download" -C "$tmp" "$member"
    src="$tmp/$member"
else
    src="$tmp/download"
fi
sudo install -m 0755 "$src" "/usr/local/bin/$name"
echo "Installed $name from $url"
