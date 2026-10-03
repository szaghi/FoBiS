"""
Ecosystem.py — knowledge of a set of interconnected FoBiS projects (``fobis ecosystem``).

The managed projects are listed in the user configuration (``[ecosystem]`` section of
``~/.config/fobis/config.ini``). This module reads their fobos files, builds the dependency
graph among them, collects the state of every repository (git, release, CI, scaffold drift,
dependency pins) and renders it as a terminal table, JSON or a self-contained HTML page.

It uses the rest of FoBiS only through public interfaces (``Fobos``, ``Scaffolder``,
``SemVer``) and never changes the working directory: every git call runs with ``git -C``.
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

import argparse
import configparser
import contextlib
import datetime
import fnmatch
import html
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field

from .SemVer import Version

GIT_TIMEOUT = 120
"""Seconds before a git or gh call is abandoned."""

_GITHUB_RE = re.compile(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$")
_CONVENTIONAL_RE = re.compile(r"^(?P<type>[A-Za-z]+)(?:\([^)]*\))?(?P<bang>!)?:")
_BUMPS = ("patch", "minor", "major")

# Paths whose changes alone never call for a release; a project's fobos can replace them with
# ``[ecosystem] release_exclude = <globs>`` (fnmatch patterns on repository-relative paths).
DEFAULT_RELEASE_EXCLUDE = ("docs/*", ".github/*", "*.md", "scripts/*")

# Overall state of a project, in decreasing order of severity: the colour of the diagram nodes.
STATES = ("error", "ci-failing", "stale", "unreleased", "ok")


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def _run(args: list[str], timeout: int = GIT_TIMEOUT) -> tuple[int, str]:
    """
    Run a command without a shell and return its exit code and output.

    Git and ssh are told never to prompt: a repository needing credentials fails instead of hanging.

    Parameters
    ----------
    args : list[str]
        Command and arguments.
    timeout : int
        Seconds before the command is abandoned.

    Returns
    -------
    tuple[int, str]
        Exit code (127 when the program is missing, 124 on timeout) and the stripped stdout
        (stderr when the command failed).
    """
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=env, check=False)
    except FileNotFoundError:
        return 127, f"{args[0]}: command not found"
    except subprocess.TimeoutExpired:
        return 124, f"{' '.join(args)}: timed out after {timeout}s"
    if proc.returncode:
        return proc.returncode, (proc.stderr or proc.stdout).strip()
    return 0, proc.stdout.strip()


def _git(path: str, *args: str) -> tuple[int, str]:
    """Run ``git -C path args...``."""
    return _run(["git", "-C", path, *args])


def github_slug(url: str) -> str:
    """
    Return the ``owner/repo`` slug of a GitHub URL ('' for any other URL).

    Parameters
    ----------
    url : str
        HTTPS or SSH remote URL.
    """
    m = _GITHUB_RE.search(url.strip())
    return f"{m.group('owner')}/{m.group('repo')}" if m else ""


def _repo_name(url: str) -> str:
    """Return the repository name of a dependency URL or ``user/repo`` shorthand."""
    return url.strip().rstrip("/").split("/")[-1].split(":")[-1].removesuffix(".git")


def suggest_bump(messages: list[str]) -> str | None:
    """
    Suggest the semantic-version bump implied by a list of commit messages.

    Conventional Commits rules: a ``!`` after the type/scope or a ``BREAKING CHANGE`` footer
    means major, ``feat`` means minor, anything else (non-conventional messages included)
    means patch.

    Parameters
    ----------
    messages : list[str]
        Full commit messages (subject, blank line, body).

    Returns
    -------
    str | None
        ``major``, ``minor``, ``patch``, or None when there are no messages.
    """
    level = -1
    for message in messages:
        subject = message.split("\n", 1)[0]
        m = _CONVENTIONAL_RE.match(subject)
        if (m and m.group("bang")) or "BREAKING CHANGE" in message or "BREAKING-CHANGE" in message:
            return "major"
        level = max(level, 1 if m and m.group("type").lower() == "feat" else 0)
    return _BUMPS[level] if level >= 0 else None


def bump_version(version: str, bump: str) -> str:
    """
    Return *version* bumped by *bump*, keeping a leading ``v`` when present.

    Parameters
    ----------
    version : str
        Current version (``1.2.3`` or ``v1.2.3``).
    bump : str
        ``major``, ``minor`` or ``patch``.
    """
    v = Version(version)
    if bump == "major":
        major, minor, patch = v.major + 1, 0, 0
    elif bump == "minor":
        major, minor, patch = v.major, v.minor + 1, 0
    else:
        major, minor, patch = v.major, v.minor, v.patch + 1
    prefix = "v" if version.strip().startswith("v") else ""
    return f"{prefix}{major}.{minor}.{patch}"


def _read_fobos(fobos_path: str):
    """Return the ``Fobos`` object of a fobos file, without depending on the current directory."""
    from .Fobos import Fobos

    return Fobos(argparse.Namespace(fobos=fobos_path, fobos_case_insensitive=False, mode=None, lmodes=False))


# ---------------------------------------------------------------------------
# Projects and graph
# ---------------------------------------------------------------------------


@dataclass
class Project:
    """
    A managed project: a git repository with a fobos file.

    Attributes
    ----------
    name : str
        Directory basename.
    path : str
        Absolute path of the repository.
    slug : str
        GitHub ``owner/repo`` ('' when the origin is not on GitHub).
    deps_dir : str
        Absolute path of the directory ``fobis fetch`` clones the dependencies into.
    fobos_deps : dict[str, str]
        ``{dependency name: URL}`` from the fobos ``[dependencies]`` section.
    deps : list[str]
        Names of the ecosystem projects this one depends on (filled by ``Ecosystem``).
    dep_keys : dict[str, str]
        ``{ecosystem project: fobos dependency key}``, the key naming it in ``fobos.lock``.
    external : list[str]
        Dependencies that are not ecosystem projects.
    release_exclude : list[str]
        Globs of the paths whose changes alone do not call for a release.
    error : str
        Why the project could not be read ('' when it was read).
    """

    name: str
    path: str
    slug: str = ""
    deps_dir: str = ""
    fobos_deps: dict[str, str] = field(default_factory=dict)
    deps: list[str] = field(default_factory=list)
    dep_keys: dict[str, str] = field(default_factory=dict)
    external: list[str] = field(default_factory=list)
    release_exclude: list[str] = field(default_factory=lambda: list(DEFAULT_RELEASE_EXCLUDE))
    error: str = ""

    @classmethod
    def load(cls, path: str) -> Project:
        """
        Read the project at *path*; problems are recorded in ``error``, never raised.

        Parameters
        ----------
        path : str
            Repository path.
        """
        path = os.path.abspath(path)
        project = cls(name=os.path.basename(path.rstrip(os.sep)), path=path)
        fobos_path = os.path.join(path, "fobos")
        if not os.path.isdir(path):
            project.error = "directory not found"
            return project
        if not os.path.exists(os.path.join(path, ".git")):
            project.error = "not a git repository"
            return project
        if not os.path.isfile(fobos_path):
            project.error = "no fobos file"
            return project
        code, url = _git(path, "remote", "get-url", "origin")
        project.slug = github_slug(url) if code == 0 else ""
        try:
            fobos = _read_fobos(fobos_path)
            project.fobos_deps = {name: spec.split("::")[0].strip() for name, spec in fobos.get_dependencies().items()}
            project.deps_dir = os.path.normpath(os.path.join(path, fobos.get_deps_dir()))
            if fobos.fobos is not None and fobos.fobos.has_option("ecosystem", "release_exclude"):
                project.release_exclude = fobos.fobos.get("ecosystem", "release_exclude").split()
        except (Exception, SystemExit) as err:  # a broken fobos must not stop the other projects
            project.error = f"cannot read fobos: {err}"
        return project

    def lock(self) -> dict[str, str]:
        """Return ``{dependency name: locked commit}`` from ``<deps_dir>/fobos.lock`` (empty if absent)."""
        lock_path = os.path.join(self.deps_dir, "fobos.lock")
        if not self.deps_dir or not os.path.isfile(lock_path):
            return {}
        cp = configparser.RawConfigParser()
        cp.optionxform = str
        cp.read(lock_path)
        return {sec: cp.get(sec, "commit", fallback="") for sec in cp.sections()}


@dataclass
class Pin:
    """
    The commit of an ecosystem dependency a project is built against.

    ``state`` is one of ``current`` (lock at the dependency's remote head), ``stale`` (lock behind
    it), ``ahead`` (lock newer than the known head: fetch the dependency), ``diverged``,
    ``unlocked`` (no lock entry: run ``fobis fetch``) and ``unknown`` (no remote head).
    """

    dep: str
    locked: str
    head: str
    state: str


@dataclass
class ProjectStatus:
    """State of one project, as shown in a dashboard row."""

    name: str
    path: str
    slug: str = ""
    branch: str = ""
    head: str = ""
    dirty: int = 0
    ahead: int | None = None
    behind: int | None = None
    fetched: bool = False
    version: str = ""
    tag: str = ""
    unreleased: int = 0
    releasable: int = 0
    bump: str | None = None
    next_version: str = ""
    pushed: bool = False
    ci: str = "unknown"
    drift: int | None = None
    pins: list[Pin] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    state: str = "ok"

    def overall_state(self) -> str:
        """Return the most severe of the project's conditions (see ``STATES``)."""
        if self.ci == "failing":
            return "ci-failing"
        if any(pin.state in ("stale", "diverged", "unlocked") for pin in self.pins):
            return "stale"
        if self.releasable:
            return "unreleased"
        return "ok"

    def to_dict(self) -> dict:
        """Return the status as a JSON-ready dict."""
        return asdict(self)


