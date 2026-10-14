"""query.py — deterministic questions about a project's code (``fobis query``).

A `CodeGraph` is built from the analysed files of a project (`fobis.lint.lint_files` without rules: the mode's
sources and ``-D`` defines) and answers:

- ``callers NAME`` / ``callees NAME``: subroutine calls, function references and type-bound calls. A name resolves
  to a procedure contained in the caller or its hosts, then to a project procedure; a generic resolves to its
  specifics and a binding to the procedures bound to it in any type (the analysis knows neither the argument types
  that select a specific nor the dynamic type of an object: those are *candidates*). Calls to nothing in the
  analysed sources (external libraries, intrinsics, dependencies) are listed as unresolved.
- ``uses MODULE``: the units that use it, with their only-lists.
- ``writers VAR`` / ``readers VAR``: assignments, ``read`` input lists, ``allocate``/``deallocate``, actual arguments
  of ``intent(out/inout)`` dummies (``intent(in)``: a read; intent unknown: possibly written); every other mention
  is a read. Each site says what the name is in its unit (local, dummy with its intent, host, a module's variable,
  through ``use`` with renames). ``module::var`` keeps the sites where the name is that module's variable.
- ``defines NAME``: modules, procedures, generics, types, bindings, module variables and parameters.
- ``region FILE:LINE``: the OpenMP/OpenACC regions around a line, with their clauses.
- ``device VAR``: device residency of a variable: ``declare``, ``enter/exit data``, data regions, ``update``,
  ``present``; the compute constructs that name it, and those that use it without naming it.
- ``mpi [ROUTINE|KIND]``: the MPI routines called, by kind, with their sites.
- ``interface NAME``: the header and dummy declarations of a procedure; the specifics of a generic; the types
  binding a name.

Limits: no resolution of generics on argument types (a generic overloading an intrinsic lists the intrinsic as a
candidate too), of the dynamic type of a polymorphic object, of pointer aliasing, nor of a name reaching a unit
through a chain of modules (a module re-exporting another one's variable); components (``obj%field``) are not
variables for ``writers``/``readers``.
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

import re
from dataclasses import dataclass, field

from .lexer import Statement
from .project import ProjectIndex
from .regions import Region, assignment, parse_directive, regions, strip_if
from .units import FileUnits, Unit, balanced_end, split_top

KINDS = ("callers", "callees", "uses", "writers", "readers", "defines", "region", "device", "mpi", "interface")

_SPEC = re.compile(
    r"^(?:integer|real|complex|logical|character|double\s*precision|double\s*complex|type\s*\(|class\s*\(|"
    r"procedure|use\b|implicit|import|parameter|dimension|allocatable|save|data\b|namelist|external|intrinsic|"
    r"public|private|protected|common|equivalence|interface|abstract\s+interface|end\s*interface|contains|"
    r"module\s+procedure|format|entry|generic|final|sequence|enum|end\s*enum|enumerator|value|optional|target|"
    r"pointer|asynchronous|volatile|bind|include)\b"
)
_CALL = re.compile(
    r"^call\s+(?P<designator>[a-z_]\w*(?:\s*(?:\((?:[^()]|\([^()]*\))*\))?\s*%\s*[a-z_]\w*)*)\s*(?:\(|$)"
)  # a name, then (subscript)%component steps (two levels of parentheses inside a subscript)
_REFERENCE = re.compile(r"(?<![%\w])([a-z_]\w*)\s*\(")
_BINDING_REFERENCE = re.compile(r"%\s*([a-z_]\w*)\s*\(")
_READ = re.compile(r"^read\s*(\(|[\w*']+\s*,?)")
_ALLOCATE = re.compile(r"^(allocate|deallocate)\s*\(")
_MPI = re.compile(r"(?<![%\w])(mpi_\w+)\s*\(")
_MPI_KINDS = (
    (
        "point-to-point",
        r"mpi_(i|b|r|s)?(send|recv|sendrecv)(_replace)?|mpi_(i|m)?probe|mpi_(wait|test)\w*|mpi_request_\w+|"
        r"mpi_\w+_init|mpi_start\w*|mpi_cancel",
    ),
    (
        "collective",
        r"mpi_i?(bcast|reduce|allreduce|reduce_scatter\w*|gatherv?|allgatherv?|scatterv?|alltoall[vw]?|barrier|"
        r"scan|exscan|neighbor_\w+)",
    ),
    ("one-sided", r"mpi_(win_\w+|r?put|r?get|accumulate|get_accumulate|fetch_and_op|compare_and_swap)"),
    ("io", r"mpi_file_\w+"),
    (
        "setup",
        r"mpi_(init|init_thread|finalize|initialized|finalized|abort|comm_\w+|group_\w+|cart_\w+|graph_\w+|"
        r"dims_create|type_\w+|op_\w+|get_\w+|query_thread|wtime|wtick|error_\w+|errhandler_\w+|info_\w+|"
        r"pack\w*|unpack\w*|address|alloc_mem|free_mem)",
    ),
)


# intrinsic procedures a project often overloads with a generic of the same name
INTRINSICS = frozenset(
    [
        "abs",
        "achar",
        "acos",
        "adjustl",
        "adjustr",
        "aimag",
        "aint",
        "all",
        "allocated",
        "anint",
        "any",
        "asin",
        "associated",
        "atan",
        "atan2",
        "bit_size",
        "btest",
        "ceiling",
        "char",
        "cmplx",
        "conjg",
        "cos",
        "cosh",
        "count",
        "cshift",
        "dble",
        "digits",
        "dim",
        "dot_product",
        "dprod",
        "eoshift",
        "epsilon",
        "exp",
        "exponent",
        "floor",
        "fraction",
        "huge",
        "iachar",
        "iand",
        "ibclr",
        "ibits",
        "ibset",
        "ichar",
        "ieor",
        "index",
        "int",
        "ior",
        "ishft",
        "ishftc",
        "kind",
        "lbound",
        "len",
        "len_trim",
        "lge",
        "lgt",
        "lle",
        "llt",
        "log",
        "log10",
        "logical",
        "matmul",
        "max",
        "maxloc",
        "maxval",
        "merge",
        "min",
        "minloc",
        "minval",
        "mod",
        "modulo",
        "nint",
        "not",
        "pack",
        "precision",
        "present",
        "product",
        "radix",
        "random_number",
        "range",
        "real",
        "repeat",
        "reshape",
        "scan",
        "selected_int_kind",
        "selected_real_kind",
        "shape",
        "sign",
        "sin",
        "sinh",
        "size",
        "spacing",
        "spread",
        "sqrt",
        "sum",
        "tan",
        "tanh",
        "tiny",
        "transfer",
        "transpose",
        "trim",
        "ubound",
        "unpack",
        "verify",
    ]
)


class QueryError(ValueError):
    """An unknown kind or a bad argument."""


def qualified(unit: Unit) -> str:
    """``module::procedure`` (hosts included, outermost first)."""
    names = []
    current: Unit | None = unit
    while current is not None:
        if current.name and current.kind != "interface":
            names.append(current.name)
        current = current.parent
    return "::".join(reversed(names))


@dataclass
class Call:
    """A call site: subroutine call (``call``), function reference (``function``) or type-bound (``binding``)."""

    caller: str  # qualified name of the calling unit
    path: str
    line: int
    name: str  # as written: a procedure, generic or binding name
    kind: str
    resolved: list[str] = field(default_factory=list)  # qualified names
    how: str = ""  # contained, unique, generic, binding, ambiguous, unresolved
    text: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class Definition:
    name: str
    kind: str
    qualified: str
    path: str
    line: int
    detail: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v != "" or k != "detail"}


@dataclass
class Result:
    kind: str
    argument: str
    items: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "argument": self.argument, "items": self.items, "notes": self.notes}


def _short(stmt: Statement, width: int = 100) -> str:
    text = " ".join(stmt.text.split())
    if stmt.sentinel:
        text = f"!${stmt.sentinel} {text}"
    return text if len(text) <= width else text[: width - 3] + "..."


def _executable(stmt: Statement) -> bool:
    return stmt.sentinel is None and not _SPEC.match(stmt.masked.strip())


def _actuals(masked: str, start: int) -> list[tuple[int, str]]:
    """(position, text) of the actual arguments of the parenthesis opening at *start*."""
    found, depth, begin = [], 0, start + 1
    end = balanced_end(masked, start) - 1
    for i in range(start + 1, end + 1):
        char = masked[i] if i < end else ","
        if char in "([":
            depth += 1
        elif char in ")]":
            depth -= 1
        elif char == "," and depth == 0:
            text = masked[begin:i]
            found.append((begin + len(text) - len(text.lstrip()), text.strip()))
            begin = i + 1
    return [(p, t) for p, t in found if t]


def use_names(stmt: Statement) -> tuple[dict[str, str], bool]:
    """(local name -> module entity name, only-list?) of a ``use`` statement: the only-list, or the renames."""
    masked = stmt.masked
    only = re.search(r"\bonly\s*:(.*)$", masked)
    if only:
        items = split_top(only.group(1))
    else:
        rest = masked.split("::", 1)[1] if "::" in masked else masked
        items = split_top(rest)[1:]
    names = {}
    for item in items:
        item = item.strip()
        if "=>" in item:
            local, original = (part.strip() for part in item.split("=>", 1))
            names[local] = original
        elif re.fullmatch(r"[a-z_]\w*", item):
            names[item] = item
    return names, bool(only)


class CodeGraph:
    """Facts across the files of a project, computed once and queried by `query`."""

    def __init__(self, files: dict[str, FileUnits], project: ProjectIndex) -> None:
        from ..ai.impact import _types
        from ..ai.testgen import type_bindings

        self.files = files
        self.project = project
        self.units: list[tuple[Unit, str]] = [(u, p) for p, f in files.items() for u in f.walk()]
        self.definitions: dict[str, list[Definition]] = {}
        self.generics: dict[str, list[str]] = {}  # generic name -> specific names
        self.bindings: dict[str, list[tuple[str, str]]] = {}  # binding name -> (type, specific)
        self.module_variables: dict[str, set[str]] = {}  # module -> its variables and parameters
        for unit, path in self.units:
            if (unit.kind in ("module", "submodule", "program") or unit.is_procedure) and unit.name:
                if not unit.is_interface_body:
                    self._define(unit.name, unit.kind, qualified(unit), path, unit.line)
                elif unit.parent.abstract:  # an abstract interface: a name used as procedure(NAME) by dummies
                    self._define(unit.name, "abstract interface", qualified(unit), path, unit.line)
            if unit.kind == "interface" and unit.name and not unit.abstract:
                words = {w for s in unit.statements for w in re.findall(r"\w+", s.masked)}
                specifics = sorted((words - {"module", "procedure"}) | {b.name for b in unit.children if b.name})
                self.generics.setdefault(unit.name, []).extend(specifics)
                host = qualified(unit.parent) if unit.parent else ""
                self._define(unit.name, "generic", f"{host}::{unit.name}", path, unit.line, ", ".join(specifics))
            if unit.kind == "module":
                variables = self.module_variables.setdefault(unit.name, set())
                for name, decl in unit.decls.items():
                    if decl.type_spec:
                        variables.add(name)
                        kind = "parameter" if "parameter" in decl.attrs else "variable"
                        self._define(name, kind, f"{unit.name}::{name}", path, decl.line, decl.type_spec)
                for name, (body, _, line) in _types(unit).items():
                    self._define(name, "type", f"{unit.name}::{name}", path, line)
                    procedures, generic = type_bindings(body)
                    for binding in procedures.values():
                        self.bindings.setdefault(binding.name, []).append((name, binding.specific))
                        self._define(
                            binding.name, "binding", f"{unit.name}::{name}%{binding.name}", path, line, binding.specific
                        )
                    for gname, (targets, _) in generic.items():
                        for target in targets:
                            specific = procedures[target].specific if target in procedures else target
                            self.bindings.setdefault(gname, []).append((name, specific))
                        self._define(gname, "binding", f"{unit.name}::{name}%{gname}", path, line, ", ".join(targets))
        self.by_name: dict[str, list[tuple[Unit, str]]] = {}
        for unit, path in self.units:
            if unit.is_procedure and unit.name and not unit.is_interface_body:
                self.by_name.setdefault(unit.name, []).append((unit, path))
        functions = {n for n, defs in self.by_name.items() if any(u.kind == "function" for u, _ in defs)}
        self.functions = functions | {g for g, specs in self.generics.items() if set(specs) & functions}
        self.calls: list[Call] = []
        for unit, path in self.units:
            if (unit.is_procedure and not unit.is_interface_body) or unit.kind == "program":
                self._collect_calls(unit, path)

    def _define(self, name: str, kind: str, qual: str, path: str, line: int, detail: str = "") -> None:
        self.definitions.setdefault(name, []).append(Definition(name, kind, qual, path, line, detail))

    # ── calls ──────────────────────────────────────────────────────────────────

    def _is_variable(self, unit: Unit, name: str) -> bool:
        """*name* is declared as a variable in *unit*'s scope (an array reference, not a call)."""
        current: Unit | None = unit
        while current is not None:
            decl = current.decls.get(name)
            if decl is not None:
                return "external" not in decl.attrs and not decl.type_spec.startswith("procedure")
            current = current.parent
        return False

    def resolve(self, unit: Unit, name: str) -> tuple[list[str], str]:
        """(qualified procedures, how) that *name* refers to when called from *unit*."""
        current: Unit | None = unit
        while current is not None:
            for child in current.children:
                if child.is_procedure and child.name == name and not child.is_interface_body:
                    return [qualified(child)], "contained"
            current = current.parent
        if name in self.generics:
            found = [qualified(u) for specific in self.generics[name] for u, _ in self.by_name.get(specific, [])]
            intrinsic = ["intrinsic " + name] if name in INTRINSICS else []  # chosen by the argument types too
            return sorted(set(found)) + intrinsic, "generic"
        defs = self.by_name.get(name, [])
        if len(defs) == 1:
            return [qualified(defs[0][0])], "unique"
        if defs:
            return sorted(qualified(u) for u, _ in defs), "ambiguous"
        return [], "unresolved"

    def resolve_binding(self, name: str) -> tuple[list[str], str]:
        found = [qualified(u) for _, specific in self.bindings.get(name, []) for u, _ in self.by_name.get(specific, [])]
        return sorted(set(found)), ("binding" if found else "unresolved")

    def _function_binding(self, name: str) -> bool:
        return any(
            u.kind == "function"
            for _, specific in self.bindings.get(name, [])
            for u, _ in self.by_name.get(specific, [])
        )

    def _collect_calls(self, unit: Unit, path: str) -> None:
        caller = qualified(unit)
        for stmt in unit.statements:
            if not _executable(stmt):
                continue
            masked = strip_if(stmt.masked.strip())
            call = _CALL.match(masked)
            called_at = -1
            if call:
                designator = re.sub(r"\((?:[^()]|\([^()]*\))*\)|\s", "", call.group("designator"))
                if "%" in designator:
                    name, kind = designator.rsplit("%", 1)[1], "binding"
                    resolved, how = self.resolve_binding(name)
                else:
                    name, kind = designator, "call"
                    resolved, how = self.resolve(unit, name)
                    called_at = call.start("designator")
                self.calls.append(Call(caller, path, stmt.line, name, kind, resolved, how, _short(stmt)))
            for match in _BINDING_REFERENCE.finditer(masked):
                name = match.group(1)
                if name in self.bindings and self._function_binding(name):
                    resolved, how = self.resolve_binding(name)
                    self.calls.append(Call(caller, path, stmt.line, name, "binding", resolved, how, _short(stmt)))
            for match in _REFERENCE.finditer(masked):
                name = match.group(1)
                if match.start() == called_at or name not in self.functions or self._is_variable(unit, name):
                    continue
                resolved, how = self.resolve(unit, name)
                self.calls.append(Call(caller, path, stmt.line, name, "function", resolved, how, _short(stmt)))

    # ── names ──────────────────────────────────────────────────────────────────

    def targets(self, name: str) -> list[tuple[Unit, str]]:
        """The procedures (or programs) named *name* (``module::proc`` or a bare name)."""
        name = name.lower()
        if "::" in name:
            return [(u, p) for u, p in self.units if qualified(u) == name]
        return [
            (u, p)
            for u, p in self.units
            if u.name == name and (u.is_procedure or u.kind == "program") and not u.is_interface_body
        ]

    def local_names(self, unit: Unit, module: str, name: str) -> set[str]:
        """The names under which *module*'s *name* is known in *unit* (its own, and renames on ``use``)."""
        names = {name}
        current: Unit | None = unit if module else None
        while current is not None:
            for use in current.uses:
                if use.module == module:
                    names.update(local for local, original in use_names(use.statement)[0].items() if original == name)
            current = current.parent
        return names

    def binding_of(self, unit: Unit, name: str) -> tuple[str, str]:
        """(what *name* is in *unit*, the module it belongs to or ''): local, dummy (intent), host, module
        variable, use (renamed), unknown."""
        current: Unit | None = unit
        first = True
        while current is not None:
            decl = current.decls.get(name)
            if decl is not None:
                if current.kind == "module":
                    return ("module variable" if first else "host module variable"), current.name
                if name in current.args:
                    intent = decl.attrs.get("intent", "")
                    what = f"dummy, intent({intent})" if intent else "dummy"
                    return (what if first else "host " + what), ""
                return ("local" if first else "host local"), ""
            for use in current.uses:
                names, only = use_names(use.statement)
                variables = self.module_variables.get(use.module, set())
                if name in names:
                    original = names[name]
                    if original in variables:
                        return ("use" if original == name else f"use, renamed from {original}"), use.module
                elif not only and name in variables and name not in names.values():
                    return "use", use.module
            current, first = current.parent, False
        return "unknown", ""


