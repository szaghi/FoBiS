"""compile_commands.py — the compilation database of a build (``compile_commands.json``).

One entry per source file of the build, ``{directory, file, arguments, output}``: the directory the command runs in,
the source, the exact compile command (split into words) and the object it writes. Editors, language servers and
static analysers read it to learn how each file is compiled: include paths, module directory, macros, flags.

Opt-in (mode key ``compile_commands = True`` or ``--compile-commands``): a new file in every project's root would
make clean-tree checks fail (release scripts, ``fobis ecosystem release``) until each ``.gitignore`` names it.
``fobis introspect --compile-commands`` prints the database of any project without writing it.

The database is written in the build directory after the dependency analysis (which adds the include directories of
the included files), before anything is compiled, so it exists even when the build fails. When the build directory
is not the project root, ``./compile_commands.json`` is a relative link to it (a copy where links are unavailable):
most tools look for the database there. Builds kept under ``.fobis/`` (shadow builds, build variants, runs) write
their own database and leave the root alone.
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

import json
import os
import shlex
import shutil
import tempfile
from collections.abc import Callable, Iterable

NAME = "compile_commands.json"
PRIVATE = ".fobis"
"""Builds whose directory is under this one never touch the project root's database."""


def entry(builder, pfile, directory: str) -> dict:
    """The database entry of *pfile*: the compile step of ``Builder._compile_command``.

    With a separate preprocessor (PreForM.py, ...) the compiler reads a temporary file: the entry names the original
    source instead, which is the file a tool has open.
    """
    steps = builder._compile_command(pfile)
    words = shlex.split(steps[-1][0])
    if len(steps) > 1:  # preprocessed first: the compile step reads the preprocessor's output
        _, preprocessed, _ = builder._compile_preprocessor(pfile)
        words = [pfile.name if word == preprocessed else word for word in words]
    output = os.path.join(builder.obj_dir, pfile.obj_name + ".o")
    return {
        "directory": directory,
        "file": os.path.normpath(os.path.join(directory, pfile.name)),
        "arguments": words,
        "output": os.path.normpath(os.path.join(directory, output)),
    }


def entries(builder, pfiles: Iterable, directory: str | None = None) -> list[dict]:
    """The entries of every compiled source of *pfiles* (included files have none), in the files' order."""
    directory = directory or os.getcwd()
    return [entry(builder, pfile, directory) for pfile in pfiles if not pfile.include]


def write(path: str, items: list[dict]) -> bool:
    """Write *items* to *path* atomically; True when the file changed (an unchanged database keeps its time)."""
    text = json.dumps(items, indent=2) + "\n"
    try:
        with open(path, encoding="utf-8") as handle:
            if handle.read() == text:
                return False
    except OSError:
        pass
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=folder, prefix=".compile_commands.", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.remove(temporary)
        raise
    return True


def _is_database_of(path: str, root: str) -> bool:
    """True when *path* is a regular file holding a compilation database of *root* (a copy FoBiS made)."""
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return False
    return isinstance(data, list) and all(isinstance(e, dict) and e.get("directory") == root for e in data)


def link_root(path: str, root: str, print_w: Callable[[str], object] | None = None) -> str | None:
    """Make ``<root>/compile_commands.json`` point to *path*; the root file, or None when left alone.

    A link, or a database of this root (the copy made where links are unavailable), is replaced; any other file of
    that name is the user's and is never touched.
    """
    target = os.path.join(root, NAME)
    if os.path.abspath(path) == os.path.abspath(target):
        return target
    relative = os.path.relpath(os.path.abspath(path), root)
    if os.path.islink(target):
        if os.readlink(target) == relative:
            return target
        os.remove(target)
    elif os.path.exists(target):
        if not _is_database_of(target, root):
            if print_w:
                print_w(
                    f"Warning: {target} is not FoBiS's compilation database: left untouched (the build's is {path})"
                )
            return None
        os.remove(target)
    try:
        os.symlink(relative, target)
    except (OSError, NotImplementedError):
        shutil.copyfile(path, target)
    return target


def remove(build_dir: str, root: str | None = None, print_w: Callable[[str], object] | None = None) -> list[str]:
    """Remove the database of *build_dir* and the root's link to it (or FoBiS's copy of it); the paths removed.

    ``fobis clean`` calls it: the database describes objects the clean removes, and a link left behind would dangle.
    """
    root = root or os.getcwd()
    path = os.path.join(build_dir, NAME)
    target = os.path.join(root, NAME)
    removed = []
    if os.path.abspath(path) != os.path.abspath(target):
        points_here = os.path.islink(target) and os.path.abspath(
            os.path.join(root, os.readlink(target))
        ) == os.path.abspath(path)
        copy = not os.path.islink(target) and os.path.isfile(target) and _is_database_of(target, root)
        if points_here or (copy and os.path.isfile(path) and _same_file_text(target, path)):
            os.remove(target)
            removed.append(target)
    if os.path.isfile(path):
        os.remove(path)
        removed.append(path)
    if print_w:
        for item in removed:
            print_w("Removing " + item)
    return removed


def _same_file_text(one: str, other: str) -> bool:
    try:
        with open(one, encoding="utf-8") as first, open(other, encoding="utf-8") as second:
            return first.read() == second.read()
    except OSError:
        return False


def update(
    cliargs,
    builder,
    pfiles: Iterable,
    print_w: Callable[[str], object] | None = None,
    accumulated: list[dict] | None = None,
) -> str | None:
    """Write the database of a build (when the mode sets ``compile_commands = True`` or with ``--compile-commands``)
    and link it from the root.

    *accumulated* collects the entries of several targets built in one run (``[target.NAME]`` sections): each call
    adds its new entries to it and writes them all. Returns the database's path, or None when disabled.
    """
    if not getattr(cliargs, "compile_commands", False):
        return None
    root = os.getcwd()
    path = os.path.join(builder.build_dir, NAME)
    items = entries(builder, pfiles, root)
    if accumulated is not None:
        accumulated.extend(item for item in items if item not in accumulated)
        items = accumulated
    write(path, items)
    if os.path.relpath(os.path.abspath(path), root).split(os.sep)[0] != PRIVATE:
        link_root(path, root, print_w)
    return path