class Ecosystem:
    """
    A set of projects and the dependency graph among them.

    Parameters
    ----------
    paths : list[str]
        Repository paths, in the order the user listed them.
    """

    def __init__(self, paths: list[str]) -> None:
        self.projects: dict[str, Project] = {}
        self.warnings: list[str] = []
        for path in paths:
            project = Project.load(path)
            if project.name in self.projects:
                self.warnings.append(f"duplicate project name {project.name!r}: {path} ignored")
                continue
            self.projects[project.name] = project
        self._link()

    def _link(self) -> None:
        """Resolve each project's fobos dependencies against the ecosystem projects."""
        by_key: dict[str, str] = {}
        for project in self.projects.values():
            by_key[project.name.lower()] = project.name
            if project.slug:
                by_key.setdefault(project.slug.split("/")[1].lower(), project.name)
        for project in self.projects.values():
            for dep_name, url in project.fobos_deps.items():
                target = by_key.get(dep_name.lower()) or by_key.get(_repo_name(url).lower())
                if target and target != project.name:
                    if target not in project.deps:
                        project.deps.append(target)
                        project.dep_keys[target] = dep_name
                else:
                    project.external.append(dep_name)

    def dep_key(self, project: str, dep: str) -> str:
        """Return the fobos ``[dependencies]`` key under which *project* names the ecosystem project *dep*."""
        return self.projects[project].dep_keys.get(dep, dep)

    def dependents(self, name: str) -> list[str]:
        """Return the projects that depend directly on *name*."""
        return [p.name for p in self.projects.values() if name in p.deps]

    def levels(self) -> tuple[list[list[str]], list[str]]:
        """
        Group the projects in topological levels (Kahn's algorithm).

        Level 0 holds the projects with no ecosystem dependency; every project sits one level
        above its deepest dependency, so releasing level by level never releases a project
        before one of its dependencies.

        Returns
        -------
        tuple[list[list[str]], list[str]]
            The levels (each in the user's order) and the projects left out because they are
            on, or depend on, a dependency cycle.
        """
        remaining = {name: set(p.deps) for name, p in self.projects.items()}
        levels: list[list[str]] = []
        while True:
            ready = [name for name, deps in remaining.items() if not deps]
            if not ready:
                break
            levels.append(ready)
            for name in ready:
                del remaining[name]
            for deps in remaining.values():
                deps.difference_update(ready)
        return levels, list(remaining)

    def release_order(self) -> list[str]:
        """Return the projects in dependency order (dependencies first); cyclic ones are excluded."""
        return [name for level in self.levels()[0] for name in level]

    def graph_dict(self) -> dict:
        """Return the graph as a JSON-ready dict."""
        levels, cycle = self.levels()
        return {
            "projects": [
                {
                    "name": p.name,
                    "path": p.path,
                    "slug": p.slug,
                    "depends_on": p.deps,
                    "dependents": self.dependents(p.name),
                    "external": p.external,
                    "error": p.error,
                }
                for p in self.projects.values()
            ],
            "levels": levels,
            "release_order": [name for level in levels for name in level],
            "cycle": cycle,
            "warnings": self.warnings,
        }

    # ------------------------------------------------------------------
    # Status collection
    # ------------------------------------------------------------------

    def fetch(self, jobs: int = 8) -> dict[str, str]:
        """
        Run ``git fetch`` in every readable project, concurrently.

        Returns
        -------
        dict[str, str]
            ``{project: error message}`` for the fetches that failed.
        """
        names = [p.name for p in self.projects.values() if not p.error]
        with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
            results = list(pool.map(lambda n: _git(self.projects[n].path, "fetch", "--quiet"), names))
        return {name: out for name, (code, out) in zip(names, results, strict=True) if code}

    def collect(self, fetch: bool = True, ci: bool = True, jobs: int = 8) -> list[ProjectStatus]:
        """
        Collect the status of every project.

        Parameters
        ----------
        fetch : bool
            Run ``git fetch`` first, so that upstream, CI at HEAD and dependency heads are current.
        ci : bool
            Query GitHub Actions through ``gh``; without ``gh`` the CI state is ``unknown``.
        jobs : int
            Projects examined concurrently.

        Returns
        -------
        list[ProjectStatus]
            One status per project, in the user's order.
        """
        fetch_errors = self.fetch(jobs) if fetch else {}
        # Remote default-branch head of every project, read after the fetch: what the pins are checked against.
        heads = {p.name: _remote_head(p.path) for p in self.projects.values() if not p.error}
        use_gh = ci and shutil.which("gh") is not None
        with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
            statuses = list(pool.map(lambda p: self._status(p, heads, use_gh), self.projects.values()))
        for status in statuses:
            if status.name in fetch_errors:
                status.errors.append(f"git fetch failed: {fetch_errors[status.name]}")
            status.fetched = fetch and status.state != "error" and status.name not in fetch_errors
        return statuses

    def _status(self, project: Project, heads: dict[str, str | None], use_gh: bool) -> ProjectStatus:
        """Collect the status of one project; problems are recorded, never raised."""
        status = ProjectStatus(name=project.name, path=project.path, slug=project.slug)
        if project.error:
            status.errors.append(project.error)
            status.state = "error"
            return status
        path = project.path
        code, out = _git(path, "rev-parse", "--abbrev-ref", "HEAD")
        status.branch = out if code == 0 else "?"
        code, out = _git(path, "rev-parse", "HEAD")
        status.head = out if code == 0 else ""
        code, out = _git(path, "status", "--porcelain")
        status.dirty = len(out.splitlines()) if code == 0 else 0
        code, out = _git(path, "rev-list", "--left-right", "--count", "HEAD...@{upstream}")
        if code == 0 and len(out.split()) == 2:
            status.ahead, status.behind = (int(n) for n in out.split())
        status.version = _read_version(path)
        _release_status(status, project.release_exclude)
        status.pushed = bool(status.head) and bool(_git(path, "branch", "-r", "--contains", "HEAD")[1])
        status.ci = _ci_status(project.slug, status.head, status.pushed) if use_gh else "unknown"
        status.drift = _scaffold_drift(path)
        locks = project.lock()
        for dep in project.deps:
            key = self.dep_key(project.name, dep)
            locked = locks.get(key) or next((c for k, c in locks.items() if k.lower() == key.lower()), "")
            status.pins.append(_pin(dep, locked, heads.get(dep), self.projects[dep].path))
        status.state = status.overall_state()
        return status


def _remote_head(path: str) -> str | None:
    """Return the commit of the remote default branch as last fetched (None if unknown)."""
    for ref in ("refs/remotes/origin/HEAD", "refs/remotes/origin/main", "refs/remotes/origin/master"):
        code, out = _git(path, "rev-parse", "--verify", "--quiet", ref)
        if code == 0 and out:
            return out
    return None


def _read_version(path: str) -> str:
    """Return the project version from its VERSION file, or the literal fobos ``[project] version``."""
    version_file = os.path.join(path, "VERSION")
    if os.path.isfile(version_file):
        with open(version_file, encoding="utf-8") as fh:
            return fh.read().strip()
    with contextlib.suppress(Exception, SystemExit):
        version = _read_fobos(os.path.join(path, "fobos")).get_project_info().get("version", "")
        if version and not os.path.exists(os.path.join(path, version)):
            return version
    return ""


def is_releasable(files: list[str], exclude: list[str] | tuple[str, ...]) -> bool:
    """
    Return True when a commit touching *files* calls for a release.

    A commit counts when it changes at least one path not matched by the *exclude* globs; a commit
    changing no file (an empty commit, a merge) does not count.

    Parameters
    ----------
    files : list[str]
        Repository-relative paths changed by the commit.
    exclude : list[str] | tuple[str, ...]
        fnmatch globs (``*`` also matches ``/``).
    """
    return any(not any(fnmatch.fnmatch(f, glob) for glob in exclude) for f in files)