# ── the queries ────────────────────────────────────────────────────────────────


def query(graph: CodeGraph, kind: str, argument: str = "") -> Result:
    """Answer one query (see the module documentation)."""
    if kind not in KINDS:
        raise QueryError(f"unknown query {kind!r} (known: {', '.join(KINDS)})")
    argument = argument.strip()
    if kind != "mpi" and not argument:
        raise QueryError(f"query {kind} needs an argument")
    handlers = {
        "callers": _callers,
        "callees": _callees,
        "uses": _uses,
        "writers": _accesses,
        "readers": _accesses,
        "defines": _defines,
        "region": _region,
        "device": _device,
        "mpi": _mpi,
        "interface": _interface,
    }
    return handlers[kind](graph, kind, argument)


def _not_found(result: Result, what: str) -> Result:
    result.notes.append(f"{what} is not defined in the analysed sources")
    return result


def _callees(graph: CodeGraph, kind: str, argument: str) -> Result:
    result = Result(kind, argument)
    targets = {qualified(u) for u, _ in graph.targets(argument)}
    if not targets:
        return _not_found(result, argument)
    calls = [c for c in graph.calls if c.caller in targets]
    result.items = [c.to_dict() for c in calls]
    unresolved = sorted({c.name for c in calls if c.how == "unresolved"})
    if unresolved:
        result.notes.append(
            "not in the analysed sources (external, intrinsic or a dependency): " + ", ".join(unresolved)
        )
    return result


