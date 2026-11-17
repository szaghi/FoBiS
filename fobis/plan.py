"""What a build compiles besides its target's dependency closure (issue #218, phase 1).

A Fortran file without modules (procedures written outside any module, ``block data``, a C source) is linked into
the target as external procedures: nothing in the dependency graph says which target needs it. FoBiS used to build
and link every such file of the source tree, and every submodule, into every target. On a project whose sources hold
the documentation snippets of its dependencies, that meant hundreds of fragments compiled (and failing) on every
build, the modules they use compiled too, and the procedures of the snippets that did compile linked into the
program.

The build plan decides, per target, which of those files are compiled and linked:

``reachable`` (the default with a target)
    a file without modules is kept when one of the external procedures it defines is NAMED in a file the target
    uses (its dependency closure, then the closure of every file kept, until nothing changes); a submodule is kept
    when its ancestor module is in the plan. The test is on words: a name in a comment keeps a file (more is
    compiled, never less), a name built by the preprocessor's token pasting is missed (the link then fails with an
    undefined reference, which ``--explain`` attributes to the file left out).
``all`` (the default without a target, and for libraries)
    every file without modules and every submodule, as FoBiS always did.
``none``
    no Fortran file without modules; submodules as for ``reachable``.

Whatever the policy, a file that defines no procedure at all (a fragment: no ``subroutine``, ``function`` or
``block data``) is compiled only under ``all``; C sources, ``block data`` files and procedures with ``bind(c)`` are
always kept, since their callers name them in ways the word test cannot see.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

POLICIES = ("reachable", "all", "none")
FAILED_FILE = ".fobis-failed.json"

FIXED_FORM_EXTENSIONS = {".f", ".for", ".f77", ".fpp", ".ftn"}

_WORD = re.compile(r"[a-z_][a-z0-9_]*")
_HEADER = re.compile(
    r"^(?P<prefix>[a-z0-9_\s(),*=:]*?)\b(?P<kind>subroutine|function)\s+(?P<name>[a-z][a-z0-9_]*)", re.IGNORECASE
)
_END_UNIT = re.compile(r"^\s*end\s*(?:(?:subroutine|function)\b.*)?$", re.IGNORECASE)
_END_BLOCK_DATA = re.compile(r"^\s*end\s*block\s*data\b", re.IGNORECASE)
_BLOCK_DATA = re.compile(r"^\s*block\s*data\b", re.IGNORECASE)
_INTERFACE = re.compile(r"^\s*(?:abstract\s+)?interface\b", re.IGNORECASE)
_END_INTERFACE = re.compile(r"^\s*end\s*interface\b", re.IGNORECASE)
_ENTRY = re.compile(r"^\s*entry\s+(?P<name>[a-z][a-z0-9_]*)", re.IGNORECASE)
_BIND_C = re.compile(r"\bbind\s*\(\s*c\b", re.IGNORECASE)
_STARTS_WITH_END = re.compile(r"^\s*end", re.IGNORECASE)


@dataclass
class ExternalProcedures:
    """What a file without modules defines for the linker."""

    names: list[str] = field(default_factory=list)  # lower case, in source order
    block_data: bool = False
    binds_c: bool = False


def _strip_comment(line: str) -> str:
    """The line without its ``!`` comment (a ``!`` inside a string is kept)."""
    quote = None
    for index, char in enumerate(line):
        if quote:
            if char == quote:
                quote = None
        elif char in "'\"":
            quote = char
        elif char == "!":
            return line[:index]
    return line


def logical_lines(source: str, fixed_form: bool) -> list[str]:
    """The statements of *source*: comments dropped, continuation lines joined, ``;`` split; preprocessor lines
    skipped. Approximate on purpose (strings holding ``&`` or ``;`` are rare in procedure headers)."""
    statements: list[str] = []
    current = ""
    for raw in source.splitlines():
        if raw.lstrip().startswith("#"):
            continue
        if fixed_form:
            if raw[:1] in ("c", "C", "*", "!"):
                continue
            line = _strip_comment(raw[:72])
            if len(line) > 5 and line[5] not in (" ", "0") and not line[:5].strip():
                current += " " + line[6:]
                continue
            if current.strip():
                statements.append(current)
            current = line[6:] if len(line) > 6 else ""
            continue
        line = _strip_comment(raw).rstrip()
        stripped = line.lstrip()
        if stripped.startswith("&"):
            stripped = stripped[1:]
        if current.endswith("&"):
            current = current[:-1] + " " + stripped
        else:
            if current.strip():
                statements.append(current)
            current = line
    if current.strip():
        statements.append(current.rstrip("&"))
    split: list[str] = []
    for statement in statements:
        split.extend(part for part in statement.split(";") if part.strip())
    return split


def external_procedures(source: str, fixed_form: bool = False) -> ExternalProcedures:
    """The external procedures a file without modules defines: the ``subroutine``/``function`` units at the top
    level (not those of an interface block, not the internal ones after ``contains``), their ``entry`` names, and
    whether it holds ``block data`` or a ``bind(c)`` procedure."""
    found = ExternalProcedures()
    depth = 0
    interfaces = 0
    for statement in logical_lines(source, fixed_form):
        if _END_INTERFACE.match(statement):
            interfaces = max(0, interfaces - 1)
            continue
        if _INTERFACE.match(statement):
            interfaces += 1
            continue
        if interfaces:
            continue
        if _END_BLOCK_DATA.match(statement):
            depth = max(0, depth - 1)
            continue
        if _BLOCK_DATA.match(statement):
            if depth == 0:
                found.block_data = True
            depth += 1
            continue
        if _STARTS_WITH_END.match(statement):
            if _END_UNIT.match(statement):
                depth = max(0, depth - 1)
            continue
        header = _HEADER.match(statement)
        if header:
            if depth == 0:
                name = header.group("name").lower()
                if name not in found.names:
                    found.names.append(name)
                if _BIND_C.search(statement):
                    found.binds_c = True
            depth += 1
            continue
        if depth == 1:
            entry = _ENTRY.match(statement)
            if entry and entry.group("name").lower() not in found.names:
                found.names.append(entry.group("name").lower())
    return found


def is_fixed_form(path: str) -> bool:
    """Fixed source form by extension (``.f``, ``.for``, ``.f77``, ``.fpp``, ``.ftn``, any case)."""
    return os.path.splitext(path)[1].lower() in FIXED_FORM_EXTENSIONS


def words_of(pfile: Any) -> set[str]:
    """The lower-case words of a file's text (memoised on the file): identifiers, keywords, comment words."""
    cached = getattr(pfile, "_plan_words", None)
    if cached is None:
        try:
            with open(pfile.name, encoding="utf-8", errors="replace") as handle:
                cached = set(_WORD.findall(handle.read().lower()))
        except OSError:
            cached = set()
        pfile._plan_words = cached
    return cached