def _release_status(status: ProjectStatus, exclude: list[str] | tuple[str, ...] = DEFAULT_RELEASE_EXCLUDE) -> None:
    """
    Fill the latest tag, the commits since it, the releasable ones and the bump they imply.

    Whether a commit calls for a release is decided by the files it changes (``is_releasable``),
    how big a release by its Conventional-Commits type (``suggest_bump``).
    """
    code, tag = _git(status.path, "describe", "--tags", "--abbrev=0")
    status.tag = tag if code == 0 else ""
    rev_range = f"{status.tag}..HEAD" if status.tag else "HEAD"
    # One record per commit: \x1e, the message, \x1f, then the changed files one per line. Python
    # counts \x1c-\x1f as whitespace, so _run's strip() may eat the first separator: skip blanks.
    code, out = _git(status.path, "log", "--format=%x1e%B%x1f", "--name-only", rev_range)
    releasable = []
    for record in [r for r in out.split("\x1e") if r.strip()] if code == 0 else []:
        message, _, files = record.partition("\x1f")
        status.unreleased += 1
        if is_releasable(files.split(), exclude):
            releasable.append(message.strip())
    status.releasable = len(releasable)
    status.bump = suggest_bump(releasable)
    if status.tag and status.bump:
        with contextlib.suppress(ValueError):
            status.next_version = bump_version(status.tag, status.bump)


def _ci_status(slug: str, sha: str, pushed: bool) -> str:
    """
    Return the GitHub Actions result for commit *sha*.

    Returns
    -------
    str
        ``passing``, ``failing``, ``running``, ``none`` (no run for the commit), ``not pushed``
        or ``unknown`` (not on GitHub, or ``gh`` failed).
    """
    if not slug or not sha:
        return "unknown"
    if not pushed:
        return "not pushed"
    code, out = _run(
        ["gh", "run", "list", "-R", slug, "--commit", sha, "--limit", "50", "--json", "workflowName,status,conclusion"]
    )
    if code:
        return "unknown"
    try:
        runs = json.loads(out or "[]")
    except json.JSONDecodeError:
        return "unknown"
    latest: dict[str, dict] = {}
    for run in runs:  # newest first: keep the latest run of each workflow (re-runs supersede)
        latest.setdefault(run.get("workflowName", ""), run)
    if not latest:
        return "none"
    if any(r.get("status") != "completed" for r in latest.values()):
        return "running"
    if all(r.get("conclusion") in ("success", "skipped", "neutral") for r in latest.values()):
        return "passing"
    return "failing"


def _scaffold_drift(path: str) -> int | None:
    """Return the number of scaffold-managed files not in sync, project-owned ones excluded (None if unknown)."""
    try:
        drift = scaffold_for(path).drift()
    except (Exception, SystemExit):
        return None
    return sum(1 for _, state in drift if state not in ("ok", "skipped"))


def _pin(dep: str, locked: str, head: str | None, dep_path: str) -> Pin:
    """Compare a locked commit with the dependency's remote head (ancestry checked in the dependency's clone)."""
    if not locked:
        return Pin(dep, "", head or "", "unlocked")
    if not head:
        return Pin(dep, locked, "", "unknown")
    if locked == head:
        return Pin(dep, locked, head, "current")
    if _git(dep_path, "merge-base", "--is-ancestor", locked, head)[0] == 0:
        return Pin(dep, locked, head, "stale")
    if _git(dep_path, "merge-base", "--is-ancestor", head, locked)[0] == 0:
        return Pin(dep, locked, head, "ahead")
    return Pin(dep, locked, head, "diverged")


def discover(root: str, registered: list[str]) -> list[str]:
    """
    Return the git repositories with a fobos file directly under *root* that are not registered.

    Parameters
    ----------
    root : str
        Directory to scan (one level, no recursion).
    registered : list[str]
        Paths already in the ecosystem.
    """
    known = {os.path.realpath(p) for p in registered}
    found: list[str] = []
    if not os.path.isdir(root):
        return found
    for entry in sorted(os.listdir(root), key=str.lower):
        path = os.path.join(root, entry)
        if (
            os.path.isdir(path)
            and os.path.exists(os.path.join(path, ".git"))
            and os.path.isfile(os.path.join(path, "fobos"))
            and os.path.realpath(path) not in known
        ):
            found.append(os.path.abspath(path))
    return found


# ---------------------------------------------------------------------------
# Acting across projects (Phase 2): exec, fetch, check, scaffold
# ---------------------------------------------------------------------------


@dataclass
class StepResult:
    """
    Outcome of one command run in one project.

    ``status`` is ``passed``, ``failed`` (non-zero exit), ``crashed`` (killed by a signal),
    ``skipped`` (not run: unreadable project, nothing to do, missing dependency), ``aborted``
    (a release declined at its prompt) or ``not run`` (after a failure with ``fail_fast``).
    """

    name: str
    status: str
    returncode: int | None = None
    seconds: float = 0.0
    detail: str = ""

    @property
    def failed(self) -> bool:
        """True when the command ran and did not succeed."""
        return self.status in ("failed", "crashed", "aborted")


class FobisShim:
    """
    A directory with ``fobis`` and ``FoBiS.py`` launchers of the running FoBiS, prepended to PATH.

    Commands run in the projects (and the fobos rules they call, which spell ``fobis`` or
    ``FoBiS.py``) then use this very FoBiS, not whichever one the PATH resolves first.
    Use as a context manager; ``env`` is the environment to run commands with.
    """

    def __enter__(self) -> FobisShim:
        self.dir = tempfile.mkdtemp(prefix="fobis-shim-")
        for name in ("fobis", "FoBiS.py"):
            path = os.path.join(self.dir, name)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} -m fobis "$@"\n')
            os.chmod(path, 0o755)
        self.env = dict(os.environ)
        self.env["PATH"] = self.dir + os.pathsep + self.env.get("PATH", "")
        return self

    def __exit__(self, *exc: object) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)


def run_step(
    name: str, command: str, cwd: str, env: dict[str, str] | None = None, echo=print, input_text: str | None = None
) -> StepResult:
    """
    Run a shell command in *cwd*, its output streaming to the terminal, and classify the outcome.

    Parameters
    ----------
    name : str
        Project name, for the header and the result.
    command : str
        Command line, run by ``bash -c``.
    cwd : str
        Working directory.
    env : dict[str, str] | None
        Environment (default: the current one).
    echo : callable
        Printer of the header line.
    input_text : str | None
        Text fed to the command's stdin; None leaves the terminal's stdin to it (prompts reach the user).
    """
    echo(f"\n==> {name}: {command}")
    sys.stdout.flush()  # the header must precede the command's own output
    start = time.monotonic()
    try:
        proc = subprocess.run(["bash", "-c", command], cwd=cwd, env=env, check=False, input=input_text, text=True)
    except OSError as err:
        return StepResult(name, "failed", None, time.monotonic() - start, str(err))
    seconds = time.monotonic() - start
    code = proc.returncode
    # bash reports a child killed by signal N as 128 + N; Python reports bash itself killed as -N
    signum = -code if code < 0 else code - 128 if code > 128 else 0
    if signum:
        with contextlib.suppress(ValueError):
            return StepResult(name, "crashed", code, seconds, signal.Signals(signum).name)
    if code:
        return StepResult(name, "failed", code, seconds, f"exit {code}")
    return StepResult(name, "passed", 0, seconds)


def select(eco: Ecosystem, only: list[str] | None = None, start: str | None = None) -> list[str]:
    """
    Return project names in release order, optionally restricted.

    Parameters
    ----------
    eco : Ecosystem
        The ecosystem.
    only : list[str] | None
        Keep only these projects (case-insensitive names).
    start : str | None
        Drop the projects before this one in release order (resume after a failure).

    Raises
    ------
    ValueError
        For a name that is not an ecosystem project.
    """
    order = eco.release_order() + eco.levels()[1]  # cyclic projects last: they have no valid position
    by_lower = {n.lower(): n for n in order}
    for name in [*(only or []), *([start] if start else [])]:
        if name.lower() not in by_lower:
            raise ValueError(f"unknown project {name!r}: choose among {', '.join(order)}")
    if start:
        order = order[order.index(by_lower[start.lower()]) :]
    if only:
        wanted = {by_lower[n.lower()] for n in only}
        order = [n for n in order if n in wanted]
    return order


def exec_all(eco: Ecosystem, command: str, names: list[str], fail_fast: bool = False, echo=print) -> list[StepResult]:
    """
    Run *command* in every selected project, in the given (release) order.

    Unreadable projects are skipped. ``fobis``/``FoBiS.py`` in the command resolve to this FoBiS.
    """
    results: list[StepResult] = []
    with FobisShim() as shim:
        for name in names:
            project = eco.projects[name]
            if project.error:
                results.append(StepResult(name, "skipped", detail=project.error))
            elif fail_fast and any(r.failed for r in results):
                results.append(StepResult(name, "not run"))
            else:
                results.append(run_step(name, command, project.path, shim.env, echo))
    return results