def _callers(graph: CodeGraph, kind: str, argument: str) -> Result:
    result = Result(kind, argument)
    targets = {qualified(u) for u, _ in graph.targets(argument)}
    bare = argument.lower().split("::")[-1]
    if not targets and bare not in graph.generics and bare not in graph.bindings:
        return _not_found(result, argument)
    for call in graph.calls:
        if targets & set(call.resolved):
            item = call.to_dict()
            if call.how in ("generic", "binding", "ambiguous") and len(call.resolved) > 1:
                item["candidate"] = True
            result.items.append(item)
        elif not targets and call.name == bare:
            result.items.append(call.to_dict())
    if any(i.get("candidate") for i in result.items):
        result.notes.append(
            "candidate: called through a generic, a binding or an ambiguous name with several procedures; the one "
            "called depends on the argument types or the dynamic type, which the analysis does not resolve"
        )
    return result


def _uses(graph: CodeGraph, kind: str, argument: str) -> Result:
    result = Result(kind, argument)
    module = argument.lower()
    for unit, path in graph.units:
        for use in unit.uses:
            if use.module == module:
                names, only = use_names(use.statement)
                item = {"unit": qualified(unit), "path": path, "line": use.line, "text": _short(use.statement)}
                item["only"] = sorted(names) if only else None
                result.items.append(item)
    if not result.items and module not in graph.module_variables:
        result.notes.append(f"module {argument} is neither used nor defined in the analysed sources")
    return result


