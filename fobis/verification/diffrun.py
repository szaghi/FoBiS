"""diffrun.py — differential execution: the cases run on a revision and on the working tree, compared (``fobis
diff-run``).

The revision is extracted with ``git archive`` (submodules at the commits the revision records), the working tree
is copied (tracked and untracked files, ignored ones excluded); the fetched dependencies of the working copy are
copied into both. Both are built and run in these scratch copies: the user's tree, build directories and
repository metadata are never written. The cases are those declared in the working tree's fobos; each quantity is
compared with the V2 comparator, with the case's tolerance. The source files and procedures that changed between
the two are listed, and with an assessment (V4) a difference is judged against the new version's own spread.
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

import io
import math
import os
import shutil
import subprocess
import tarfile
from dataclasses import dataclass, field
from typing import Any

from .verify import Reference, Verification, verify


class DiffRunError(Exception):
    """The revision cannot be resolved or extracted."""


def _git(root: str, *args: str, binary: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=not binary)


def resolve(root: str, ref: str) -> str:
    """The commit of *ref* in the repository at *root*."""
    done = _git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    if done.returncode != 0:
        raise DiffRunError(f"{ref!r} is not a revision of the repository at {os.path.abspath(root)}")
    return done.stdout.strip()


def _extract(root: str, commit: str, dst: str) -> None:
    done = _git(root, "archive", "--format=tar", commit, binary=True)
    if done.returncode != 0:
        raise DiffRunError(f"git archive {commit} failed: {done.stderr.decode(errors='replace').strip()}")
    os.makedirs(dst, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(done.stdout)) as archive:
        if hasattr(tarfile, "data_filter"):
            archive.extractall(dst, filter="data")
        else:  # pragma: no cover - Python without the extraction filters
            archive.extractall(dst)


def export_revision(root: str, commit: str, dst: str, notes: list[str]) -> None:
    """The tree of *commit* in *dst*, submodules at the commits it records (from the working copy's submodule
    repositories; one that cannot provide its commit is copied as it is, with a note)."""
    _extract(root, commit, dst)
    for line in _git(root, "ls-tree", "-r", commit).stdout.splitlines():
        meta, _, path = line.partition("\t")
        parts = meta.split()
        if len(parts) != 3 or parts[1] != "commit":
            continue
        sub, target = os.path.join(root, path), os.path.join(dst, path)
        if os.path.exists(os.path.join(sub, ".git")) and _git(sub, "cat-file", "-e", parts[2]).returncode == 0:
            export_revision(sub, parts[2], target, notes)
        elif os.path.isdir(sub) and os.listdir(sub):
            shutil.copytree(sub, target, symlinks=True, ignore=shutil.ignore_patterns(".git"), dirs_exist_ok=True)
            notes.append(f"submodule {path}: commit {parts[2][:12]} not available, its working copy used")
        else:
            notes.append(f"submodule {path}: not checked out, left empty")


def copy_dependencies(root: str, deps_dir: str, dst: str) -> bool:
    """The fetched dependencies of the working copy into *dst* (without ``.git``); False when there are none."""
    deps = os.path.join(root, deps_dir)
    if not os.path.isdir(deps):
        return False
    shutil.copytree(
        deps,
        os.path.join(dst, deps_dir),
        symlinks=True,
        ignore=shutil.ignore_patterns(".git"),
        dirs_exist_ok=True,  # partly tracked, e.g. src/third_party/CMakeLists.txt
    )
    return True


@dataclass
class ChangedFile:
    path: str
    status: str
    procedures: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"path": self.path, "status": self.status, "procedures": self.procedures}


def changed_files(root: str, commit: str) -> list[ChangedFile]:
    """The files that differ between *commit* and the working tree (untracked ones included, status ``?``), with the
    Fortran procedures whose code changed."""
    from ..ai.change import WORKTREE, Revision, file_change, staged_changes
    from ..ai.impact import git_in

    top = _git(root, "rev-parse", "--show-toplevel").stdout.strip() or os.path.abspath(root)
    git = git_in(top)
    revision = Revision((commit,), commit, WORKTREE, top)
    found = [
        ChangedFile(path, status, list(file_change(status, path, old, git, revision).procedures))
        for status, path, old in staged_changes(git, revision)
    ]
    untracked = _git(top, "ls-files", "--others", "--exclude-standard").stdout.splitlines()
    return found + [ChangedFile(path, "?") for path in untracked]


@dataclass
class CaseDiff:
    """One case on both sides."""

    verification: Verification
    old: Any = None  # the RunResult on the revision
    spread: dict[str, dict] = field(default_factory=dict)  # quantity -> digits, max_rel, within

    @property
    def status(self) -> str:
        """``equivalent``, ``within-uncertainty`` (every difference below the new version's own spread),
        ``differs``, ``new-failed`` (the working tree's run), ``old-failed`` (the revision's run)."""
        status = self.verification.status
        if status == "pass":
            return "equivalent"
        if status == "run-failed":
            return "new-failed"
        if status == "old-failed":
            return status
        failing = [c for c in self.verification.comparisons if not c.ok]
        if failing and all(self.spread.get(c.name, {}).get("within") for c in failing):
            return "within-uncertainty"
        return "differs"

    @property
    def ok(self) -> bool:
        return self.status in ("equivalent", "within-uncertainty")

    def to_dict(self) -> dict:
        data = self.verification.to_dict()
        data.pop("reference", None)
        data["status"] = self.status
        if self.old is not None and self.old.status != "ok":
            data["old_run"] = {
                "status": self.old.status,
                "exit_code": self.old.exit_code,
                "probe_errors": self.old.probe_errors,
                "stderr": "\n".join(self.old.stderr.splitlines()[-20:]),
            }
            if self.old.build is not None:
                data["old_run"]["build"] = self.old.build
        if self.spread:
            data["spread"] = self.spread
        return data


def compare(new: Any, old: Any, tolerance: dict[str, str]) -> CaseDiff:
    """The run on the working tree against the run on the revision (the revision plays the reference)."""
    if old.status != "ok":
        outcome = Verification(new.case, "old-failed", new, note=f"the run on the revision is {old.status}")
        return CaseDiff(outcome, old)
    reference = Reference(old.case, {q.name: q for q in old.quantities}, old.provenance)
    return CaseDiff(verify([new], reference, tolerance), old)


def judge(case_diff: CaseDiff, digits: dict[str, float]) -> None:
    """For each quantity with an assessed spread: whether its difference is below the new version's own spread
    (a relative difference under ``10**-digits`` is what the code produces anyway)."""
    for comparison in case_diff.verification.comparisons:
        if comparison.name not in digits:
            continue
        shared = digits[comparison.name]
        item: dict[str, Any] = {"digits": shared if math.isfinite(shared) else "inf", "max_rel": comparison.max_rel}
        if not comparison.ok:
            item["within"] = math.isfinite(shared) and comparison.max_rel <= 10.0 ** (-shared)
        case_diff.spread[comparison.name] = item