def fetch_all(eco: Ecosystem, names: list[str], fail_fast: bool = False, echo=print) -> list[StepResult]:
    """
    Run ``fobis fetch --update`` in every selected project that declares dependencies, in release order.

    A project's dependencies are updated after the dependencies themselves: once every project
    is fetched, each lock points at the heads of its dependencies.
    """
    with_deps = [n for n in names if eco.projects[n].fobos_deps or eco.projects[n].error]
    by_name = {r.name: r for r in exec_all(eco, "fobis fetch --update", with_deps, fail_fast, echo)}
    return [by_name.get(n) or StepResult(n, "skipped", detail="no dependencies") for n in names]


def transitive_dependents(eco: Ecosystem, name: str) -> list[str]:
    """Return the projects depending on *name* directly or indirectly, in release order."""
    found: set[str] = set()
    frontier = [name]
    while frontier:
        for dependent in eco.dependents(frontier.pop()):
            if dependent not in found:
                found.add(dependent)
                frontier.append(dependent)
    return [n for n in select(eco) if n in found]


def check_commands(project: Project) -> list[str]:
    """
    Return the commands that build and test *project* for ``check``.

    From the project's fobos ``[ecosystem] check`` (one command per line), else the coverage
    rule the CI runs (``fobis rule --ex makecoverage``) when the fobos defines it, else
    ``fobis build``.
    """
    cfg = configparser.RawConfigParser()
    cfg.optionxform = str
    with contextlib.suppress(configparser.Error, OSError):
        cfg.read(os.path.join(project.path, "fobos"))
    if cfg.has_option("ecosystem", "check"):
        return [line.strip() for line in cfg.get("ecosystem", "check").splitlines() if line.strip()]
    if cfg.has_section("rule-makecoverage"):
        return ["fobis rule --ex makecoverage"]
    return ["fobis build"]


def _working_files(path: str) -> list[str] | None:
    """Return the files of a working copy (tracked and untracked, not ignored), or None if not a git repository."""
    code, out = _run(["git", "-C", path, "ls-files", "-z", "--cached", "--others", "--exclude-standard"])
    if code:
        return None
    return sorted({f for f in out.split("\0") if f})


def copy_working_copy(src: str, dst: str) -> None:
    """
    Copy the working copy of *src* to *dst*: tracked and untracked files, uncommitted changes included,
    ignored files (build products, fetched dependencies, node_modules) excluded.

    A directory that is not a git repository is copied whole.
    """
    files = _working_files(src)
    if files is None:
        shutil.copytree(src, dst, symlinks=True)
        return
    os.makedirs(dst, exist_ok=True)
    for rel in files:
        source, target = os.path.join(src, rel), os.path.join(dst, rel)
        if os.path.isdir(source) and not os.path.islink(source):  # a submodule: its own working copy
            copy_working_copy(source, target)
            continue
        if not os.path.lexists(source):  # deleted in the working tree, still in the index
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if os.path.islink(source):
            os.symlink(os.readlink(source), target)
        else:
            shutil.copy2(source, target)


def stage_dependent(eco: Ecosystem, dependent: str, changed: str, workdir: str) -> str:
    """
    Stage a copy of *dependent* built against the local working copy of *changed*.

    The copy holds the dependent's working copy and, in its ``deps_dir``, every dependency as the
    dependent has fetched it, except *changed*, taken from its local working copy (uncommitted
    changes included). Nothing is built yet, so the build is clean by construction.

    Returns
    -------
    str
        Path of the staged copy.

    Raises
    ------
    FileNotFoundError
        When a dependency was never fetched in the dependent (run ``fobis fetch`` there).
    """
    project = eco.projects[dependent]
    stage = os.path.join(workdir, dependent)
    copy_working_copy(project.path, stage)
    staged_deps = os.path.join(stage, os.path.relpath(project.deps_dir, project.path))
    os.makedirs(staged_deps, exist_ok=True)
    if os.path.isdir(project.deps_dir):  # .deps_config.ini, fobos.lock: read by the build
        for entry in os.listdir(project.deps_dir):
            source = os.path.join(project.deps_dir, entry)
            if os.path.isfile(source):
                shutil.copy2(source, os.path.join(staged_deps, entry))
    changed_key = project.dep_keys.get(changed)
    for key in project.fobos_deps:
        target = os.path.join(staged_deps, key)
        if key == changed_key:
            copy_working_copy(eco.projects[changed].path, target)
            continue
        source = os.path.join(project.deps_dir, key)
        if not os.path.isdir(source):
            raise FileNotFoundError(f"dependency {key} not fetched in {dependent}: run 'fobis fetch' there")
        copy_working_copy(source, target)
    return stage


def check_dependents(
    eco: Ecosystem, changed: str, keep: bool = False, fail_fast: bool = False, echo=print
) -> tuple[list[StepResult], str | None]:
    """
    Pre-release impact check: build and test every dependent of *changed* against its local working copy.

    Each transitive dependent is staged in a temporary directory (``stage_dependent``) and its check
    commands (``check_commands``) run there, in release order: the real repositories are never
    touched and every build is clean.

    Returns
    -------
    tuple[list[StepResult], str | None]
        One result per dependent, and the temporary directory when it was kept (on request, or
        because a check did not pass, for inspection), else None.
    """
    workdir = tempfile.mkdtemp(prefix=f"fobis-check-{changed}-")
    results: list[StepResult] = []
    with FobisShim() as shim:
        for name in transitive_dependents(eco, changed):
            if fail_fast and any(r.failed for r in results):
                results.append(StepResult(name, "not run"))
                continue
            try:
                stage = stage_dependent(eco, name, changed, workdir)
            except OSError as err:
                results.append(StepResult(name, "skipped", detail=str(err)))
                continue
            command = " && ".join(f"({c})" for c in check_commands(eco.projects[name]))
            results.append(run_step(name, command, stage, shim.env, echo))
    if keep or any(r.status != "passed" for r in results):
        return results, workdir
    shutil.rmtree(workdir, ignore_errors=True)
    return results, None


def scaffold_for(path: str, print_n=print, print_w=print):
    """Return the ``Scaffolder`` of the project at *path*, honouring its fobos ``[scaffold] skip``."""
    from .Scaffolder import Scaffolder, get_project_vars

    fobos = _read_fobos(os.path.join(path, "fobos"))
    return Scaffolder(
        get_project_vars(fobos=fobos, cwd=path),
        cwd=path,
        print_n=print_n,
        print_w=print_w,
        skip=fobos.get_scaffold_config()["skip"],
    )


def render_results(results: list[StepResult], color: bool = True) -> str:
    """
    Render the pass/fail summary of a multi-project run.

    Parameters
    ----------
    results : list[StepResult]
        One result per project.
    color : bool
        Use ANSI colours.
    """
    colours = {"passed": _GREEN, "failed": _RED, "crashed": _RED, "aborted": _RED, "skipped": _YELLOW, "not run": _DIM}
    width = max([len("Project"), *(len(r.name) for r in results)])

    def paint(text: str, colour: str) -> str:
        return f"{colour}{text}{_END}" if color and colour else text

    lines = [paint(f"{'Project'.ljust(width)}  {'Result'.ljust(8)}  {'Time':>8}  Detail", _BOLD)]
    for r in results:
        seconds = f"{r.seconds:7.1f}s" if r.status in ("passed", "failed", "crashed") else ""
        lines.append(
            f"{r.name.ljust(width)}  {paint(r.status.ljust(8), colours.get(r.status, ''))}  {seconds:>8}  {r.detail}".rstrip()
        )
    failed = [r.name for r in results if r.failed]
    passed = sum(r.status == "passed" for r in results)
    summary = f"{passed} passed, {len(failed)} failed" + (f": {', '.join(failed)}" if failed else "")
    lines.extend(["", paint(summary, _RED if failed else _GREEN)])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Release train (Phase 3)
# ---------------------------------------------------------------------------

RELEASE_SCRIPT = "scripts/release.sh"
_VERSION_RE = re.compile(r"^v?\d+\.\d+\.\d+$")


