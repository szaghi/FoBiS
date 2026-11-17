"""Stop the recompile cascade at unchanged module interfaces (issue #218, phase 4; opt-in ``interface_cutoff``).

FoBiS recompiles a file when any file it depends on, directly or not, changed: an edit of a procedure body in a
low-level module recompiles everything above it. Yet the module file the compiler writes (``.mod``) holds the
interface only: measured, gfortran 16.2 writes a byte-identical ``.mod`` after a body edit, nvfortran 26.9 one that
differs only in its third line (the date).

With ``interface_cutoff = true`` the ready queue compiles a file whose own source (and includes) did not change only
when the interface of a module in its dependency closure changed: the normalised digest of every module file is
recorded after each compile (``<obj_dir>/.fobis-interfaces.json``), together with the digests each file was compiled
against. The closure, not only the modules a file uses directly: an nvfortran ``.mod`` refers to the modules it uses
by name, so a type changed two modules down does not change the module in between.

Supported where the module file was measured: gfortran (``gnu``, ``opencoarrays-gnu``) and nvfortran (``nvfortran``,
``pgi``). Off when the flags ask for cross-file inlining or link-time optimisation of the host code (then an object
holds code of other modules' bodies): ``-flto``, ``-Mipa``, ``-Mextract``, ``-Minline=lib...``, ``-ipo``,
``-fwhole-program``.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

INTERFACES_FILE = ".fobis-interfaces.json"
SUPPORTED = {"gnu": "gnu", "opencoarrays-gnu": "gnu", "nvfortran": "nvfortran", "pgi": "nvfortran"}
CROSS_FILE_FLAGS = ("-flto", "-Mipa", "-Mextract", "-Minline=lib", "-ipo", "-fwhole-program")


def unsupported_reason(compiler: str, cflags: str) -> str | None:
    """Why the cutoff cannot be used with this compiler and these flags (None: it can)."""
    if (compiler or "").lower() not in SUPPORTED:
        return f"interface_cutoff: not measured for compiler {compiler!r} (gnu, nvfortran): every dependent compiles"
    for word in (cflags or "").split():
        if any(word.startswith(flag) for flag in CROSS_FILE_FLAGS):
            return f"interface_cutoff: off with {word} (an object may hold other modules' code)"
    return None


def module_digest(path: str, family: str) -> str | None:
    """The digest of a module file, normalised for *family*: nvfortran's third line is the compile date."""
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError:
        return None
    if family == "nvfortran":
        lines = data.split(b"\n")
        if len(lines) > 2:
            del lines[2]
        data = b"\n".join(lines)
    return hashlib.sha256(data).hexdigest()


class InterfaceCutoff:
    """The recorded interfaces of one object directory, and the decision for the files whose own source did not
    change."""

    def __init__(self, obj_dir: str, mod_dir: str, compiler: str) -> None:
        self.obj_dir = obj_dir
        self.mod_dir = mod_dir
        self.family = SUPPORTED[(compiler or "").lower()]
        self.path = os.path.join(obj_dir, INTERFACES_FILE)
        try:
            with open(self.path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            data = {}
        self.modules: dict[str, str] = dict(data.get("modules", {})) if isinstance(data, dict) else {}
        self.compiled_against: dict[str, dict[str, str]] = (
            dict(data.get("compiled_against", {})) if isinstance(data, dict) else {}
        )
        self.skipped = 0

    @staticmethod
    def closure_modules(pfile: Any) -> list[str]:
        """The project modules *pfile*'s compile reads: those defined in its dependency closure (itself aside)."""
        names = []
        for member in pfile.pfile_dep_all or []:
            if member is pfile or member.include:
                continue
            names.extend(name.lower() for name in member.module_names or [])
        return sorted(set(names))

    def must_compile(self, pfile: Any) -> bool:
        """For a file whose own source did not change: compile it when a module of its closure changed interface
        since it was last compiled, or when nothing was recorded for it."""
        recorded = self.compiled_against.get(pfile.name)
        if recorded is None:
            return True
        # a submodule reads its parent's .smod (the parent's private entities), which is not digested: compiled
        if pfile.submodule or any(m.submodule for m in pfile.pfile_dep_all or [] if m is not pfile):
            return True
        for name in self.closure_modules(pfile):
            current = self.modules.get(name)
            if current is None or recorded.get(name) != current:
                return True
        return False

    def compiled(self, pfile: Any) -> None:
        """Record what *pfile*'s compile wrote (its modules' digests) and read (its closure's)."""
        for name in pfile.module_names or []:
            digest = module_digest(os.path.join(self.mod_dir, name.lower() + ".mod"), self.family)
            if digest is not None:
                self.modules[name.lower()] = digest
        self.compiled_against[pfile.name] = {
            name: self.modules[name] for name in self.closure_modules(pfile) if name in self.modules
        }

    def save(self) -> None:
        os.makedirs(self.obj_dir, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "modules": dict(sorted(self.modules.items())),
                    "compiled_against": dict(sorted(self.compiled_against.items())),
                },
                handle,
                indent=1,
            )
        os.replace(tmp, self.path)


def changed_itself(pfile: Any, obj_dir: str, force: bool, external_mods: dict[str, float]) -> bool:
    """Whether *pfile* must compile for a reason of its own (not because a file it depends on changed): forced, no
    object, the source or a file it includes newer than the object, a module from outside the project newer."""
    if force:
        return True
    obj = os.path.join(obj_dir, pfile.obj_name + ".o")
    if not os.path.exists(obj):
        return True
    stamp = os.path.getmtime(obj)
    if stamp < pfile.timestamp:
        return True
    stack = list(pfile.pfile_dep or [])
    seen = set()
    while stack:  # the files it includes, and those they include in turn
        dep = stack.pop()
        if id(dep) in seen or not dep.include:
            continue
        seen.add(id(dep))
        if not os.path.exists(dep.name) or os.path.getmtime(dep.name) > stamp:
            return True
        stack.extend(dep.pfile_dep or [])
    for member in (pfile, *(pfile.pfile_dep_all or [])):
        for dep in member.dependencies or []:
            if dep.type == "module" and not dep.file and external_mods.get(dep.name.lower(), 0.0) > stamp:
                return True
    return False
