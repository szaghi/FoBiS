"""project.py — cross-file facts: procedures, device routines, device-declared variables, MPI initialisation.

Built once over every linted file so that rules about one file can use what the rest of the project says:
whether a procedure called inside an OpenACC compute region carries ``!$acc routine``, whether a reduction
targets a module variable declared ``!$acc declare create``, how MPI is initialised. Names are resolved by
name only (no ``use``/rename resolution): two procedures with the same name in different modules are both
recorded.
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
from collections.abc import Iterable
from dataclasses import dataclass, field

from .regions import call_name, parse_directive, regions
from .units import FileUnits, Unit, balanced_end, split_top

_MPI_INIT_RE = re.compile(r"\bmpi_init\s*\(")
_MPI_INIT_THREAD_RE = re.compile(r"\bmpi_init_thread\s*\(")
_COMM_RANK_RE = re.compile(r"^call\s+mpi_comm_rank\s*\(")
_TYPE_DEF_RE = re.compile(r"^type\s*(?:,[^:]*)?::\s*(\w+)|^type\s+(?!is\b)(\w+)\s*(?:\(.*\))?\s*$")
_END_TYPE_RE = re.compile(r"^end\s*type\b")
_FINAL_RE = re.compile(r"^final\s*(?:::)?\s*(.*)$")
_KIND_NAMES = {
    "real32": 6,
    "c_float": 6,
    "real64": 15,
    "c_double": 15,
    "real128": 33,
    "c_long_double": 18,
}
_KIND_LITERAL_PRECISION = {"4": 6, "8": 15, "10": 18, "16": 33}


@dataclass(frozen=True)
class DeviceVariable:
    """A module variable made device-resident by ``!$acc declare create/copyin``."""

    name: str
    module: str
    path: str
    line: int
    allocatable: bool


@dataclass
class ProjectIndex:
    """Facts gathered across all files of a lint run.

    Attributes
    ----------
    procedures : dict
        Procedure name to list of (unit, path) defining it.
    device_routines : set of str
        Procedures marked ``!$acc routine`` or ``!$omp declare target``.
    device_variables : dict
        Module variable name to `DeviceVariable`.
    parallel_callees : set of str
        Procedures called (``call``) inside an OpenMP parallel or OpenACC compute region somewhere.
    mpi_init, mpi_init_thread : bool
        ``mpi_init`` / ``mpi_init_thread`` is called somewhere.
    kind_parameters : dict
        Integer named constant to its initialiser text (``r8p`` -> ``selected_real_kind(15,307)``).
    module_arrays : set of str
        Names of the arrays declared in modules (visible to their users).
    finalisers : dict
        Derived type name to the names of its final procedures.
    enter_data : set of str
        Variables listed in ``!$acc enter data`` / ``!$omp target enter data`` anywhere (device-resident
        beyond one unit).
    rank_variables : set of str
        Variables receiving the rank of ``mpi_comm_rank`` somewhere.
    """

    procedures: dict[str, list[tuple[Unit, str]]] = field(default_factory=dict)
    device_routines: set[str] = field(default_factory=set)
    device_variables: dict[str, DeviceVariable] = field(default_factory=dict)
    parallel_callees: set[str] = field(default_factory=set)
    mpi_init: bool = False
    mpi_init_thread: bool = False
    kind_parameters: dict[str, str] = field(default_factory=dict)
    module_arrays: set[str] = field(default_factory=set)
    finalisers: dict[str, list[str]] = field(default_factory=dict)
    enter_data: set[str] = field(default_factory=set)
    rank_variables: set[str] = field(default_factory=set)

    def functions(self) -> set[str]:
        """Names of the functions defined in the project."""
        return {name for name, defs in self.procedures.items() if any(u.kind == "function" for u, _ in defs)}

    def procedure(self, name: str) -> Unit | None:
        """The unit defining procedure *name* when exactly one does, else None."""
        defs = self.procedures.get(name, [])
        return defs[0][0] if len(defs) == 1 else None

    def real_precision(self, kind: str, local: dict[str, str] | None = None, depth: int = 0) -> int | None:
        """Decimal precision of the real kind *kind* (a literal, an intrinsic-module name or a named constant).

        Named constants are resolved through *local* (the unit's own constants) and then the project's;
        None when the kind cannot be resolved.
        """
        kind = kind.strip().lower()
        if kind in _KIND_LITERAL_PRECISION:
            return _KIND_LITERAL_PRECISION[kind]
        if kind in _KIND_NAMES:
            return _KIND_NAMES[kind]
        if depth > 8 or not re.fullmatch(r"[a-z_]\w*", kind):
            return None
        init = (local or {}).get(kind) or self.kind_parameters.get(kind)
        if init is None:
            # PENF naming convention (R4P/R8P/R16P = bytes), for kind modules outside the linted sources
            penf = re.fullmatch(r"r(4|8|10|16)p", kind)
            return _KIND_LITERAL_PRECISION[penf.group(1)] if penf else None
        init = init.replace(" ", "")
        if init.startswith("selected_real_kind("):
            args = split_top(init[len("selected_real_kind(") : balanced_end(init, len("selected_real_kind")) - 1])
            precision = args[0].split("=", 1)[1] if args and args[0].startswith("p=") else (args[0] if args else "")
            return int(precision) if precision.isdigit() else None
        literal = re.fullmatch(r"kind\((?:\d+\.\d*|\.\d+)([de][-+]?\d+)?(?:_(\w+))?\)", init)
        if literal:
            if literal.group(2):
                return self.real_precision(literal.group(2), local, depth + 1)
            return 15 if (literal.group(1) or "").startswith("d") else 6
        return self.real_precision(init, local, depth + 1)


def _index_unit(index: ProjectIndex, unit: Unit, path: str) -> None:
    if unit.is_procedure and unit.name and not unit.is_interface_body:
        index.procedures.setdefault(unit.name, []).append((unit, path))
    for decl in unit.decls.values():
        if "parameter" in decl.attrs and decl.init is not None and decl.type_spec.startswith("integer"):
            index.kind_parameters[decl.name] = decl.init
        if unit.kind == "module" and (decl.dims or "dimension" in decl.attrs):
            index.module_arrays.add(decl.name)
    current_type = None
    for stmt in unit.statements:
        if stmt.sentinel is None:
            masked = stmt.masked.strip()
            if _MPI_INIT_THREAD_RE.search(masked):
                index.mpi_init_thread = True
            elif _MPI_INIT_RE.search(masked):
                index.mpi_init = True
            elif _COMM_RANK_RE.match(masked):
                args = split_top(masked[masked.index("(") + 1 : balanced_end(masked, masked.index("(")) - 1])
                rank = re.sub(r"^rank\s*=\s*", "", args[1]) if len(args) > 1 else ""
                last = re.search(r"([a-z_]\w*)\s*$", rank)  # the component for "self%rank"
                if last:
                    index.rank_variables.add(last.group(1))
            typedef = _TYPE_DEF_RE.match(masked)
            if typedef:
                current_type = typedef.group(1) or typedef.group(2)
            elif _END_TYPE_RE.match(masked):
                current_type = None
            elif current_type:
                final = _FINAL_RE.match(masked)
                if final:
                    names = [n.strip() for n in final.group(1).split(",") if n.strip()]
                    index.finalisers.setdefault(current_type, []).extend(names)
            continue
        directive = parse_directive(stmt)
        if directive.construct in ("enter data", "target enter data"):
            index.enter_data.update(directive.variables("copyin", "create", "map", "attach"))
        if directive.construct == "routine" or (stmt.sentinel == "omp" and directive.construct == "declare target"):
            named = re.match(r"^(?:routine|declare\s+target)\s*\(\s*(\w+)\s*\)", stmt.masked.strip())
            if named:
                index.device_routines.add(named.group(1))
            elif unit.is_procedure and unit.name:
                index.device_routines.add(unit.name)
        elif directive.construct == "declare" and unit.kind == "module":
            for name in directive.variables("create", "copyin", "device_resident"):
                decl = unit.decls.get(name)
                index.device_variables[name] = DeviceVariable(
                    name=name,
                    module=unit.name,
                    path=path,
                    line=stmt.line,
                    allocatable=decl is not None and "allocatable" in decl.attrs,
                )
    for region in regions(unit.statements):
        if region.is_acc_compute or region.is_omp_parallel:
            index.parallel_callees.update(name for s in region.statements if (name := call_name(s)))


def build_index(files: Iterable[FileUnits]) -> ProjectIndex:
    """Index every unit of *files*."""
    index = ProjectIndex()
    for file_units in files:
        for unit in file_units.walk():
            _index_unit(index, unit, file_units.source.path)
    return index