def _mentions(masked: str, name: str) -> list[int]:
    """Positions where *name* is referenced in *masked*: not a component ``%name``, not a keyword ``name=``."""
    found = []
    for match in re.finditer(rf"(?<![%\w]){re.escape(name)}\b", masked):
        after = masked[match.end() :].lstrip()
        if after.startswith("=") and not after.startswith("=="):
            if masked[: match.start()].count("(") > masked[: match.start()].count(")"):
                continue  # a keyword argument name inside parentheses
        found.append(match.start())
    return found


def _accesses(graph: CodeGraph, kind: str, argument: str) -> Result:
    result = Result(kind, argument)
    module, _, name = argument.lower().rpartition("::")
    if not re.fullmatch(r"[a-z_]\w*", name):
        raise QueryError(f"{argument!r} is not a variable name (NAME or module::NAME)")
    intents = {
        qualified(u): [(a, (u.decls[a].attrs.get("intent", "") if a in u.decls else "")) for a in u.args]
        for u, _ in graph.units
        if u.is_procedure
    }
    for unit, path in graph.units:
        if not ((unit.is_procedure and not unit.is_interface_body) or unit.kind in ("program", "module")):
            continue
        for local in sorted(graph.local_names(unit, module, name)):
            binding, origin = graph.binding_of(unit, local)
            if module and origin != module:
                continue
            for stmt in unit.statements:
                if local not in stmt.masked or not _executable(stmt):
                    continue
                for access, how in _statement_accesses(graph, unit, stmt, local, intents):
                    if (kind == "writers") != (access == "write"):
                        continue
                    item = {"unit": qualified(unit), "path": path, "line": stmt.line, "is": binding}
                    item["text"] = _short(stmt)
                    if origin:
                        item["module"] = origin
                    if how:
                        item["how"] = how
                    result.items.append(item)
    if module and module not in graph.module_variables:
        result.notes.append(f"module {module} is not in the analysed sources")
    result.notes.append("pointer aliasing and accesses under another name (argument association) are not followed")
    return result


