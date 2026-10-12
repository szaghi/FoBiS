"""change.py — facts of the staged change, for ``fobis commit`` (deterministic, no model).

What FoBiS can establish about a staged change without reading it like a model:

- **scope candidates**, from the repository's own history first (the scopes of past commits that touched the
  same files, else the nearest directory with history): projects name their components by directory (``lib``,
  ``prism/fnl``, ``cli``), not by module, and history is the only reliable record of that convention; brand-new
  paths fall back to the first directory under ``src/`` (or the package);
- **what kind of lines changed** in Fortran sources, from the staged and the HEAD versions lexed by
  `fobis.analysis`: code, OpenMP/OpenACC directives, or only comments and blank lines; and which procedures,
  and which procedure headers (interfaces), the code lines belong to;
- **type hints** from the file kinds: only documentation, only tests, only CI, only build files, only
  directives (``perf(acc)``), only comments.

`ChangeFacts.render` is the section added to the commit prompt; the scope candidates also restrict the scope
of the structured answer.
"""

# Copyright (C) 2015  Stefano Zaghi
#
# This file is part of FoBiS.py.
#
# FoBiS.py is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# FoBiS.py is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with FoBiS.py. If not, see <http://www.gnu.org/licenses/>.

from __future__ import annotations

import os
import re
import subprocess
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from ..analysis import FileUnits, Unit
from ..lint.engine import analyse

FORTRAN_EXTENSIONS = (".f", ".for", ".fpp", ".f77", ".f90", ".f95", ".f03", ".f08", ".f18", ".f23", ".fypp", ".inc")
BUILD_FILES = ("fobos", "makefile", "cmakelists.txt", "pyproject.toml", "fpm.toml", "setup.py", "setup.cfg")
HISTORY_DEPTH = 300

_HEADER = re.compile(r"^[a-z]+\((?P<scope>[^)]+)\)!?:")
_HUNK = re.compile(r"^@@ -(?P<old>\d+)(?:,(?P<olen>\d+))? \+(?P<new>\d+)(?:,(?P<nlen>\d+))? @@")

Git = Callable[..., str]


@dataclass(frozen=True)
class Revision:
    """Which change to read: the ``git diff`` arguments, and where the old and new versions of a file are.

    Attributes
    ----------
    diff : tuple of str
        Arguments selecting the change (``("--cached",)``, ``("abc123", "HEAD")``, ``("HEAD",)``).
    old : str
        Revision of the old side, for ``git show <old>:<path>``.
    new : str
        Revision of the new side: a commit, ``""`` for the index (``git show :<path>``), or ``WORKTREE``
        (the file on disk).
    root : str
        Top directory of the repository (git paths are relative to it): used to read ``WORKTREE`` files.
    """

    diff: tuple[str, ...]
    old: str
    new: str
    root: str = ""

    def show(self, side: str, path: str, git: Git) -> str:
        """The text of *path* on *side* (``old`` or ``new``)."""
        rev = self.old if side == "old" else self.new
        if rev == WORKTREE:
            try:
                with open(os.path.join(self.root, path), encoding="utf-8", errors="replace") as handle:
                    return handle.read()
            except OSError:
                return ""
        return git("show", f"{rev}:{path}")


WORKTREE = "WORKTREE"
STAGED = Revision(("--cached",), "HEAD", "")


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else ""


# ── file kinds ─────────────────────────────────────────────────────────────────


def file_kind(path: str) -> str:
    """``fortran``, ``docs``, ``test``, ``ci``, ``build`` or ``other``."""
    low = path.lower()
    parts = low.split("/")
    name = parts[-1]
    if low.startswith(".github/") or name in (".gitlab-ci.yml", ".travis.yml"):
        return "ci"
    if any(p in ("test", "tests") for p in parts[:-1]) or name.startswith("test_"):
        return "test"
    if parts[0] in ("doc", "docs") or name.endswith((".md", ".rst")):
        return "docs"
    if name in BUILD_FILES or name.endswith(".cmake") or name.startswith("fobos"):
        return "build"
    if name.endswith(FORTRAN_EXTENSIONS):
        return "fortran"
    return "other"


