#!/usr/bin/env bash
# make_gifs.sh — generate all FoBiS demo GIFs using VHS
#
# Install VHS: https://github.com/charmbracelet/vhs#installation
# Prerequisites: gfortran must be in PATH (and git; the ecosystem tapes also need git-cliff).
# 18_packages reads the public fortran-index and the packages' sources on GitHub (network).
# The *_llm_* tapes need an LLM directory with the runtime and coder-7b already installed
# (fobis llm runtime install && fobis llm pull coder-7b, or FOBIS_LLM_DIR pointing to one).
# GIF_LLM_CPU=1 records them with the CPU runtime and no GPU at all (GIF_LLM_THREADS threads, default 6), for a
# machine whose GPUs are busy: e.g.  GIF_LLM_CPU=1 bash make_gifs.sh 13
# GIF_LLM_URL=http://HOST:PORT records them with a llama-server already running elsewhere (e.g. on a GPU node reached
# through an ssh tunnel), as an OpenAI-compatible provider; its key in the variable GIF_LLM_KEY_ENV names (default
# FOBIS_GIF_LLM_KEY). Nothing is started or stopped then.
# Tapes 14-16 start from the AI tutorial's project as its chapters leave it: GIF_STATES names a directory made by
#   python scripts/docs_examples.py --check --track 6-ai --keep DIR
# The tapes run the `fobis` found on PATH: to record unreleased features, put the dev one first,
# e.g.  PATH="$(realpath ../.venv/bin):$PATH" bash make_gifs.sh 09 10 11  (absolute: tapes cd elsewhere)
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

# work dirs are made under one root: _make_work_dir runs in a $(...) subshell, which cannot add to _cleanup_dirs
_WORK_ROOT=$(mktemp -d)
_cleanup_dirs=()
trap 'rm -rf "$_TMPBIN" "$_WORK_ROOT" "${_cleanup_dirs[@]}"' EXIT

_make_work_dir() {
    local src="$1"
    local work_dir
    work_dir=$(mktemp -d -p "$_WORK_ROOT")
    cp -r "$src/." "$work_dir/"
    echo "$work_dir"
}