def _statement_accesses(
    graph: CodeGraph, unit: Unit, stmt: Statement, name: str, intents: dict[str, list[tuple[str, str]]]
) -> list[tuple[str, str]]:
    """(write|read, how) of every access of *name* in *stmt*."""
    masked = strip_if(stmt.masked.strip())
    mentions = _mentions(masked, name)
    if not mentions:
        return []
    found: list[tuple[str, str]] = []
    handled: set[int] = set()
    assigned = assignment(stmt)
    if assigned and assigned[0] == name:
        found.append(("write", "assignment"))
        handled.add(mentions[0])
    alloc = _ALLOCATE.match(masked)
    if alloc:
        found += [("write", alloc.group(1))] * len(mentions)
        handled.update(mentions)
    read = _READ.match(masked)
    if read:
        start = masked.index("(") if read.group(1) == "(" else -1
        items_at = balanced_end(masked, start) if start >= 0 else read.end()
        for position in mentions:
            if position >= items_at:
                found.append(("write", "read statement"))
                handled.add(position)
    call = _CALL.match(masked)
    if call and masked[call.end() - 1 : call.end()] == "(":
        designator = re.sub(r"\((?:[^()]|\([^()]*\))*\)|\s", "", call.group("designator"))
        if "%" in designator:
            resolved, _ = graph.resolve_binding(designator.rsplit("%", 1)[1])
        else:
            resolved, _ = graph.resolve(unit, designator)
        dummies = intents.get(resolved[0], []) if len(resolved) == 1 else []
        if "%" in designator and dummies:
            dummies = dummies[1:]  # the passed object
        callee = resolved[0] if len(resolved) == 1 else designator
        for index, (position, actual) in enumerate(_actuals(masked, call.end() - 1)):
            keyword = re.match(r"([a-z_]\w*)\s*=(?!=)\s*", actual)
            target = actual[keyword.end() :] if keyword else actual
            if not re.match(rf"{re.escape(name)}\b", target):
                continue
            start = position + (keyword.end() if keyword else 0)
            handled.add(start)
            intent = (
                dict(dummies).get(keyword.group(1), "")
                if keyword
                else (dummies[index][1] if index < len(dummies) else "")
            )
            if intent in ("out", "inout"):
                found.append(("write", f"actual argument of {callee}, intent({intent})"))
            if intent in ("in", "inout"):
                found.append(("read", f"actual argument of {callee}, intent({intent})"))
            if not intent:
                found.append(("write", f"actual argument of {callee}, intent unknown: possibly written"))
                found.append(("read", f"actual argument of {callee}, intent unknown"))
    if any(position not in handled for position in mentions):
        found.append(("read", ""))
    return found


