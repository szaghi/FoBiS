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
TRUNK="master"

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

# ── stage tracking + recovery trap ───────────────────────────────────────────
STAGE="preflight"
NEW_VER=""

on_error() {
  echo ""
  echo "================================================================"
  echo "  release.sh FAILED at stage: $STAGE"
  echo "================================================================"
  case "$STAGE" in
    preflight | lint | confirm)
      echo "  Nothing was changed. Fix the issue above and re-run."
      ;;
    bumped)
      echo "  Version bump and changelog were modified locally but not committed."
      echo "  To discard and start over:"
      echo "    git checkout -- $FOBIS_INIT docs/guide/changelog.md"
      ;;
    committed)
      echo "  Version bump was committed but not tagged/pushed. To resume:"
      echo "    git tag -a v${NEW_VER} -m \"Release v${NEW_VER}\""
      echo "    git push origin ${TRUNK} --follow-tags"
      ;;
    tagged)
      echo "  Tag v${NEW_VER} was created locally but not pushed. To resume:"
      echo "    git push origin ${TRUNK} --follow-tags"
      ;;
  esac
  echo "================================================================"
}

trap 'on_error' ERR

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
STAGE="preflight"
[[ -f "$FOBIS_INIT" ]]          || die "$FOBIS_INIT not found — run from the repo root"
command -v git-cliff >/dev/null || die "'git-cliff' not found (install: pipx install git-cliff)"

CURRENT_BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null || true)
[[ "$CURRENT_BRANCH" == "$TRUNK" ]] \
  || die "must be on '$TRUNK' branch (currently on '$CURRENT_BRANCH')"
[[ -z "$(git status --porcelain)" ]] \
  || die "working tree is not clean — commit or stash changes first"

git fetch --tags --quiet
[[ -z "$(git tag -l "v${NEW_VER}")" ]] || die "tag v${NEW_VER} already exists"

BEHIND=$(git rev-list --count HEAD..origin/${TRUNK} 2>/dev/null || echo 0)
[[ "$BEHIND" -eq 0 ]] \
  || die "${TRUNK} is ${BEHIND} commit(s) behind origin/${TRUNK} — run: git pull origin ${TRUNK}"

# ── lint / format check ───────────────────────────────────────────────────────
STAGE="lint"
info "Running ruff lint + format check"
.venv/bin/ruff check fobis/ tests/        || die "lint failed — run 'make fmt' to fix, then retry"
.venv/bin/ruff format --check fobis/ tests/ || die "format check failed — run 'make fmt' to fix, then retry"

# ── confirm ───────────────────────────────────────────────────────────────────
STAGE="confirm"
echo "  Current version : $CUR_VER"
echo "  New version     : $NEW_VER"
echo
read -r -p "Proceed? [y/N] " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }

# ── bump version + changelog ──────────────────────────────────────────────────
STAGE="bumped"
info "Bumping version ($CUR_VER → $NEW_VER)"
sed -i "s/__version__ = \"${CUR_VER}\"/__version__ = \"${NEW_VER}\"/" "$FOBIS_INIT"
grep -q "__version__ = \"${NEW_VER}\"" "$FOBIS_INIT" || die "version bump in $FOBIS_INIT failed"

info "Generating docs/guide/changelog.md with git-cliff"
mkdir -p docs/guide
git-cliff --tag "v${NEW_VER}" -o docs/guide/changelog.md

info "Running test suite"
.venv/bin/pytest

# ── commit, tag, push ─────────────────────────────────────────────────────────
STAGE="committed"
git add "$FOBIS_INIT" docs/guide/changelog.md
git commit -m "chore(release): bump version to v${NEW_VER}"

STAGE="tagged"
git tag -a "v${NEW_VER}" -m "Release v${NEW_VER}"

info "Pushing ${TRUNK} + tag to origin (CI will publish to PyPI)"
git push origin "${TRUNK}" --follow-tags

info "Done — v${NEW_VER} released"