@dataclass
class BuildPlan:
    """The files without modules and the submodules a target is built with."""

    policy: str
    nomodlibs: list[Any] = field(default_factory=list)
    submodules: list[Any] = field(default_factory=list)
    left_out: dict[str, str] = field(default_factory=dict)  # file name -> why it is not built

    def fragments(self) -> list[str]:
        return [name for name, why in self.left_out.items() if why.startswith("fragment")]


def resolve_policy(cliargs: Any) -> str:
    """The policy of this build: the ``nomodlibs`` option or mode key, else ``reachable`` for a build with a target
    that is not a library, else ``all``."""
    value = (getattr(cliargs, "nomodlibs", None) or "").strip().lower()
    if value:
        if value not in POLICIES:
            raise ValueError(f"nomodlibs = {value}: one of {', '.join(POLICIES)}")
        return value
    if getattr(cliargs, "build_all", False) or getattr(cliargs, "mklib", None) or not getattr(cliargs, "target", None):
        return "all"
    return "reachable"


def _always_kept(pfile: Any) -> bool:
    procedures = getattr(pfile, "external_procedures", None)
    return bool(pfile.c_source or (procedures and (procedures.block_data or procedures.binds_c)))


def make_plan(pfiles: list[Any], roots: list[Any], policy: str) -> BuildPlan:
    """The plan of a build whose targets are *roots* (their dependency closures are built anyway)."""
    nomodlibs = [p for p in pfiles if p.nomodlib]
    submodules = [p for p in pfiles if p.submodule]
    if policy == "all" or not roots:
        return BuildPlan("all", nomodlibs, submodules)
    plan = BuildPlan(policy)
    in_plan: set[int] = set()
    words: set[str] = set()
    modules: set[str] = set()

    def add(pfile: Any) -> None:
        for member in pfile.pfile_dep_all or [pfile]:
            if id(member) in in_plan:
                continue
            in_plan.add(id(member))
            words.update(words_of(member))
            modules.update(name.lower() for name in (member.module_names or []))

    for root in roots:
        add(root)
    pending: list[Any] = []
    for pfile in nomodlibs:
        procedures = getattr(pfile, "external_procedures", None)
        if _always_kept(pfile):
            plan.nomodlibs.append(pfile)
            add(pfile)
        elif policy == "none":
            plan.left_out[pfile.name] = "nomodlibs = none"
        elif not procedures or not procedures.names:
            plan.left_out[pfile.name] = "fragment: defines no subroutine, function or block data"
        else:
            pending.append(pfile)
    pending_submodules = list(submodules)
    changed = True
    while changed:
        changed = False
        for pfile in list(pending):
            if any(name in words for name in pfile.external_procedures.names):
                pending.remove(pfile)
                plan.nomodlibs.append(pfile)
                add(pfile)
                changed = True
        for pfile in list(pending_submodules):
            ancestor = (getattr(pfile, "submodule_ancestor", None) or "").lower()
            if id(pfile) in in_plan or not ancestor or ancestor in modules:
                pending_submodules.remove(pfile)
                plan.submodules.append(pfile)
                add(pfile)
                changed = True
    for pfile in pending:
        names = ", ".join(pfile.external_procedures.names[:4])
        more = "..." if len(pfile.external_procedures.names) > 4 else ""
        plan.left_out[pfile.name] = f"not reachable: no file of the target names {names}{more}"
    for pfile in pending_submodules:
        plan.left_out[pfile.name] = (
            f"not reachable: the target does not use its ancestor module {pfile.submodule_ancestor}"
        )
    order = {id(p): n for n, p in enumerate(pfiles)}
    plan.nomodlibs.sort(key=lambda p: order[id(p)])
    plan.submodules.sort(key=lambda p: order[id(p)])
    return plan