def _defines(graph: CodeGraph, kind: str, argument: str) -> Result:
    result = Result(kind, argument)
    result.items = [d.to_dict() for d in graph.definitions.get(argument.lower(), [])]
    return result if result.items else _not_found(result, argument)


def _unit_at(graph: CodeGraph, path: str, line: int) -> tuple[Unit, str] | None:
    """The innermost unit of *path* holding *line*."""
    best = None
    for unit, upath in graph.units:
        if upath != path and not upath.endswith("/" + path) and not path.endswith("/" + upath):
            continue
        if unit.line <= line <= (unit.end_line or line) and (best is None or unit.line >= best[0].line):
            best = (unit, upath)
    return best


def _region_item(region: Region, unit: Unit, path: str) -> dict:
    directive = region.directive
    last = region.statements[-1].end_line if region.statements else directive.statement.line
    return {
        "unit": qualified(unit),
        "path": path,
        "line": directive.statement.line,
        "end_line": last,
        "sentinel": directive.sentinel,
        "construct": directive.construct,
        "clauses": directive.clauses,
        "text": _short(directive.statement),
    }


def _region(graph: CodeGraph, kind: str, argument: str) -> Result:
    result = Result(kind, argument)
    path, _, number = argument.rpartition(":")
    if not path or not number.isdigit():
        raise QueryError(f"region takes FILE:LINE, not {argument!r}")
    line = int(number)
    found = _unit_at(graph, path, line)
    if found is None:
        result.notes.append(f"{argument}: no unit of the analysed sources holds this line")
        return result
    unit, upath = found
    for region in regions(unit.statements):
        start = region.directive.statement.line
        end = region.statements[-1].end_line if region.statements else start
        if start <= line <= end:
            result.items.append(_region_item(region, unit, upath))
    if not result.items:
        result.notes.append(f"line {line} of {upath} is in no OpenMP/OpenACC region (unit {qualified(unit)})")
    return result


