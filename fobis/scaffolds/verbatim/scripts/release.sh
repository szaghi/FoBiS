#!/usr/bin/env bash
# release.sh — bump version in the project VERSION file
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <new-version>" >&2
  exit 1
fi

VERSION_FILE="$(git rev-parse --show-toplevel)/VERSION"
if [[ ! -f "$VERSION_FILE" ]]; then
  echo "Error: VERSION file not found at $VERSION_FILE" >&2
  exit 1
fi

CURRENT=$(cat "$VERSION_FILE" | tr -d '[:space:]')
echo "$1" > "$VERSION_FILE"
echo "Bumped version: $CURRENT → $1"