# Files without modules that failed to compile are remembered (issue #218): a fragment that cannot compile was
# compiled again on every build. The digest covers the file, the files it includes and the compile command, so any
# change of them retries it.


def failure_digest(pfile: Any, command: str) -> str:
    digest = hashlib.sha256(command.encode())
    for member in [pfile, *(dep for dep in (pfile.pfile_dep_all or []) if dep.include)]:
        try:
            with open(member.name, "rb") as handle:
                digest.update(member.name.encode() + b"\0" + handle.read())
        except OSError:
            digest.update(member.name.encode() + b"\0missing")
    return digest.hexdigest()


def load_failures(obj_dir: str) -> dict[str, str]:
    try:
        with open(os.path.join(obj_dir, FAILED_FILE), encoding="utf-8") as handle:
            data = json.load(handle)
        return {str(k): str(v) for k, v in data.get("failed", {}).items()}
    except (OSError, ValueError, AttributeError):
        return {}


def save_failures(obj_dir: str, failures: dict[str, str]) -> None:
    path = os.path.join(obj_dir, FAILED_FILE)
    if not failures:
        if os.path.exists(path):
            os.remove(path)
        return
    os.makedirs(obj_dir, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump({"failed": dict(sorted(failures.items()))}, handle, indent=1)
        handle.write("\n")
    os.replace(tmp, path)