# ── staged hunks and line kinds ───────────────────────────────────────────────


def staged_changes(git: Git = _git, revision: Revision = STAGED) -> list[tuple[str, str, str]]:
    """(status, path, old path) of every changed file of *revision* (staged by default; renames detected)."""
    found = []
    for line in git("diff", "--no-color", *revision.diff, "--name-status", "-M").splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        old, new = (parts[1], parts[2]) if len(parts) > 2 else (parts[1], parts[1])
        found.append((parts[0][:1], new, old))
    return found


def hunks(path: str, git: Git = _git, revision: Revision = STAGED, old: str | None = None) -> tuple[set[int], set[int]]:
    """(removed old line numbers, added new line numbers) of the diff of *path* in *revision*."""
    removed: set[int] = set()
    added: set[int] = set()
    # git prints paths relative to the top of the repository; ":(top)" makes the pathspec match from any cwd
    paths = [f":(top){p}" for p in ([old, path] if old and old != path else [path])]
    for line in git("diff", "--no-color", *revision.diff, "-U0", "-M", "--", *paths).splitlines():
        match = _HUNK.match(line)
        if not match:
            continue
        old, olen = int(match.group("old")), int(match.group("olen") or 1)
        new, nlen = int(match.group("new")), int(match.group("nlen") or 1)
        removed.update(range(old, old + olen))
        added.update(range(new, new + nlen))
    return removed, added


def line_kinds(units: FileUnits) -> dict[int, str]:
    """Physical line to ``code``, ``omp`` or ``acc`` (directive); lines absent are comments or blank."""
    kinds: dict[int, str] = {}
    for stmt in units.source.statements:
        for line in range(stmt.line, stmt.end_line + 1):
            kinds[line] = stmt.sentinel or "code"
    return kinds


def _innermost(units: FileUnits, line: int) -> Unit | None:
    best = None
    for unit in units.walk():
        if unit.kind in ("interface", "fragment") or not unit.end_line or not unit.name:
            continue
        if unit.line <= line <= unit.end_line and (best is None or unit.line >= best.line):
            best = unit
    return best


def _qualified(unit: Unit) -> str:
    names = []
    node: Unit | None = unit
    while node is not None:
        if node.name and node.kind != "interface":
            names.append(node.name)
        node = node.parent
    return "::".join(reversed(names))


@dataclass
class FileChange:
    """One staged file.

    Attributes
    ----------
    path, status : str
        Path and git status letter (``A``, ``M``, ``D``, ``R`` ...).
    kind : str
        See `file_kind`.
    lines : Counter
        Changed Fortran lines by kind: ``code``, ``omp``, ``acc``, ``comment`` (comment or blank).
    procedures : list of str
        Units whose code lines changed (``module::procedure``).
    interfaces : list of str
        Procedures whose header statement changed.
    added : set of int
        Line numbers, in the new version, of the added or modified lines (Fortran sources only).
    """

    path: str
    status: str
    kind: str
    lines: Counter = field(default_factory=Counter)
    procedures: list[str] = field(default_factory=list)
    interfaces: list[str] = field(default_factory=list)
    added: set[int] = field(default_factory=set)


def _side(text: str, path: str, numbers: set[int], change: FileChange) -> None:
    """Classify the changed *numbers* of one side (HEAD or staged) of a Fortran file."""
    units = analyse(text, path)
    kinds = line_kinds(units)
    headers = {u.header.line: u for u in units.walk() if u.header is not None and u.is_procedure}
    for number in sorted(numbers):
        kind = kinds.get(number, "comment")
        change.lines[kind] += 1
        if kind != "code":
            continue
        unit = _innermost(units, number)
        if unit is not None and unit.kind != "module" and (name := _qualified(unit)) not in change.procedures:
            change.procedures.append(name)
        header = headers.get(number)
        if header is not None and (name := _qualified(header)) not in change.interfaces:
            change.interfaces.append(name)