@dataclass
class ReleaseItem:
    """
    One project in a release plan.

    Attributes
    ----------
    name : str
        Project name.
    current : str
        Latest tag ('' for a first release).
    bump : str
        ``major``, ``minor``, ``patch`` or ``explicit`` (version given by the user).
    version : str
        Tag to create ('' when it cannot be computed: a blocker says why).
    releasable : int
        Releasable commits since ``current``.
    blockers : list[str]
        Reasons the project cannot be released now; any blocker stops the whole train.
    warnings : list[str]
        Conditions worth knowing that do not prevent the release.
    """

    name: str
    current: str
    bump: str
    version: str
    releasable: int
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def parse_bump_overrides(specs: list[str], eco: Ecosystem) -> dict[str, str]:
    """
    Parse ``NAME=major|minor|patch|vX.Y.Z`` overrides into ``{project: bump or version}``.

    Raises
    ------
    ValueError
        For a malformed spec, an unknown project or an invalid bump/version.
    """
    by_lower = {n.lower(): n for n in eco.projects}
    overrides: dict[str, str] = {}
    for spec in specs:
        name, sep, value = spec.partition("=")
        if not sep or not name.strip() or not value.strip():
            raise ValueError(f"malformed --bump {spec!r}: use NAME=major|minor|patch|vX.Y.Z")
        project = by_lower.get(name.strip().lower())
        if project is None:
            raise ValueError(f"unknown project {name.strip()!r} in --bump {spec!r}")
        value = value.strip()
        if value not in _BUMPS and not _VERSION_RE.match(value):
            raise ValueError(f"invalid bump {value!r} in --bump {spec!r}: use major, minor, patch or vX.Y.Z")
        overrides[project] = value
    return overrides


def _trunk(path: str) -> str:
    """Return the remote default branch of a repository ('' if unknown), as ``release.sh`` resolves it."""
    code, out = _git(path, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if code == 0 and out.startswith("origin/"):
        return out.removeprefix("origin/")
    for branch in ("master", "main"):
        if _git(path, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}")[0] == 0:
            return branch
    return ""


def plan_release(
    eco: Ecosystem,
    statuses: list[ProjectStatus],
    names: list[str] | None = None,
    overrides: dict[str, str] | None = None,
) -> list[ReleaseItem]:
    """
    Plan a release train: which projects to release, with which version, and what blocks them.

    A project is in the plan when it has releasable commits since its latest tag, or when an
    override names it. The plan follows the release order, so no project is released before one
    of its dependencies.

    Parameters
    ----------
    eco : Ecosystem
        The ecosystem.
    statuses : list[ProjectStatus]
        Fresh statuses (``Ecosystem.collect``; fetch first, so upstream and CI are current).
    names : list[str] | None
        Projects to consider, in release order (default: all).
    overrides : dict[str, str] | None
        ``{project: major|minor|patch|vX.Y.Z}`` replacing the suggested bump.
    """
    overrides = overrides or {}
    by_name = {s.name: s for s in statuses}
    no_cliff = shutil.which("git-cliff") is None
    plan: list[ReleaseItem] = []
    for name in names if names is not None else select(eco):
        status = by_name[name]
        override = overrides.get(name)
        if not status.releasable and not override:
            continue
        item = ReleaseItem(name, status.tag, "", "", status.releasable)
        if override and _VERSION_RE.match(override):
            item.bump, item.version = "explicit", override if override.startswith("v") else f"v{override}"
        else:
            item.bump = override or status.bump or "patch"
            if status.tag:
                with contextlib.suppress(ValueError):
                    item.version = bump_version(status.tag, item.bump)
        _release_checks(eco.projects[name], status, item, no_cliff)
        plan.append(item)
    return plan


def _release_checks(project: Project, status: ProjectStatus, item: ReleaseItem, no_cliff: bool) -> None:
    """Fill the blockers and warnings of a planned release."""
    if status.state == "error":
        item.blockers.extend(status.errors)
        return
    if not item.version:
        item.blockers.append("no previous tag: give the version with --bump NAME=vX.Y.Z")
    elif status.tag and Version(item.version) <= Version(status.tag):
        item.blockers.append(f"{item.version} is not above the current {status.tag}")
    elif _git(project.path, "rev-parse", "--verify", "--quiet", f"refs/tags/{item.version}")[0] == 0:
        item.blockers.append(f"tag {item.version} already exists")
    if not os.access(os.path.join(project.path, RELEASE_SCRIPT), os.X_OK):
        item.blockers.append(f"no executable {RELEASE_SCRIPT}")
    if no_cliff:
        item.blockers.append("git-cliff not found (release.sh needs it)")
    trunk = _trunk(project.path)
    if trunk and status.branch != trunk:
        item.blockers.append(f"on branch {status.branch}, not {trunk}")
    if status.dirty:
        item.blockers.append(f"working tree not clean ({status.dirty} changed)")
    if status.ahead is None:
        item.blockers.append("no upstream branch")
    elif status.behind:
        item.blockers.append(f"{status.behind} commit(s) behind the upstream: pull first")
    if status.ci == "failing":
        item.blockers.append("CI failing at HEAD")
    elif status.ci == "not pushed":
        item.warnings.append(f"{status.ahead} unpushed commit(s): pushed by the release, CI has not seen them")
    elif status.ci != "passing":
        item.warnings.append(f"CI at HEAD: {status.ci}")
    if not status.fetched:
        item.warnings.append("not fetched: upstream and CI may be out of date")
    if not project.slug:
        item.warnings.append("not on GitHub: the GitHub release cannot be awaited")


def render_plan(plan: list[ReleaseItem], color: bool = True) -> str:
    """Render a release plan for the terminal."""

    def paint(text: str, colour: str) -> str:
        return f"{colour}{text}{_END}" if color else text

    if not plan:
        return "Nothing to release: no project has releasable commits."
    width = max(len(i.name) for i in plan)
    lines = [paint("Release plan (dependencies first)", _BOLD)]
    for n, item in enumerate(plan, 1):
        target = f"{item.current or '(none)'} -> {item.version or '?'}"
        why = f"{item.bump}, {item.releasable} releasable commit(s)" if item.bump != "explicit" else "explicit version"
        mark = paint("BLOCKED", _RED) if item.blockers else paint("ready", _GREEN)
        lines.append(f"  {n:>2}. {item.name.ljust(width)}  {target:<22}  {mark}  ({why})")
        lines.extend(paint(f"        x {b}", _RED) for b in item.blockers)
        lines.extend(paint(f"        ! {w}", _YELLOW) for w in item.warnings)
    return "\n".join(lines)


def github_release_published(slug: str, tag: str) -> bool:
    """Return True when the GitHub release of *tag* exists and is not a draft."""
    code, out = _run(["gh", "release", "view", tag, "-R", slug, "--json", "tagName,isDraft"])
    if code:
        return False
    try:
        return not json.loads(out).get("isDraft", True)
    except json.JSONDecodeError:
        return False


def wait_github_release(slug: str, tag: str, timeout: float, interval: float = 15.0, echo=print) -> bool:
    """Poll until the GitHub release of *tag* is published; False after *timeout* seconds."""
    deadline = time.monotonic() + timeout
    echo(f"    waiting for the GitHub release {slug} {tag} (up to {int(timeout)}s)...")
    while True:
        if github_release_published(slug, tag):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval)


def run_release_train(
    eco: Ecosystem,
    plan: list[ReleaseItem],
    yes: bool = False,
    wait: bool = True,
    timeout: float = 900.0,
    interval: float = 15.0,
    echo=print,
) -> list[StepResult]:
    """
    Release the planned projects in order, stopping at the first failure.

    For each project: run ``scripts/release.sh <version>`` (its own confirmation prompt is left to
    the user unless *yes*); verify the tag exists locally and on the remote (``release.sh`` exits 0
    when its prompt is declined); wait for the GitHub release; then ``fobis fetch --update`` in its
    direct dependents, so that they build against the new release.

    Returns
    -------
    list[StepResult]
        One result per planned project (``passed`` = released), ``not run`` after a failure.
    """
    results: list[StepResult] = []
    with FobisShim() as shim:
        for item in plan:
            if any(r.status != "passed" for r in results):
                results.append(StepResult(item.name, "not run"))
                continue
            project = eco.projects[item.name]
            command = f"./{RELEASE_SCRIPT} {shlex.quote(item.version)}"
            result = run_step(item.name, command, project.path, shim.env, echo, input_text="y\n" if yes else None)
            if result.status == "passed":
                result = _verify_release(project, item, result, wait, timeout, interval, echo)
            if result.status == "passed":
                dependents = eco.dependents(item.name)
                failed = [r.name for r in (fetch_all(eco, dependents, echo=echo) if dependents else []) if r.failed]
                if failed:
                    detail = f"released {item.version}; fetch failed in {', '.join(failed)}"
                    result = StepResult(item.name, "failed", 0, result.seconds, detail)
            results.append(result)
    return results