# the AI tutorial's project after chapter $1 of track 6-ai, made ready for tape $2
_ai_work_dir() {
    local state="${GIF_STATES:-}/states/6-ai/$1" chapter="$SCRIPT_DIR/examples/tutorial/6-ai"
    if [[ ! -d "$state" ]]; then
        echo "  [error] $2 needs GIF_STATES: python scripts/docs_examples.py --check --track 6-ai --keep DIR" >&2
        return 1
    fi
    local work_dir
    work_dir=$(_make_work_dir "$state")
    (
        cd "$work_dir"
        export GIT_AUTHOR_NAME=Demo GIT_AUTHOR_EMAIL=demo@example.org GIT_COMMITTER_NAME=Demo GIT_COMMITTER_EMAIL=demo@example.org
        git config commit.gpgsign false
        git reset -q --hard
        case "$2" in
            14_llm_review) cp "$chapter/06-review/racy/sweep.F90" src/sweep.F90 ;;
            16_llm_merge)
                git checkout -qb midpoint && git apply "$chapter/08-merge/topic.patch"
                git commit -qam "test: midpoint is exact on a line too"
                git checkout -q master && git apply "$chapter/08-merge/master.patch"
                git commit -qam "test: a tolerance of a few ulps, for -O3 builds" ;;
        esac
        fobis test --quiet >/dev/null 2>&1 || true  # the modules built, off camera
    ) >&2
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
    elif [[ "$name" == "17_doctests" || "$name" == "18_packages" ]]; then
        # quad, the tutorial's project, with the doctests of its tests chapter
        work_dir=$(_make_work_dir "$SCRIPT_DIR/examples/tutorial/1-first-steps/01-first-build/files")
        cp -r "$SCRIPT_DIR/examples/tutorial/1-first-steps/04-tests/files/." "$work_dir/"
    elif [[ "$name" == "13_llm_explain" ]]; then
        # quad, the tutorial's project, as its first chapter starts
        work_dir=$(_make_work_dir "$SCRIPT_DIR/examples/tutorial/1-first-steps/01-first-build/files")
    elif [[ "$name" == 14_llm_review ]]; then
        work_dir=$(_ai_work_dir 05 "$name")
    elif [[ "$name" == 15_llm_testgen ]]; then
        work_dir=$(_ai_work_dir 04 "$name")
    elif [[ "$name" == 16_llm_merge ]]; then
        work_dir=$(_ai_work_dir 07 "$name")
    elif [[ "$name" == *_ecosystem_* ]]; then
        # a fresh demo ecosystem (three git repos with local remotes) for every tape
        work_dir=$(mktemp -d)
        _cleanup_dirs+=("$work_dir")
        bash "$SCRIPT_DIR/demo/ecosystem-demo/setup.sh" "$work_dir" </dev/null >/dev/null
    else
        work_dir=$(_make_work_dir "$SCRIPT_DIR/demo")
    fi

    if [[ "$name" == *_llm_* ]]; then
        # the managed provider with coder-7b, whatever the recorder's own [llm] settings are
        local xdg
        xdg=$(mktemp -d)
        _cleanup_dirs+=("$xdg")
        mkdir -p "$xdg/fobis"
        printf '[llm]\nprovider = managed\nmodel = coder-7b\n' > "$xdg/fobis/config.ini"
        local gpus="${CUDA_VISIBLE_DEVICES-unset}"
        if [[ -n "${GIF_LLM_URL:-}" ]]; then
            printf '[llm]\nprovider = openai\nurl = %s\nmodel = coder-7b\napi_key_env = %s\n' \
                "$GIF_LLM_URL" "${GIF_LLM_KEY_ENV:-FOBIS_GIF_LLM_KEY}" > "$xdg/fobis/config.ini"
            FOBIS_DEMO_DIR="$work_dir" XDG_CONFIG_HOME="$xdg" vhs "$tape"
            return
        fi
        if [[ "${GIF_LLM_CPU:-0}" == 1 ]]; then
            printf 'runtime_variant = cpu\nn_gpu_layers = 0\nthreads = %s\n' "${GIF_LLM_THREADS:-6}" >> "$xdg/fobis/config.ini"
            gpus=""
        fi
        # a short path for the recording: the work dir links to the recorder's LLM directory
        ln -s "${FOBIS_LLM_DIR:-$HOME/.fobis/llm}" "$xdg/llm"
        local status=0
        if [[ "$gpus" == unset ]]; then
            FOBIS_DEMO_DIR="$work_dir" XDG_CONFIG_HOME="$xdg" FOBIS_LLM_DIR="$xdg/llm" vhs "$tape" || status=$?
        else
            CUDA_VISIBLE_DEVICES="$gpus" FOBIS_DEMO_DIR="$work_dir" XDG_CONFIG_HOME="$xdg" FOBIS_LLM_DIR="$xdg/llm" \
                vhs "$tape" || status=$?
        fi
        # a tape may start a persistent server (fobis llm serve start): never leave it running
        XDG_CONFIG_HOME="$xdg" FOBIS_LLM_DIR="$xdg/llm" fobis llm serve stop >/dev/null 2>&1 || true
        return "$status"
    fi

    if [[ "$name" == "18_packages" ]]; then
        # a throwaway user configuration and index cache: the tape registers the public fortran-index (network)
        local xdg
        xdg=$(mktemp -d)
        _cleanup_dirs+=("$xdg")
        FOBIS_DEMO_DIR="$work_dir" XDG_CONFIG_HOME="$xdg" FOBIS_INDEX_DIR="$xdg/indexes" vhs "$tape"
        return
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
