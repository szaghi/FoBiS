"""Run the documentation examples and regenerate every command output the pages include.

Layout::

    docs/examples/tutorial/<track>/<NN-name>/
        files/        files copied into the project before the session (the project's state at that chapter)
        session.sh    the chapter's commands (cwd: the project, $DOCS_CHAPTER: this directory), bash with the
                      helpers of PRELUDE:
                        show ID COMMAND   run COMMAND, write "$ COMMAND", its output and its exit status to ID.txt
                        quiet COMMAND     run COMMAND, output not shown; the session stops when it fails
                        needs TOOL...     the rest of the chapter needs TOOL: when it is missing, the chapter's
                                          committed outputs are kept (a chapter recorded on another machine)
        START         (first chapter of a track only) the chapter whose final state the track starts from;
                      without it, a track starts from an empty project
        PROJECT       (first chapter of a track only) the project directory's name, default "quad"
    docs/examples/output/<track>/<NN>/<ID>.txt    generated
    docs/examples/output/manifest.json            generated: the compiler that produced the outputs

Every chapter starts from the previous chapter's final state, in a scratch directory: ``$HOME/<project>`` with a
throwaway HOME, shown as ``~/<project>`` in the outputs. The environment is minimal and fixed (C locale, UTC, a git
identity and fixed commit dates, so commit hashes are reproducible); ``fobis`` is this repository's FoBiS, ``gfortran``
is ``$DOCS_FC`` (default ``gfortran-13``, the compiler of the CI, when installed). Variables named ``DOCS_*`` reach
the sessions: ``DOCS_MPI_SETUP`` is the shell code that makes ``mpif90`` and ``mpirun`` available on this machine (for
example ``source /usr/share/lmod/lmod/init/bash; module load openmpi``); without it the MPI chapters keep their outputs.

Usage::

    python docs/scripts/docs_examples.py            # regenerate docs/examples/output
    python docs/scripts/docs_examples.py --check    # regenerate in a scratch directory and compare
    python docs/scripts/docs_examples.py --track 1-first-steps

``--check`` compares byte by byte (durations, backtrace addresses, timestamps, commit hashes and scratch
directory names aside) when the compiler's major version is the recorded one; with another compiler only the
exit status of every run is compared (compiler messages and numbers are not portable across versions).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent
EXAMPLES = DOCS / "examples"
TUTORIAL = EXAMPLES / "tutorial"
OUTPUT = EXAMPLES / "output"
MANIFEST = "manifest.json"
KEPT = ".kept"  # written by `needs` when a tool is missing: the chapter's outputs are not regenerated
DEFAULT_PROJECT = "quad"
GIT_DATE = "2026-01-15T10:00:00+00:00"

PRELUDE = r"""
set -uo pipefail
show() {  # show ID COMMAND: run COMMAND, record it with its output and exit status
  local id=$1; shift
  [ -e "$DOCS_OUT/.kept" ] && return 0
  {
    printf '$ %s\n' "$*"
    bash -c "$*" 2>&1
    local status=$?
    [ "$status" -ne 0 ] && printf '[exit status %d]\n' "$status"
  } > "$DOCS_OUT/$id.txt"
  return 0
}
quiet() {  # quiet COMMAND: run COMMAND unseen; stop the chapter when it fails
  [ -e "$DOCS_OUT/.kept" ] && return 0
  local log
  log=$(bash -c "$*" 2>&1) || { printf 'docs_examples: failed: %s\n%s\n' "$*" "$log" >&2; exit 1; }
}
needs() {  # needs TOOL...: keep the committed outputs when a tool is missing
  local tool
  for tool in "$@"; do
    command -v "$tool" > /dev/null 2>&1 || { echo "$tool" > "$DOCS_OUT/.kept"; return 0; }
  done
}
"""


class ExamplesError(Exception):
    """A chapter's session failed."""


def chapters(track: str | None = None) -> list[tuple[str, Path]]:
    """Every chapter in reading order as ``(track, chapter directory)``, or the chapters of *track*."""
    if not TUTORIAL.is_dir():
        return []
    found = []
    for track_dir in sorted(p for p in TUTORIAL.iterdir() if p.is_dir()):
        if track is None or track_dir.name == track:
            found += [(track_dir.name, c) for c in sorted(p for p in track_dir.iterdir() if p.is_dir())]
    return found


def chapter_key(track: str, chapter: Path) -> str:
    """``<track>/<NN>``: the chapter's output directory, and the name a ``START`` file uses."""
    return f"{track}/{chapter.name.split('-', 1)[0]}"


def _compiler() -> str:
    wanted = os.environ.get("DOCS_FC", "gfortran-13")
    return shutil.which(wanted) or shutil.which("gfortran") or wanted