def _verify_release(
    project: Project, item: ReleaseItem, result: StepResult, wait: bool, timeout: float, interval: float, echo
) -> StepResult:
    """Check that release.sh really tagged and pushed, then wait for the GitHub release."""
    tag = item.version
    if _git(project.path, "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}")[0]:
        return StepResult(item.name, "aborted", result.returncode, result.seconds, f"{tag} not created (declined?)")
    code, out = _git(project.path, "ls-remote", "--tags", "origin", f"refs/tags/{tag}")
    if code or not out:
        return StepResult(
            item.name, "failed", result.returncode, result.seconds, f"{tag} created but not on the remote"
        )
    if wait and project.slug and shutil.which("gh"):
        if not wait_github_release(project.slug, tag, timeout, interval, echo):
            detail = f"{tag} pushed; GitHub release not published in {int(timeout)}s"
            return StepResult(item.name, "failed", 0, result.seconds, detail)
        return StepResult(item.name, "passed", 0, result.seconds, f"released {tag}")
    return StepResult(item.name, "passed", 0, result.seconds, f"{tag} pushed (GitHub release not awaited)")


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

_GREEN, _YELLOW, _RED, _DIM, _BOLD, _END = "\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"
_HEADERS = ["Project", "Branch", "Tree", "Upstream", "Version / tag", "Unreleased", "CI", "Drift", "Pins"]


def _cells(status: ProjectStatus) -> list[tuple[str, str]]:
    """Return the ``(text, colour)`` cells of a dashboard row (name and error only for an unreadable project)."""
    if status.state == "error":
        return [(status.name, _RED), ("; ".join(status.errors), _RED)]
    tree = ("clean", _GREEN) if not status.dirty else (f"{status.dirty} changed", _YELLOW)
    if status.ahead is None:
        upstream = ("no upstream", _YELLOW)
    elif status.ahead or status.behind:
        upstream = (f"+{status.ahead}/-{status.behind}", _YELLOW)
    else:
        upstream = ("in sync", _GREEN)
    version_ok = bool(status.version) and status.version.lstrip("v") == status.tag.lstrip("v")
    version = (f"{status.version or '-'} / {status.tag or '-'}", "" if version_ok else _YELLOW)
    target = f" -> {status.next_version}" if status.next_version else ""
    if not status.unreleased:
        unreleased = ("0", _GREEN)
    elif not status.releasable:
        unreleased = (f"{status.unreleased}, none to release", _GREEN)
    elif status.releasable < status.unreleased:
        unreleased = (f"{status.unreleased}, {status.releasable} to release ({status.bump}{target})", _YELLOW)
    else:
        unreleased = (f"{status.unreleased} ({status.bump}{target})", _YELLOW)
    ci_colour = {"passing": _GREEN, "failing": _RED, "running": _YELLOW, "not pushed": _YELLOW}.get(status.ci, _DIM)
    drift = ("?", _DIM) if status.drift is None else (str(status.drift), _YELLOW if status.drift else _GREEN)
    bad_pins = [p for p in status.pins if p.state != "current"]
    if not status.pins:
        pins = ("-", _DIM)
    elif bad_pins:
        severe = any(p.state in ("stale", "diverged", "unlocked") for p in bad_pins)
        pins = (", ".join(f"{p.dep} {p.state}" for p in bad_pins), _RED if severe else _YELLOW)
    else:
        pins = ("current", _GREEN)
    return [
        (status.name, _BOLD),
        (status.branch, ""),
        tree,
        upstream,
        version,
        unreleased,
        (status.ci, ci_colour),
        drift,
        pins,
    ]


def _notes(statuses: list[ProjectStatus]) -> list[str]:
    """Return the per-project problems shown below the table."""
    notes = [f"{s.name}: {e}" for s in statuses if s.state != "error" for e in s.errors]
    if statuses and not any(s.fetched for s in statuses):
        notes.append("not fetched: upstream, CI and pins reflect the last fetch")
    return notes


def render_table(statuses: list[ProjectStatus], color: bool = True) -> str:
    """
    Render the dashboard as a terminal table.

    Parameters
    ----------
    statuses : list[ProjectStatus]
        One status per project.
    color : bool
        Use ANSI colours.
    """
    rows = [_cells(s) for s in statuses]
    widths = [len(h) for h in _HEADERS]
    for row in rows:
        if len(row) == len(_HEADERS):
            for i, (text, _) in enumerate(row):
                widths[i] = max(widths[i], len(text))

    def paint(text: str, colour: str) -> str:
        return f"{colour}{text}{_END}" if color and colour else text

    lines = ["  ".join(paint(h.ljust(w), _BOLD) for h, w in zip(_HEADERS, widths, strict=True)).rstrip()]
    lines.append("  ".join("-" * w for w in widths))
    for row in rows:
        if len(row) != len(_HEADERS):  # unreadable project: the error spans the row
            lines.append(f"{paint(row[0][0].ljust(widths[0]), row[0][1])}  {paint(row[1][0], row[1][1])}")
            continue
        lines.append("  ".join(paint(t.ljust(w), c) for (t, c), w in zip(row, widths, strict=True)).rstrip())
    notes = _notes(statuses)
    if notes:
        lines.append("")
        lines.extend(paint(f"note: {n}", _YELLOW) for n in notes)
    return "\n".join(lines)


def render_graph(eco: Ecosystem, color: bool = True) -> str:
    """
    Render the release order and the dependency tree for the terminal.

    Parameters
    ----------
    eco : Ecosystem
        The ecosystem.
    color : bool
        Use ANSI colours.
    """

    def bold(text: str) -> str:
        return f"{_BOLD}{text}{_END}" if color else text

    levels, cycle = eco.levels()
    lines = [bold("Release order (dependencies first)")]
    n = 0
    for depth, level in enumerate(levels):
        for name in level:
            n += 1
            lines.append(f"  {n:>2}. {name}  (level {depth})")
    if cycle:
        lines.append(f"  dependency cycle, not ordered: {', '.join(cycle)}")
    lines.extend(["", bold("Dependency tree")])
    roots = [p.name for p in eco.projects.values() if not eco.dependents(p.name)] or list(eco.projects)
    expanded: set[str] = set()
    marked = False

    def walk(name: str, prefix: str, last: bool, top: bool, stack: tuple[str, ...]) -> None:
        nonlocal marked
        connector = "" if top else ("`-- " if last else "|-- ")
        if name in stack:
            lines.append(f"{prefix}{connector}{name} (cycle)")
            return
        deps = eco.projects[name].deps
        if name in expanded and deps:
            lines.append(f"{prefix}{connector}{name} (*)")
            marked = True
            return
        lines.append(f"{prefix}{connector}{name}")
        expanded.add(name)
        child_prefix = prefix if top else prefix + ("    " if last else "|   ")
        for i, dep in enumerate(deps):
            walk(dep, child_prefix, i == len(deps) - 1, False, (*stack, name))

    for root in roots:
        walk(root, "", True, True, ())
    if marked:
        lines.append("(*) dependencies shown above")
    externals = sorted({e for p in eco.projects.values() for e in p.external})
    if externals:
        lines.extend(["", f"External dependencies (not managed): {', '.join(externals)}"])
    lines.extend(f"warning: {w}" for w in eco.warnings)
    return "\n".join(lines)


def dashboard_dict(eco: Ecosystem, statuses: list[ProjectStatus]) -> dict:
    """Return the dashboard as a JSON-ready dict."""
    graph = eco.graph_dict()
    return {
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "projects": [s.to_dict() for s in statuses],
        "levels": graph["levels"],
        "release_order": graph["release_order"],
        "cycle": graph["cycle"],
        "warnings": eco.warnings,
    }


# ---------------------------------------------------------------------------
# HTML themes
# ---------------------------------------------------------------------------

