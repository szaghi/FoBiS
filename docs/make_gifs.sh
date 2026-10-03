#!/usr/bin/env bash
# make_gifs.sh — generate all FoBiS demo GIFs using VHS
#
# Install VHS: https://github.com/charmbracelet/vhs#installation
# Prerequisites: gfortran must be in PATH (and git; the ecosystem tapes also need git-cliff).
# The tapes run the `fobis` found on PATH: to record unreleased features, put the dev one first,
# e.g.  PATH=../.venv/bin:$PATH bash make_gifs.sh 09 10 11
#
# Usage:
#   bash make_gifs.sh           — generate all GIFs
#   bash make_gifs.sh 01        — generate only 01_basic_build
#   bash make_gifs.sh 01 05 08  — generate a selection

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

mkdir -p public/gifs

# ── force color output in VHS sessions ───────────────────────────────────────
export TERM=xterm-256color
export COLORTERM=truecolor
export CLICOLOR=1
export CLICOLOR_FORCE=1
export FORCE_COLOR=1

# ── slowout: write stdin line-by-line with a configurable delay ───────────────
# Injected into a temp bin dir on PATH so VHS tape sessions can use it as a
# plain command: e.g.  fobis build | slowout .2
_TMPBIN=$(mktemp -d)
cat > "$_TMPBIN/slowout" <<'SLOWOUT'
#!/usr/bin/env bash
delay=${1:-.1}
while IFS= read -r line; do
  printf '%s\n' "$line"
  sleep "$delay"
done
SLOWOUT
chmod +x "$_TMPBIN/slowout"
export PATH="$_TMPBIN:$PATH"

_cleanup_dirs=()
trap 'rm -rf "$_TMPBIN" "${_cleanup_dirs[@]}"' EXIT

_make_work_dir() {
    local src="$1"
    local work_dir
    work_dir=$(mktemp -d)
    _cleanup_dirs+=("$work_dir")
    cp -r "$src/." "$work_dir/"
    echo "$work_dir"
}

run_tape() {
    local tape="$1"
    local name
    name=$(basename "$tape" .tape)

    echo "  vhs $tape"

    local work_dir
    if [[ "$name" == "07_fetch" ]]; then
        work_dir=$(_make_work_dir "$SCRIPT_DIR/demo/fetch-demo")
    elif [[ "$name" == *_ecosystem_* ]]; then
        # a fresh demo ecosystem (three git repos with local remotes) for every tape
        work_dir=$(mktemp -d)
        _cleanup_dirs+=("$work_dir")
        bash "$SCRIPT_DIR/demo/ecosystem-demo/setup.sh" "$work_dir" </dev/null >/dev/null
    else
        work_dir=$(_make_work_dir "$SCRIPT_DIR/demo")
    fi

    FOBIS_DEMO_DIR="$work_dir" vhs "$tape"
}

echo ""
echo "Generating GIFs..."
echo ""

if [[ $# -eq 0 ]]; then
    for tape in public/gifs/tapes/*.tape; do
        run_tape "$tape"
    done
else
    for id in "$@"; do
        if [[ -f "$id" ]]; then
            run_tape "$id"
        else
            match=$(compgen -G "public/gifs/tapes/${id}*.tape" 2>/dev/null | head -1 || true)
            if [[ -z "$match" ]]; then
                echo "  [error] no tape found matching '${id}'" >&2
            else
                run_tape "$match"
            fi
        fi
    done
fi

echo ""
echo "Done. GIFs written to public/gifs/"
