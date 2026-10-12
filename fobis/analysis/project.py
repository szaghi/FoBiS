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
from .units import FileUnits, Unit

_MPI_INIT_RE = re.compile(r"\bmpi_init\s*\(")
_MPI_INIT_THREAD_RE = re.compile(r"\bmpi_init_thread\s*\(")


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
    """

    procedures: dict[str, list[tuple[Unit, str]]] = field(default_factory=dict)
    device_routines: set[str] = field(default_factory=set)
    device_variables: dict[str, DeviceVariable] = field(default_factory=dict)
    parallel_callees: set[str] = field(default_factory=set)
    mpi_init: bool = False
    mpi_init_thread: bool = False

    def functions(self) -> set[str]:
        """Names of the functions defined in the project."""
        return {name for name, defs in self.procedures.items() if any(u.kind == "function" for u, _ in defs)}


def _index_unit(index: ProjectIndex, unit: Unit, path: str) -> None:
    if unit.is_procedure and unit.name and not unit.is_interface_body:
        index.procedures.setdefault(unit.name, []).append((unit, path))
    for stmt in unit.statements:
        if stmt.sentinel is None:
            if _MPI_INIT_THREAD_RE.search(stmt.masked):
                index.mpi_init_thread = True
            elif _MPI_INIT_RE.search(stmt.masked):
                index.mpi_init = True
            continue
        directive = parse_directive(stmt)
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