# Popular palettes, each with a light and a dark variant (the official ones where the palette
# defines both; Nord's light variant is its Snow Storm/Polar Night inversion). Keys: background,
# raised surface (table header, diagram box), text, secondary text, links and four status accents.
# A missing ``surface`` is derived from bg/fg; the page darkens (light variants) or lightens (dark
# variants) the secondary, link and status colours, keeping their hue, until they reach a 4.5:1
# contrast with ``bg``. The body text ``fg`` is left as the palette defines it.
THEMES: dict[str, dict] = {
    "github": {
        "label": "GitHub",
        "light": {
            "bg": "#ffffff",
            "surface": "#f6f8fa",
            "fg": "#1f2328",
            "muted": "#656d76",
            "link": "#0969da",
            "green": "#1a7f37",
            "yellow": "#9a6700",
            "orange": "#bc4c00",
            "red": "#cf222e",
        },
        "dark": {
            "bg": "#0d1117",
            "surface": "#161b22",
            "fg": "#e6edf3",
            "muted": "#8d96a0",
            "link": "#4493f8",
            "green": "#3fb950",
            "yellow": "#d29922",
            "orange": "#db6d28",
            "red": "#f85149",
        },
    },
    "solarized": {
        "label": "Solarized",
        "light": {
            "bg": "#fdf6e3",
            "surface": "#eee8d5",
            "fg": "#657b83",
            "muted": "#93a1a1",
            "link": "#268bd2",
            "green": "#859900",
            "yellow": "#b58900",
            "orange": "#cb4b16",
            "red": "#dc322f",
        },
        "dark": {
            "bg": "#002b36",
            "surface": "#073642",
            "fg": "#839496",
            "muted": "#586e75",
            "link": "#268bd2",
            "green": "#859900",
            "yellow": "#b58900",
            "orange": "#cb4b16",
            "red": "#dc322f",
        },
    },
    "dracula": {
        "label": "Dracula / Alucard",
        "light": {
            "bg": "#fffbeb",
            "fg": "#1f1f1f",
            "muted": "#6c664b",
            "link": "#644ac9",
            "green": "#14710a",
            "yellow": "#846e15",
            "orange": "#a34d14",
            "red": "#cb3a2a",
        },
        "dark": {
            "bg": "#282a36",
            "surface": "#44475a",
            "fg": "#f8f8f2",
            "muted": "#6272a4",
            "link": "#bd93f9",
            "green": "#50fa7b",
            "yellow": "#f1fa8c",
            "orange": "#ffb86c",
            "red": "#ff5555",
        },
    },
    "nord": {
        "label": "Nord",
        "light": {
            "bg": "#eceff4",
            "surface": "#e5e9f0",
            "fg": "#2e3440",
            "muted": "#4c566a",
            "link": "#5e81ac",
            "green": "#a3be8c",
            "yellow": "#ebcb8b",
            "orange": "#d08770",
            "red": "#bf616a",
        },
        "dark": {
            "bg": "#2e3440",
            "surface": "#3b4252",
            "fg": "#eceff4",
            "muted": "#d8dee9",
            "link": "#88c0d0",
            "green": "#a3be8c",
            "yellow": "#ebcb8b",
            "orange": "#d08770",
            "red": "#bf616a",
        },
    },
    "tokyo-night": {
        "label": "Tokyo Night / Day",
        "light": {
            "bg": "#e1e2e7",
            "surface": "#d5d6db",
            "fg": "#3760bf",
            "muted": "#6172b0",
            "link": "#2e7de9",
            "green": "#587539",
            "yellow": "#8c6c3e",
            "orange": "#b15c00",
            "red": "#f52a65",
        },
        "dark": {
            "bg": "#1a1b26",
            "surface": "#24283b",
            "fg": "#c0caf5",
            "muted": "#a9b1d6",
            "link": "#7aa2f7",
            "green": "#9ece6a",
            "yellow": "#e0af68",
            "orange": "#ff9e64",
            "red": "#f7768e",
        },
    },
    "catppuccin": {
        "label": "Catppuccin Latte / Mocha",
        "light": {
            "bg": "#eff1f5",
            "surface": "#e6e9ef",
            "fg": "#4c4f69",
            "muted": "#6c6f85",
            "link": "#1e66f5",
            "green": "#40a02b",
            "yellow": "#df8e1d",
            "orange": "#fe640b",
            "red": "#d20f39",
        },
        "dark": {
            "bg": "#1e1e2e",
            "surface": "#313244",
            "fg": "#cdd6f4",
            "muted": "#a6adc8",
            "link": "#89b4fa",
            "green": "#a6e3a1",
            "yellow": "#f9e2af",
            "orange": "#fab387",
            "red": "#f38ba8",
        },
    },
    "gruvbox": {
        "label": "Gruvbox",
        "light": {
            "bg": "#fbf1c7",
            "surface": "#ebdbb2",
            "fg": "#3c3836",
            "muted": "#7c6f64",
            "link": "#076678",
            "green": "#79740e",
            "yellow": "#b57614",
            "orange": "#af3a03",
            "red": "#9d0006",
        },
        "dark": {
            "bg": "#282828",
            "surface": "#3c3836",
            "fg": "#ebdbb2",
            "muted": "#a89984",
            "link": "#83a598",
            "green": "#b8bb26",
            "yellow": "#fabd2f",
            "orange": "#fe8019",
            "red": "#fb4934",
        },
    },
    "one": {
        "label": "One Light / Dark",
        "light": {
            "bg": "#fafafa",
            "surface": "#f0f0f0",
            "fg": "#383a42",
            "muted": "#696c77",
            "link": "#4078f2",
            "green": "#50a14f",
            "yellow": "#c18401",
            "orange": "#986801",
            "red": "#e45649",
        },
        "dark": {
            "bg": "#282c34",
            "surface": "#21252b",
            "fg": "#abb2bf",
            "muted": "#7f848e",
            "link": "#61afef",
            "green": "#98c379",
            "yellow": "#e5c07b",
            "orange": "#d19a66",
            "red": "#e06c75",
        },
    },
    "rose-pine": {
        "label": "Rose Pine / Dawn",
        "light": {
            "bg": "#faf4ed",
            "surface": "#f2e9e1",
            "fg": "#575279",
            "muted": "#797593",
            "link": "#907aa9",
            "green": "#286983",
            "yellow": "#ea9d34",
            "orange": "#d7827e",
            "red": "#b4637a",
        },
        "dark": {
            "bg": "#191724",
            "surface": "#1f1d2e",
            "fg": "#e0def4",
            "muted": "#908caa",
            "link": "#c4a7e7",
            "green": "#9ccfd8",
            "yellow": "#f6c177",
            "orange": "#ebbcba",
            "red": "#eb6f92",
        },
    },
}
DEFAULT_THEME = "github"
MODES = ("auto", "light", "dark")


# ---------------------------------------------------------------------------
# HTML renderer
# ---------------------------------------------------------------------------


def mermaid(eco: Ecosystem, statuses: list[ProjectStatus]) -> str:
    """
    Return the Mermaid source of the dependency diagram (dependency --> dependent).

    Every node carries the class of its project's state (``ok``, ``unreleased``, ``stale``,
    ``ci_failing``, ``error``); the page appends the ``classDef`` lines of the active palette.
    """
    state = {s.name: s.state for s in statuses}
    ids = {name: f"p{i}" for i, name in enumerate(eco.projects)}
    lines = ["graph LR"]
    for name, node in ids.items():
        lines.append(f'  {node}["{name}"]:::{state.get(name, "ok").replace("-", "_")}')
    for project in eco.projects.values():
        lines.extend(f"  {ids[dep]} --> {ids[project.name]}" for dep in project.deps)
    return "\n".join(lines)


def render_html(eco: Ecosystem, statuses: list[ProjectStatus], theme: str = DEFAULT_THEME, mode: str = "auto") -> str:
    """
    Render the dashboard as a self-contained HTML page.

    Parameters
    ----------
    eco : Ecosystem
        The ecosystem.
    statuses : list[ProjectStatus]
        One status per project.
    theme : str
        Initial palette, a key of ``THEMES``; the page lets the reader switch it.
    mode : str
        Initial mode: ``auto`` (follow the system), ``light`` or ``dark``.

    Raises
    ------
    ValueError
        For an unknown theme or mode.

    Notes
    -----
    Mermaid is loaded from a CDN to draw the diagram; without network the page still shows the
    table and the diagram source. Without JavaScript the page falls back to the GitHub palette.
    """
    if theme not in THEMES:
        raise ValueError(f"unknown theme {theme!r}: choose one of {', '.join(THEMES)}")
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}: choose one of {', '.join(MODES)}")
    esc = html.escape
    classes = {_GREEN: "good", _YELLOW: "warn", _RED: "bad", _DIM: "dim"}
    rows = []
    for s in statuses:
        cells = _cells(s)
        name = f"<strong>{esc(s.name)}</strong>"
        if s.slug:
            base = f"https://github.com/{esc(s.slug)}"
            name = (
                f'<a href="{base}"><strong>{esc(s.name)}</strong></a><div class="links">'
                f'<a href="{base}/actions">actions</a> &middot; <a href="{base}/releases">releases</a></div>'
            )
        if len(cells) != len(_HEADERS):
            rows.append(
                f'<tr><td>{name}</td><td class="bad" colspan="{len(_HEADERS) - 1}">{esc(cells[1][0])}</td></tr>'
            )
            continue
        tds = [f"<td>{name}</td>"]
        tds.extend(f'<td class="{classes.get(colour, "")}">{esc(text)}</td>' for text, colour in cells[1:])
        rows.append(f"<tr>{''.join(tds)}</tr>")
    notes = "".join(f"<li>{esc(n)}</li>" for n in _notes(statuses))
    source = mermaid(eco, statuses)
    data = {"themes": THEMES, "theme": theme, "mode": mode, "mermaid": source}
    replacements = {
        "@@GENERATED@@": esc(datetime.datetime.now().strftime("%Y-%m-%d %H:%M")),
        "@@HEAD@@": "".join(f"<th>{esc(h)}</th>" for h in _HEADERS),
        "@@ROWS@@": "\n".join(rows),
        "@@NOTES@@": f'<ul class="notes">{notes}</ul>' if notes else "",
        "@@ORDER@@": " &rarr; ".join(esc(n) for n in eco.release_order()),
        "@@THEME_OPTIONS@@": "".join(f'<option value="{esc(k)}">{esc(v["label"])}</option>' for k, v in THEMES.items()),
        "@@MERMAID@@": esc(source),
        # JSON inside <script>: "</" must not close the element.
        "@@DATA@@": json.dumps(data).replace("</", "<\\/"),
    }
    page = _HTML_PAGE
    for key, value in replacements.items():
        page = page.replace(key, value)
    return page