_DATA_CLAUSES = {
    "copy", "copyin", "copyout", "create", "present", "deviceptr", "attach", "detach", "delete", "no_create",
    "device_resident", "link", "map", "to", "from", "host", "device", "self", "use_device", "use_device_ptr",
    "use_device_addr", "is_device_ptr", "has_device_addr", "private", "firstprivate", "reduction",
}  # fmt: skip


def _device(graph: CodeGraph, kind: str, argument: str) -> Result:
    result = Result(kind, argument)
    name = argument.lower()
    for unit, path in graph.units:
        named: set[int] = set()
        for stmt in unit.statements:
            if stmt.sentinel is None:
                continue
            directive = parse_directive(stmt)
            clauses = sorted(c for c in directive.clauses if c in _DATA_CLAUSES and name in directive.variables(c))
            if clauses:
                named.add(stmt.line)
                result.items.append(
                    {
                        "unit": qualified(unit),
                        "path": path,
                        "line": stmt.line,
                        "sentinel": directive.sentinel,
                        "construct": directive.construct,
                        "clauses": clauses,
                        "text": _short(stmt),
                    }
                )
        for region in regions(unit.statements):
            offload = region.is_acc_compute or (
                region.directive.sentinel == "omp" and region.directive.construct.startswith("target")
            )
            if not offload or region.directive.statement.line in named:
                continue
            if any(_mentions(s.masked, name) for s in region.statements if s.sentinel is None):
                item = _region_item(region, unit, path)
                item["implicit"] = True
                result.items.append(item)
    if any(i.get("implicit") for i in result.items):
        result.notes.append(
            "implicit: used in a compute construct that does not name it (present through an enclosing data "
            "region, a declare or an enter data, or copied implicitly)"
        )
    variable = graph.project.device_variables.get(name)
    if variable is not None:
        result.notes.append(f"declared device-resident in module {variable.module} ({variable.path}:{variable.line})")
    return result