def file_change(status: str, path: str, old: str, git: Git = _git, revision: Revision = STAGED) -> FileChange:
    """The facts of one changed file (Fortran sources are lexed on both sides of the diff)."""
    change = FileChange(path, status, file_kind(path))
    if not path.lower().endswith(FORTRAN_EXTENSIONS):
        return change
    removed, added = hunks(path, git, revision, old)
    change.added = added
    if status != "A" and removed:
        _side(revision.show("old", old, git), old, removed, change)
    if status != "D" and added:
        _side(revision.show("new", path, git), path, added, change)
    return change


# ── scope candidates ───────────────────────────────────────────────────────────


@dataclass
class ScopeCandidate:
    """A scope and why FoBiS proposes it."""

    name: str
    score: float
    reasons: list[str] = field(default_factory=list)


def history_scopes(git: Git = _git, depth: int = HISTORY_DEPTH) -> dict[str, Counter]:
    """Path (files, and directories with a trailing ``/``) to the scopes of the last *depth* commits touching it."""
    by_path: dict[str, Counter] = {}
    scope = None
    seen: set[str] = set()  # paths already counted for the current commit: one vote per commit
    for line in git("log", "--no-color", f"-n{depth}", "--no-merges", "--format=%x00%s", "--name-only").splitlines():
        if line.startswith("\x00"):
            match = _HEADER.match(line[1:])
            scope = match.group("scope").strip() if match else None
            seen = set()
            continue
        if not line.strip() or scope is None:
            continue
        path = line.strip()
        keys = [path]
        parent = os.path.dirname(path)
        while parent:
            keys.append(parent + "/")
            parent = os.path.dirname(parent)
        for key in keys:
            if key not in seen:
                seen.add(key)
                by_path.setdefault(key, Counter())[scope] += 1
    return by_path


def path_scope(path: str) -> str | None:
    """The component a path new to the history suggests: the directory under ``src/`` (or the package)."""
    parts = [p for p in path.split("/") if p]
    if len(parts) == 1:
        return None
    if parts[0] in ("src", "lib", "source"):
        return parts[1].lower() if len(parts) > 2 else os.path.splitext(parts[1])[0].lower()
    if len(parts) > 2:
        return parts[1].lower()
    return os.path.splitext(parts[-1])[0].lower()


def scope_candidates(
    paths: list[str], history: dict[str, Counter], limit: int = 4, floor: float = 0.15, evidence: int = 3
) -> list[ScopeCandidate]:
    """Scopes for the staged *paths*, best first: each file votes with the scope shares of its history.

    The evidence of a file is its own history or, when that counts fewer than *evidence* commits, the history
    of its nearest enclosing directory that does; directories stop below the top level (the history of ``src/``
    or of the package is the whole project, no evidence of a component). A file with no evidence at all votes
    for `path_scope`. When the directory decides, the file's own commits weigh half as a tie-break.
    Candidates scoring below *floor* times the best are left out.
    """
    scores: dict[str, ScopeCandidate] = {}
    for path in paths:
        counter: Counter = Counter()
        where = path
        key, parent = path, os.path.dirname(path)
        while True:
            if history.get(key):  # a directory's history contains its files': it replaces, never adds
                counter, where = history[key], key
            if sum(counter.values()) >= evidence or "/" not in parent:
                break
            key, parent = parent + "/", os.path.dirname(parent)
        if counter:
            total = sum(counter.values())
            own = history.get(path) if where != path else None
            own_total = sum(own.values()) if own else 0
            for name, count in counter.items():
                cand = scores.setdefault(name, ScopeCandidate(name, 0.0))
                cand.score += count / total
                cand.reasons.append(f"{count} of {total} past commits touching {where} used it")
                if own and own[name]:  # the file's own (thin) history breaks the ties of its directory
                    cand.score += 0.5 * own[name] / own_total
                    cand.reasons.append(f"{own[name]} of {own_total} past commits touching {path} used it")
        elif (name := path_scope(path)) is not None:
            cand = scores.setdefault(name, ScopeCandidate(name, 0.0))
            cand.score += 0.5
            cand.reasons.append(f"{path} is new to the history: named after its directory")
    ranked = sorted(scores.values(), key=lambda c: (-c.score, c.name))
    if not ranked:
        return []
    return [c for c in ranked if c.score >= floor * ranked[0].score][:limit]