# Placeholders are @@NAME@@ (filled by render_html), so the CSS and JavaScript braces stay literal.
_HTML_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fortran Ecosystem Dashboard</title>
<style>
:root { color-scheme: light dark;
  --bg:#ffffff; --surface:#f6f8fa; --fg:#1f2328; --muted:#656d76; --line:#d0d7de; --link:#0969da;
  --good:#1a7f37; --warn:#9a6700; --stale:#bc4c00; --bad:#cf222e; }
@media (prefers-color-scheme: dark) { :root {
  --bg:#0d1117; --surface:#161b22; --fg:#e6edf3; --muted:#8d96a0; --line:#30363d; --link:#4493f8;
  --good:#3fb950; --warn:#d29922; --stale:#db6d28; --bad:#f85149; } }
body { background:var(--bg); color:var(--fg); font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;
  margin:0 auto; padding:24px 16px; max-width:1200px; transition:background .15s,color .15s; }
header { display:flex; flex-wrap:wrap; gap:8px 24px; align-items:flex-end; justify-content:space-between; margin-bottom:16px; }
h1 { font-size:22px; margin:0 0 4px; }
h2 { font-size:17px; margin:28px 0 8px; }
.meta { color:var(--muted); margin:0; }
.controls { display:flex; gap:12px; flex-wrap:wrap; }
.controls label { color:var(--muted); font-size:13px; display:flex; gap:6px; align-items:center; }
select { background:var(--surface); color:var(--fg); border:1px solid var(--line); border-radius:6px;
  padding:4px 8px; font:inherit; font-size:13px; }
.scroll { overflow-x:auto; }
table { border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums; }
th, td { text-align:left; padding:6px 10px; border-bottom:1px solid var(--line); white-space:nowrap; vertical-align:top; }
th { background:var(--surface); font-weight:600; }
a { color:var(--link); text-decoration:none; }
a:hover { text-decoration:underline; }
.links { font-size:12px; }
.good { color:var(--good); }
.warn { color:var(--warn); }
.bad { color:var(--bad); font-weight:600; }
.dim { color:var(--muted); }
.notes { color:var(--warn); }
.legend { display:flex; flex-wrap:wrap; gap:6px; margin:0 0 10px; }
.legend span { padding:1px 10px; border-radius:4px; border:1px solid var(--line); }
.diagram { background:var(--surface); border:1px solid var(--line); border-radius:6px; padding:12px; overflow-x:auto; }
.diagram svg { max-width:100%; height:auto; }
pre.source { margin:0; color:var(--muted); }
</style>
</head>
<body>
<header>
<div>
<h1>Fortran ecosystem</h1>
<p class="meta">Generated @@GENERATED@@ by <code>fobis ecosystem dashboard</code></p>
</div>
<div class="controls">
<label>Theme <select id="theme">@@THEME_OPTIONS@@</select></label>
<label>Mode <select id="mode"><option value="auto">auto</option><option value="light">light</option><option
value="dark">dark</option></select></label>
</div>
</header>
<div class="scroll"><table>
<thead><tr>@@HEAD@@</tr></thead>
<tbody>
@@ROWS@@
</tbody>
</table></div>
@@NOTES@@
<h2>Release order</h2>
<p>@@ORDER@@</p>
<h2>Dependencies</h2>
<p class="legend"><span data-state="ok">up to date</span><span data-state="unreleased">changes to release</span><span
data-state="stale">stale pins</span><span data-state="ci_failing">CI failing</span><span data-state="error">unreadable</span></p>
<div class="diagram"><div id="diagram"></div><pre class="source" id="diagram-source">@@MERMAID@@</pre></div>
<script type="application/json" id="eco-data">@@DATA@@</script>
<script type="module">
const DATA = JSON.parse(document.getElementById("eco-data").textContent);
const THEMES = DATA.themes;
const MERMAID_URL = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
const store = {
  get(key) { try { return localStorage.getItem(key); } catch (e) { return null; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* storage unavailable */ } },
};
let theme = store.get("fobis-ecosystem-theme");
if (!(theme in THEMES)) theme = DATA.theme;
let mode = store.get("fobis-ecosystem-mode");
if (!["auto", "light", "dark"].includes(mode)) mode = DATA.mode;
const media = window.matchMedia("(prefers-color-scheme: dark)");

const rgb = (c) => [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16));
const hex = (v) => "#" + v.map((x) => Math.round(x).toString(16).padStart(2, "0")).join("");
// mix(a, b, t): t of a, 1 - t of b
const mix = (a, b, t) => { const x = rgb(a), y = rgb(b); return hex(x.map((v, i) => v * t + y[i] * (1 - t))); };
const luminance = (c) => rgb(c).map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; })
  .reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0);
const contrast = (a, b) => { const [hi, lo] = [luminance(a), luminance(b)].sort((p, q) => q - p); return (hi + 0.05) / (lo + 0.05); };
// Darken (light bg) or lighten (dark bg) a text colour until it reaches the given contrast with bg,
// keeping its hue: mixing towards fg instead would turn every status colour into the same grey.
const readable = (c, bg, min = 4.5) => {
  const ink = luminance(bg) > 0.4 ? "#000000" : "#ffffff";
  let out = c;
  for (let t = 0.95; contrast(out, bg) < min && t > -0.01; t -= 0.05) out = mix(c, ink, Math.max(t, 0));
  return out;
};

let mermaidLib = null, renders = 0;
async function drawDiagram(p, dark, colors, accents) {
  const box = document.getElementById("diagram"), source = document.getElementById("diagram-source");
  if (!mermaidLib) {
    try { mermaidLib = (await import(MERMAID_URL)).default; } catch (e) { source.hidden = false; return; }
  }
  const classDefs = Object.entries(accents).map(([state, accent]) =>
    `  classDef ${state} fill:${mix(accent, p.bg, dark ? 0.3 : 0.2)},stroke:${accent},color:${p.fg},stroke-width:1.5px`);
  mermaidLib.initialize({ startOnLoad: false, securityLevel: "strict", theme: "base", themeVariables: {
    background: colors.surface, primaryColor: colors.surface, primaryTextColor: p.fg, primaryBorderColor: colors.line,
    lineColor: colors.muted, fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif", fontSize: "14px" } });
  const id = ++renders;
  try {
    const { svg } = await mermaidLib.render(`ecosystem-graph-${id}`, DATA.mermaid + "\\n" + classDefs.join("\\n"));
    if (id !== renders) return;  // a newer theme change is already drawing
    box.innerHTML = svg;
    source.hidden = true;
  } catch (e) { source.hidden = false; }
}

function apply() {
  const dark = mode === "dark" || (mode === "auto" && media.matches);
  const p = THEMES[theme][dark ? "dark" : "light"];
  const colors = {
    bg: p.bg, surface: p.surface || mix(p.fg, p.bg, 0.06), fg: p.fg, line: mix(p.fg, p.bg, 0.18),
    muted: readable(p.muted, p.bg), link: readable(p.link, p.bg),
    good: readable(p.green, p.bg), warn: readable(p.yellow, p.bg),
    stale: readable(p.orange, p.bg), bad: readable(p.red, p.bg),
  };
  const root = document.documentElement;
  for (const [name, value] of Object.entries(colors)) root.style.setProperty(`--${name}`, value);
  root.style.colorScheme = dark ? "dark" : "light";
  const accents = { ok: p.green, unreleased: p.yellow, stale: p.orange, ci_failing: p.red, error: colors.muted };
  for (const chip of document.querySelectorAll(".legend span")) {
    const accent = accents[chip.dataset.state];
    chip.style.background = mix(accent, p.bg, dark ? 0.3 : 0.2);
    chip.style.borderColor = accent;
    chip.style.color = p.fg;
  }
  drawDiagram(p, dark, colors, accents);
}

const themeSelect = document.getElementById("theme"), modeSelect = document.getElementById("mode");
themeSelect.value = theme;
modeSelect.value = mode;
themeSelect.addEventListener("change", () => { theme = themeSelect.value; store.set("fobis-ecosystem-theme", theme); apply(); });
modeSelect.addEventListener("change", () => { mode = modeSelect.value; store.set("fobis-ecosystem-mode", mode); apply(); });
media.addEventListener("change", () => { if (mode === "auto") apply(); });
apply();
</script>
</body>
</html>
"""