def _mpi(graph: CodeGraph, kind: str, argument: str) -> Result:
    result = Result(kind, argument)
    wanted = argument.lower()
    for unit, path in graph.units:
        for stmt in unit.statements:
            if not _executable(stmt):
                continue
            for match in _MPI.finditer(stmt.masked):
                routine = match.group(1)
                category = next((k for k, p in _MPI_KINDS if re.fullmatch(p, routine)), "other")
                if wanted and wanted not in (routine, category):
                    continue
                result.items.append(
                    {
                        "routine": routine,
                        "kind": category,
                        "unit": qualified(unit),
                        "path": path,
                        "line": stmt.line,
                        "text": _short(stmt),
                    }
                )
    counts: dict[str, int] = {}
    for item in result.items:
        counts[item["kind"]] = counts.get(item["kind"], 0) + 1
    if counts:
        result.notes.append("calls by kind: " + ", ".join(f"{k} {n}" for k, n in sorted(counts.items())))
    return result


def _interface(graph: CodeGraph, kind: str, argument: str) -> Result:
    from ..ai.impact import _procedure_signature

    result = Result(kind, argument)
    for unit, path in graph.targets(argument):
        if unit.is_procedure:
            item = {"qualified": qualified(unit), "path": path, "line": unit.line}
            item["signature"] = _procedure_signature(unit)
            result.items.append(item)
    bare = argument.lower().split("::")[-1]
    if bare in graph.generics:
        result.items.append({"generic": bare, "specifics": graph.generics[bare]})
    if bare in graph.bindings:
        result.items.append({"binding": bare, "types": [{"type": t, "procedure": p} for t, p in graph.bindings[bare]]})
    return result if result.items else _not_found(result, argument)


# ── report ─────────────────────────────────────────────────────────────────────


def render_text(result: Result) -> str:
    lines = [f"{result.kind} {result.argument}".strip() + f": {len(result.items)} result(s)"]
    for item in result.items:
        lines += _describe(result.kind, item)
    lines += [f"note: {note}" for note in result.notes]
    return "\n".join(lines)


def _describe(kind: str, item: dict) -> list[str]:
    if "signature" in item:
        return [
            f"{item['path']}:{item['line']}: {item['qualified']}",
            *(f"    {s}" for s in item["signature"].splitlines()),
        ]
    if "specifics" in item:
        return [f"generic {item['generic']}: {', '.join(item['specifics'])}"]
    if "types" in item:
        return ["binding " + ", ".join(f"{t['type']}%{item['binding']} => {t['procedure']}" for t in item["types"])]
    where = f"{item['path']}:{item['line']}"
    if kind in ("callers", "callees"):
        target = ", ".join(item["resolved"]) or "-"
        mark = ", candidate" if item.get("candidate") else ""
        who = item["caller"] if kind == "callers" else item["name"]
        return [f"{where}: {who} [{item['kind']}, {item['how']}{mark}] -> {target}: {item['text']}"]
    if kind == "defines":
        detail = f" ({item['detail']})" if item.get("detail") else ""
        return [f"{where}: {item['kind']} {item['qualified']}{detail}"]
    if kind == "uses":
        only = "" if item["only"] is None else f" (only: {', '.join(item['only'])})"
        return [f"{where}: {item['unit']}{only}"]
    if kind in ("writers", "readers"):
        origin = f" of {item['module']}" if item.get("module") else ""
        how = f"; {item['how']}" if item.get("how") else ""
        return [f"{where}: {item['unit']} [{item['is']}{origin}{how}]: {item['text']}"]
    if kind in ("region", "device"):
        span = f"-{item['end_line']}" if item.get("end_line", item["line"]) != item["line"] else ""
        implicit = " (implicit)" if item.get("implicit") else ""
        return [f"{where}{span}: {item['unit']}{implicit}: {item['text']}"]
    if kind == "mpi":
        return [f"{where}: {item['routine']} [{item['kind']}] in {item['unit']}"]
    return [str(item)]
