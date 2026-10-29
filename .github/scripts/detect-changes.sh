#!/usr/bin/env bash
# Decide whether a change needs a new image, i.e. touches anything outside
# gitops/. Writes `app=true|false` to $GITHUB_OUTPUT (or stdout).
#
#   detect-changes.sh <base-sha> <head-sha>
#
# A commit that only edits gitops/ (an image promotion or rollback) must not
# build and publish a new image: that would trigger another promotion, and
# so on forever. Anything we can't diff reliably counts as an app change.
set -euo pipefail

base="${1:-}" head="${2:-HEAD}"
out="${GITHUB_OUTPUT:-/dev/stdout}"

if [ -z "$base" ] || [ "$base" = "0000000000000000000000000000000000000000" ] \
    || ! git cat-file -e "${base}^{commit}" 2>/dev/null; then
    echo "No usable base commit ($base); treating as an app change."
    echo "app=true" >> "$out"
    exit 0
fi

changed="$(git diff --name-only "$base" "$head")"
echo "Changed files ($base..$head):"
echo "${changed:-  (none)}" | sed 's/^/  /'

if [ -n "$changed" ] && echo "$changed" | grep -qv '^gitops/'; then
    echo "app=true" >> "$out"
else
    echo "Only gitops/ changed: no new image needed."
    echo "app=false" >> "$out"
fi
