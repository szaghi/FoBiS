#!/usr/bin/env bash
# install.sh — repo-agnostic install script
set -euo pipefail

PREFIX="${1:-/usr/local}"
FoBiS.py install --prefix "$PREFIX"
echo "Installed to $PREFIX"
