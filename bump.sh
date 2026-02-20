#!/usr/bin/env bash
# bump.sh — Bump FoBiS.py version, publish to GitHub and PyPI.
#
# Usage:
#   ./bump.sh (--major | --minor | --patch | <X.Y.Z>) [--no-pypi]
#
#   --major, -M     X.Y.Z → X+1.0.0
#   --minor, -m     X.Y.Z → X.Y+1.0
#   --patch, -p     X.Y.Z → X.Y.Z+1
#   <X.Y.Z>         set an explicit version
#   --no-pypi       skip the PyPI upload step

set -euo pipefail

FOBIS_CONFIG="src/main/python/fobis/FoBiSConfig.py"

die()  { echo "ERROR: $*" >&2; exit 1; }
info() { echo "==> $*"; }

usage() {
  sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'
  exit 1
}

current_version() {
  grep -oP '(?<=__version__ = ")[^"]+' "$FOBIS_CONFIG"
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

SKIP_PYPI=false
BUMP_ARG=""

for arg in "$@"; do
  case "$arg" in
    --no-pypi)              SKIP_PYPI=true ;;
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
[[ -f "$FOBIS_CONFIG" ]] || die "$FOBIS_CONFIG not found — run from the repo root"
command -v pyb   >/dev/null || die "'pyb' not found (install: pipx install pybuilder)"
[[ "$SKIP_PYPI" == true ]] || \
  command -v twine >/dev/null || die "'twine' not found (install: pipx install twine)"

CURRENT_BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null || true)
[[ "$CURRENT_BRANCH" == "develop" ]] \
  || die "must be on 'develop' branch (currently on '$CURRENT_BRANCH')"
[[ -z "$(git status --porcelain)" ]] \
  || die "working tree is not clean — commit or stash changes first"

git fetch --tags --quiet
[[ -z "$(git tag -l "v${NEW_VER}")" ]] || die "tag v${NEW_VER} already exists"

# ensure local develop and master are not behind their remotes
DEVELOP_BEHIND=$(git rev-list --count HEAD..origin/develop 2>/dev/null || echo 0)
MASTER_BEHIND=$(git rev-list --count master..origin/master 2>/dev/null || echo 0)
[[ "$DEVELOP_BEHIND" -eq 0 ]] || die "develop is ${DEVELOP_BEHIND} commit(s) behind origin/develop — run: git pull origin develop"
[[ "$MASTER_BEHIND"  -eq 0 ]] || die "master is ${MASTER_BEHIND} commit(s) behind origin/master — run: git pull origin master"

# ── confirm ───────────────────────────────────────────────────────────────────
echo "  Current version : $CUR_VER"
echo "  New version     : $NEW_VER"
echo "  PyPI upload     : $([[ "$SKIP_PYPI" == true ]] && echo no || echo yes)"
echo
read -r -p "Proceed? [y/N] " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }

# ── create release branch and bump version ────────────────────────────────────
RELEASE_BRANCH="release/v${NEW_VER}"
# build.py sanitises the branch name: strips feature/ hotfix/ and replaces / with -
# release/v3.2.0 → release-v3.2.0 → dir release/FoBiS-release-v3.2.0
DIST_DIR="release/FoBiS-release-v${NEW_VER}"

info "Creating branch $RELEASE_BRANCH"
git checkout -b "$RELEASE_BRANCH"

info "Bumping version in $FOBIS_CONFIG ($CUR_VER → $NEW_VER)"
sed -i "s/__version__ = \"${CUR_VER}\"/__version__ = \"${NEW_VER}\"/" "$FOBIS_CONFIG"
git add "$FOBIS_CONFIG"
git commit -m "chore: bump version to v${NEW_VER}"

# ── build and test ────────────────────────────────────────────────────────────
info "Running pyb (analyze + build + test)"
pyb

# ── merge to master, tag, push to GitHub ─────────────────────────────────────
info "Merging to master and tagging v${NEW_VER}"
git checkout master
git pull origin master --ff-only
git merge --no-ff "$RELEASE_BRANCH" -m "Merge branch '${RELEASE_BRANCH}'"
git tag -a "v${NEW_VER}" -m "Release v${NEW_VER}"

info "Pushing master + tag to origin"
git push origin master
git push origin "v${NEW_VER}"

# ── merge back to develop, push ───────────────────────────────────────────────
info "Merging master back to develop"
git checkout develop
git merge --no-ff master -m "Merge branch 'master' into develop"
git push origin develop

# ── remove local release branch ───────────────────────────────────────────────
git branch -d "$RELEASE_BRANCH"

# ── upload to PyPI ────────────────────────────────────────────────────────────
if [[ "$SKIP_PYPI" == false ]]; then
  info "Building sdist and uploading to PyPI from $DIST_DIR"
  (
    cd "$DIST_DIR"
    python setup.py sdist
    # PyPI now requires normalized filenames (PEP 625): FoBiS.py-X.Y.Z → fobis_py-X.Y.Z
    mv dist/FoBiS.py-${NEW_VER}.tar.gz dist/fobis_py-${NEW_VER}.tar.gz
    twine upload dist/fobis_py-${NEW_VER}.tar.gz
  )
fi

info "Done — v${NEW_VER} released"