def compiler_version(fc: str) -> str:
    """First line of ``fc --version``."""
    try:
        return subprocess.run([fc, "--version"], capture_output=True, text=True, check=False).stdout.splitlines()[0]
    except (OSError, IndexError):
        return ""


def _major(version: str) -> str:
    match = re.search(r"\) (\d+)\.", version) or re.search(r"(\d+)\.\d+", version)
    return match.group(1) if match else version


def _shims(bin_dir: Path, fc: str) -> None:
    """``fobis`` running this repository's FoBiS; ``gfortran`` and ``gcov`` the chosen compiler's."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    tools = {"fobis": f'exec "{sys.executable}" -m fobis "$@"', "gfortran": f'exec "{fc}" "$@"'}
    gcov = shutil.which(Path(fc).name.replace("gfortran", "gcov"))
    if gcov:
        tools["gcov"] = f'exec "{gcov}" "$@"'
    for name, body in tools.items():
        shim = bin_dir / name
        shim.write_text(f"#!/bin/sh\n{body}\n")
        shim.chmod(0o755)


def _environment(home: Path, bin_dir: Path) -> dict[str, str]:
    path = [str(bin_dir), str(Path(sys.executable).parent), "/usr/local/bin", "/usr/bin", "/bin"]
    env = {
        "HOME": str(home),
        "PATH": os.pathsep.join(path),
        "LC_ALL": "C",
        "TZ": "UTC",
        "TERM": "dumb",
        "COLUMNS": "100",
        "TMPDIR": str(home / "tmp"),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "GIT_AUTHOR_DATE": GIT_DATE,
        "GIT_COMMITTER_DATE": GIT_DATE,
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    for name, value in os.environ.items():  # DOCS_*: machine settings a session may use (DOCS_MPI_SETUP)
        if name.startswith("DOCS_"):
            env[name] = value
    return env


def _git_config(home: Path) -> None:
    (home / ".gitconfig").write_text(
        "[user]\n\tname = Ada Fortran\n\temail = ada@example.org\n[init]\n\tdefaultBranch = master\n"
        "[color]\n\tui = never\n[advice]\n\tdetachedHead = false\n[commit]\n\tgpgsign = false\n"
    )


def run_chapter(track: str, chapter: Path, home: Path, project: Path, out: Path, env: dict[str, str]) -> bool:
    """Run one chapter in *project*, writing its outputs to *out*; False when its outputs are kept."""
    files = chapter / "files"
    if files.is_dir():
        shutil.copytree(files, project, dirs_exist_ok=True, copy_function=shutil.copy)  # fresh mtimes: an edit
    fresh = Path(tempfile.mkdtemp(prefix="out-", dir=home / "tmp"))
    session = chapter / "session.sh"
    script = PRELUDE + (session.read_text() if session.is_file() else "")
    result = subprocess.run(
        ["bash", "-c", script],
        cwd=project,
        env={**env, "DOCS_OUT": str(fresh), "DOCS_CHAPTER": str(chapter)},
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ExamplesError(f"{chapter_key(track, chapter)}: session failed\n{result.stdout}{result.stderr}")
    kept = (fresh / KEPT).exists()
    out.mkdir(parents=True, exist_ok=True)
    if not kept:  # the whole session ran: its outputs replace the chapter's
        for stale in out.glob("*.txt"):
            if not (fresh / stale.name).exists():
                stale.unlink()
    for txt in fresh.glob("*.txt"):  # a session stopped by `needs` overwrites only what ran
        text = txt.read_text(errors="replace").replace(str(home), "~")
        target = out / txt.name
        if not (target.is_file() and _normalised(target.read_text()) == _normalised(text)):  # no churn: addresses
            target.write_text(text)
    shutil.rmtree(fresh)
    return not kept


def generate(out_root: Path, track: str | None = None, keep: Path | None = None) -> dict[str, bool]:
    """Run the chapters (all, or those of *track* and the chapters it starts from), outputs under *out_root*.

    Returns ``{chapter key: regenerated}``. A chapter whose tool is missing keeps the committed outputs (copied into
    *out_root* when it is not the committed directory).
    """
    fc = _compiler()
    scratch = Path(tempfile.mkdtemp(prefix="fobis-docs-")) if keep is None else keep
    states = scratch / "states"
    bin_dir = scratch / "bin"
    by_track: dict[str, list[Path]] = {}
    for t, c in chapters():
        by_track.setdefault(t, []).append(c)
    done: dict[str, bool] = {}

    def run_track(t: str, upto: str | None = None) -> None:
        home = scratch / f"home-{t}"
        if home.exists():
            shutil.rmtree(home)
        (home / "tmp").mkdir(parents=True)
        _git_config(home)
        env = _environment(home, bin_dir)
        first = by_track[t][0]
        name = (first / "PROJECT").read_text().strip() if (first / "PROJECT").is_file() else DEFAULT_PROJECT
        project = home / name
        start = first / "START"
        if start.is_file():
            origin = start.read_text().strip()
            if not (states / origin).exists():
                run_track(origin.split("/")[0], upto=origin)
            shutil.copytree(states / origin, project, symlinks=True)
        else:
            project.mkdir()
        for c in by_track[t]:
            key = chapter_key(t, c)
            out = out_root / key
            regenerated = run_chapter(t, c, home, project, out, env)
            if not regenerated and out_root != OUTPUT and (OUTPUT / key).is_dir():
                for committed in (OUTPUT / key).glob("*.txt"):  # the runs after `needs`: the others ran
                    if not (out / committed.name).exists():
                        shutil.copy2(committed, out / committed.name)
            done[key] = regenerated
            shutil.copytree(project, states / key, symlinks=True, dirs_exist_ok=True)
            if key == upto:
                return

    try:
        _shims(bin_dir, fc)
        for t in by_track:
            if track is None or t == track:
                run_track(t)
        out_root.mkdir(parents=True, exist_ok=True)
        (out_root / MANIFEST).write_text(json.dumps({"compiler": compiler_version(fc)}, indent=2) + "\n")
    finally:
        if keep is None:
            shutil.rmtree(scratch, ignore_errors=True)
    return done


# shown as measured, not compared: test timings, and the addresses of a backtrace (address-space randomisation)
_VOLATILE = (
    (re.compile(r"\b\d+\.\d+ ?s\b"), "N s"),
    # commit hashes: the ecosystem demo's commits hold its scratch path (the scaffolded remote URL)
    (re.compile(r"\b(?=[0-9a-f]*[a-f])(?=[0-9a-f]*\d)[0-9a-f]{7,64}\b"), "HASH"),
    (re.compile(r'"duration": [0-9.]+'), '"duration": N'),
    (re.compile(r"\b0x[0-9a-f]{6,}\b"), "0xADDRESS"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?\b"), "DATETIME"),  # "generated" stamps
    (re.compile(r"(~/tmp/[\w.-]*-)[a-z0-9_]{8}(?!\w)"), r"\1RANDOM"),  # scratch directories (mkdtemp PREFIX-)
)


def _normalised(text: str) -> str:
    for pattern, replacement in _VOLATILE:
        text = pattern.sub(replacement, text)
    return text


def _same(new: Path, old: Path) -> bool:
    return _normalised(new.read_text()) == _normalised(old.read_text())


def _status(text: str) -> str:
    last = text.rstrip("\n").rsplit("\n", 1)[-1]
    return last if last.startswith("[exit status") else "[exit status 0]"


def compare(fresh: Path, committed: Path = OUTPUT, track: str | None = None) -> list[str]:
    """Differences between freshly generated outputs and the committed ones (of *track* only, when given)."""
    recorded = json.loads((committed / MANIFEST).read_text()) if (committed / MANIFEST).is_file() else {}
    current = json.loads((fresh / MANIFEST).read_text())
    exact = _major(recorded.get("compiler", "")) == _major(current["compiler"])
    names = {p.relative_to(fresh) for p in fresh.rglob("*.txt")} | {
        p.relative_to(committed) for p in committed.rglob("*.txt")
    }
    problems = []
    for name in sorted(names):
        if track is not None and name.parts[0] != track:
            continue
        new, old = fresh / name, committed / name
        if not new.is_file():
            problems.append(f"{name}: committed but no longer generated")
        elif not old.is_file():
            problems.append(f"{name}: generated but not committed")
        elif exact and not _same(new, old):
            problems.append(f"{name}: differs")
        elif not exact and _status(new.read_text()) != _status(old.read_text()):
            problems.append(f"{name}: {_status(new.read_text())} instead of {_status(old.read_text())}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="regenerate in a scratch directory and compare")
    parser.add_argument("--track", help="only this track (and the chapters it starts from)")
    parser.add_argument("--keep", type=Path, help="run in this directory and keep it (debugging)")
    args = parser.parse_args(argv)
    try:
        if args.check:
            with tempfile.TemporaryDirectory(prefix="fobis-docs-check-") as tmp:
                generate(Path(tmp), args.track, args.keep)
                problems = compare(Path(tmp), track=args.track)
            for problem in problems:
                print(problem)
            return 1 if problems else 0
        for key, regenerated in generate(OUTPUT, args.track, args.keep).items():
            print(f"{key}: {'regenerated' if regenerated else 'kept (a tool is missing)'}")
    except ExamplesError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
