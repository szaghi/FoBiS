"""new.py — ``fobis new``: a ready-to-build project (issue #206 step 8).

A module in ``src/``, a program in ``app/`` (none with ``--lib``), a test in ``test/``, a fobos with debug and release
modes (FoBiS build profiles, so any compiler family works) and a ``[test]`` section, a ``.gitignore`` and a git
repository with nothing committed. The templates are package data read with ``importlib.resources``, so they load from
the zipapp too. Nothing is ever overwritten: a file that exists stops the command before anything is written.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from importlib.resources import files
from typing import Any

NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,62}$")  # a Fortran name: a letter, then letters, digits, _ (63 at most)

# template -> path in the project ({name} replaced); the library's has no program
FILES = {"module.f90": "src/{name}.f90", "main.f90": "app/main.f90", "test.f90": "test/test_{name}.f90"}
LIB_FILES = {"module.f90": "src/{name}.f90", "test.f90": "test/test_{name}.f90"}


class NewError(Exception):
    """The project cannot be created: an invalid name, or files that exist (``conflicts``)."""

    def __init__(self, message: str, conflicts: list[str] | None = None) -> None:
        super().__init__(message)
        self.conflicts = conflicts or []


@dataclass
class Created:
    """What ``create`` wrote."""

    root: str
    name: str
    files: list[str] = field(default_factory=list)
    git: str = ""  # "initialised", "inside an existing repository" or why not


def templates_root() -> Any:
    """The templates (a Traversable: a directory, or a path inside the zipapp)."""
    return files("fobis") / "templates" / "new"


def _render(template: str, values: dict[str, str]) -> str:
    text = (templates_root() / template).read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace(f"@@{key}@@", value)
    return text


def git_author(cwd: str = ".") -> str:
    """``Name <email>`` from ``git config`` (what is set of the two; empty without git)."""

    def config(key: str) -> str:
        try:
            result = subprocess.run(["git", "config", key], cwd=cwd, capture_output=True, text=True, check=False)
        except OSError:
            return ""
        return result.stdout.strip()

    name, email = config("user.name"), config("user.email")
    return f"{name} <{email}>" if name and email else name or email


def project_name(path: str, name: str | None = None) -> str:
    """The project's Fortran name: *name*, else the directory's; `NewError` when it is not a Fortran name."""
    name = name or os.path.basename(os.path.abspath(path))
    if not NAME.match(name):
        if not name:
            raise NewError("no project name: give one with --name")
        fixed = re.sub(r"\W", "_", name)
        hint = f", for example --name {fixed}" if NAME.match(fixed) else ""
        raise NewError(
            f"{name!r} is not a Fortran name (a letter, then letters, digits or _): give one with --name{hint}"
        )
    return name


def plan(path: str, name: str | None = None, lib: bool = False, compiler: str = "gnu") -> dict[str, str]:
    """{relative path: content} of the project at *path*, named *name* (default: the directory's name)."""
    root = os.path.abspath(path)
    name = project_name(path, name)
    existing = root
    while not os.path.isdir(existing):  # git config is read where git would read it: the nearest directory
        existing = os.path.dirname(existing)
    author = git_author(existing)
    values = {"NAME": name, "COMPILER": compiler, "AUTHORS": f"authors = {author}\n" if author else ""}
    layout = {template: target.format(name=name) for template, target in (LIB_FILES if lib else FILES).items()}
    layout["fobos-lib" if lib else "fobos"] = "fobos"
    layout["gitignore"] = ".gitignore"
    return {target: _render(template, values) for template, target in layout.items()}


def conflicts(path: str, contents: dict[str, str]) -> list[str]:
    """The files of *contents* that exist under *path*."""
    return sorted(target for target in contents if os.path.lexists(os.path.join(path, target)))


def create(path: str, name: str | None = None, lib: bool = False, compiler: str = "gnu", git: bool = True) -> Created:
    """Write the project at *path* (created if missing); raises `NewError` before writing anything when a file
    exists or the name is invalid. With *git*, ``git init`` unless *path* is inside a repository already; nothing is
    committed."""
    contents = plan(path, name, lib, compiler)
    existing = conflicts(path, contents)
    if existing:
        raise NewError(f"{len(existing)} file(s) exist, nothing written", existing)
    root = os.path.abspath(path)
    created = Created(root, project_name(path, name))
    for target, text in contents.items():
        full = os.path.join(root, target)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "x", encoding="utf-8") as handle:  # "x": never replace a file that appeared meanwhile
            handle.write(text)
        created.files.append(target)
    created.git = _git_init(root) if git else "not initialised (--no-git)"
    return created


def _git_init(root: str) -> str:
    try:
        inside = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"], cwd=root, capture_output=True, text=True, check=False
        )
    except OSError:
        return "not initialised: git is not installed"
    if inside.returncode == 0 and inside.stdout.strip() == "true":
        return "inside an existing repository: not initialised"
    result = subprocess.run(["git", "init", "-q"], cwd=root, capture_output=True, text=True, check=False)
    return "initialised" if result.returncode == 0 else f"not initialised: {result.stderr.strip()}"