# ── the facts ──────────────────────────────────────────────────────────────────


@dataclass
class ChangeFacts:
    """Facts of the staged change: files, scope candidates, type hints."""

    files: list[FileChange] = field(default_factory=list)
    scopes: list[ScopeCandidate] = field(default_factory=list)
    hints: list[tuple[str, str]] = field(default_factory=list)

    @property
    def scope_names(self) -> list[str]:
        return [c.name for c in self.scopes]

    def render(self) -> str:
        """The prompt section (also printed by ``fobis commit --show-facts``)."""
        lines = ["## Facts of the change (computed by FoBiS from git and the sources)", ""]
        if self.scopes:
            lines.append("Scope candidates (use one of these, or an empty scope for a cross-cutting change):")
            lines += [f"- {c.name}: " + "; ".join(c.reasons[:3]) for c in self.scopes]
        else:
            lines.append("No scope candidate: name the component from the paths, or leave the scope empty.")
        lines += [f"Type hint: {hint} ({reason})" for hint, reason in self.hints]
        details = []
        for change in self.files:
            parts = []
            if change.lines:
                parts.append(
                    "changed lines (removed + added): " + ", ".join(f"{n} {k}" for k, n in sorted(change.lines.items()))
                )
            if change.procedures:
                parts.append("procedures: " + ", ".join(change.procedures[:8]))
            if change.interfaces:
                parts.append("headers (interfaces) changed: " + ", ".join(change.interfaces[:8]))
            if parts:
                details.append(f"- {change.path}: " + "; ".join(parts))
        if details:
            lines += [
                "",
                "Fortran sources (changed lines classified by the lexer; comment = comment or blank):",
                *details,
            ]
        return "\n".join(lines)


_ONLY = {
    "docs": "only documentation files changed",
    "test": "only test files changed",
    "ci": "only CI configuration changed",
    "build": "only build files changed",
}


def _hints(files: list[FileChange]) -> list[tuple[str, str]]:
    hints = []
    kinds = {f.kind for f in files}
    if len(kinds) == 1 and (kind := next(iter(kinds))) in _ONLY:
        hints.append((kind, _ONLY[kind]))
    if files and all(f.lines for f in files):
        total: Counter = Counter()
        for change in files:
            total.update(change.lines)
        directives = [k for k in ("omp", "acc") if total[k]]
        if directives and not total["code"]:
            names = " and ".join("OpenMP" if k == "omp" else "OpenACC" for k in directives)
            hints.append((f"perf({directives[0]})", f"only {names} directive lines changed, no code"))
        elif not total["code"] and not directives:
            hints.append(("docs or style", "only comments and blank lines changed in the Fortran sources"))
    interfaces = [n for f in files for n in f.interfaces]
    if interfaces:
        hints.append(
            ("breaking?", f"procedure headers changed ({', '.join(interfaces)}): breaking only for a published API")
        )
    return hints


def change_facts(git: Git = _git, depth: int = HISTORY_DEPTH, revision: Revision = STAGED) -> ChangeFacts:
    """The facts of the change of *revision* (staged by default) in the repository of the current directory."""
    files = [file_change(status, path, old, git, revision) for status, path, old in staged_changes(git, revision)]
    facts = ChangeFacts(files=files, hints=_hints(files))
    facts.scopes = scope_candidates([f.path for f in files], history_scopes(git, depth))
    directive = next((h for h, _ in facts.hints if h.startswith("perf(")), None)
    if directive:  # the plan's perf(acc): only directives changed, the programming model is the component
        name = directive[len("perf(") : -1]
        first = ScopeCandidate(name, 1.0, ["only these directives changed"])
        facts.scopes = [first, *(c for c in facts.scopes if c.name != name)][:4]
    return facts
