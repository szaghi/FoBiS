#!/usr/bin/env bash
# release.sh — Bump FoBiS.py version, generate changelog, publish to GitHub.
#
# Usage:
#   ./release.sh (--major | --minor | --patch | <X.Y.Z>)
#
#   --major, -M     X.Y.Z → X+1.0.0
#   --minor, -m     X.Y.Z → X.Y+1.0
#   --patch, -p     X.Y.Z → X.Y.Z+1
#   <X.Y.Z>         set an explicit version

set -euo pipefail

FOBIS_INIT="fobis/__init__.py"

die()  { echo "ERROR: $*" >&2; exit 1; }
info() { echo "==> $*"; }

usage() {
  sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'
  exit 1
}

current_version() {
  grep -oP '(?<=__version__ = ")[^"]+' "$FOBIS_INIT"
}

bump() {
  local cur="$1" part="$2"
  local major minor patch
  IFS='.' read -r major minor patch <<< "$cur"
  case "$part" in
    major) echo "$((major + 1)).0.0" ;;
    minor) echo "${major}.$((minor + 1)).0" ;;
    patch) echo "${major}.${minor}.$((patch + 1))" ;;
  esac
}

# ── argument parsing ──────────────────────────────────────────────────────────
[[ $# -ge 1 ]] || usage

BUMP_ARG=""

for arg in "$@"; do
  case "$arg" in
    --major | -M)           BUMP_ARG=major ;;
    --minor | -m)           BUMP_ARG=minor ;;
    --patch | -p)           BUMP_ARG=patch ;;
    [0-9]*.[0-9]*.[0-9]*)  BUMP_ARG="$arg" ;;
    *) usage ;;
  esac
done

[[ -n "$BUMP_ARG" ]] || usage

CUR_VER=$(current_version)
case "$BUMP_ARG" in
  major | minor | patch) NEW_VER=$(bump "$CUR_VER" "$BUMP_ARG") ;;
  *)                     NEW_VER="$BUMP_ARG" ;;
esac

# ── pre-flight checks ─────────────────────────────────────────────────────────
[[ -f "$FOBIS_INIT" ]]          || die "$FOBIS_INIT not found — run from the repo root"
command -v git-cliff >/dev/null || die "'git-cliff' not found (install: pipx install git-cliff)"

# Resolve the build command: prefer 'python -m build', fall back to 'pyproject-build' (pipx)
if python -m build --version >/dev/null 2>&1; then
  BUILD_CMD="python -m build"
elif command -v pyproject-build >/dev/null 2>&1; then
  BUILD_CMD="pyproject-build"
else
  die "'build' not found — install it: pipx install build  OR  pip install build"
fi

CURRENT_BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null || true)
[[ "$CURRENT_BRANCH" == "master" ]] \
  || die "must be on 'master' branch (currently on '$CURRENT_BRANCH')"
[[ -z "$(git status --porcelain)" ]] \
  || die "working tree is not clean — commit or stash changes first"

git fetch --tags --quiet
[[ -z "$(git tag -l "v${NEW_VER}")" ]] || die "tag v${NEW_VER} already exists"

MASTER_BEHIND=$(git rev-list --count HEAD..origin/master 2>/dev/null || echo 0)
[[ "$MASTER_BEHIND" -eq 0 ]] || die "master is ${MASTER_BEHIND} commit(s) behind origin/master — run: git pull origin master"

# ── lint ──────────────────────────────────────────────────────────────────────
info "Running lint checks"
.venv/bin/ruff check . || die "lint failed — run 'make fmt' to fix"
.venv/bin/ruff format --check . || die "formatting check failed — run 'make fmt' to fix"

# ── confirm ───────────────────────────────────────────────────────────────────
echo "  Current version : $CUR_VER"
echo "  New version     : $NEW_VER"
echo
read -r -p "Proceed? [y/N] " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }

# ── bump version ──────────────────────────────────────────────────────────────
info "Bumping version ($CUR_VER → $NEW_VER)"
sed -i "s/__version__ = \"${CUR_VER}\"/__version__ = \"${NEW_VER}\"/" "$FOBIS_INIT"
grep -q "__version__ = \"${NEW_VER}\"" "$FOBIS_INIT" || die "version bump in $FOBIS_INIT failed"

# ── generate changelog ────────────────────────────────────────────────────────
info "Generating docs/guide/changelog.md with git-cliff"
git-cliff --tag "v${NEW_VER}" -o docs/guide/changelog.md

# ── run tests ─────────────────────────────────────────────────────────────────
info "Running test suite"
.venv/bin/pytest

# ── commit, tag ───────────────────────────────────────────────────────────────
info "Committing version bump and tagging v${NEW_VER}"
git add "$FOBIS_INIT" docs/guide/changelog.md
git commit -m "chore(release): bump version to v${NEW_VER}"
git tag -a "v${NEW_VER}" -m "Release v${NEW_VER}"

# ── build distribution ────────────────────────────────────────────────────────
info "Building distribution with $BUILD_CMD"
$BUILD_CMD

# ── push master + tag ─────────────────────────────────────────────────────────
info "Pushing master + tag to origin"
git push --follow-tags origin master

# ── PyPI upload is triggered by the tag push via CI ───────────────────────────
info "Done — v${NEW_VER} released (PyPI upload triggered by tag push via CI)"
