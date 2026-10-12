"""_common.py — helpers shared by rule modules."""

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
from collections.abc import Iterator
from dataclasses import dataclass

from ...analysis import Decl, Statement, Unit, mask_strings
from ...analysis.lexer import _scan
from ...analysis.regions import is_do, loop_end
from ..rule import Edit, LintContext


def unit_name(unit: Unit) -> str:
    """Human-readable designation of *unit*: ``subroutine 'step'``."""
    return f"{unit.kind} '{unit.name}'" if unit.name else unit.kind


def code(ctx: LintContext) -> Iterator[tuple[Unit, Statement]]:
    """Every code statement (directives excluded) with the unit owning it."""
    for unit in ctx.units.walk():
        for stmt in unit.statements:
            if stmt.sentinel is None:
                yield unit, stmt


def declared_in_scope(unit: Unit | None, name: str) -> bool:
    """*name* is declared in *unit* or one of its hosts."""
    while unit is not None:
        if name in unit.decls:
            return True
        unit = unit.parent
    return False


def physical_code(ctx: LintContext, stmt: Statement) -> Iterator[tuple[int, str]]:
    """(line, masked code) of each physical line of *stmt*: comments removed, literal contents blanked.

    Columns are preserved, so a match position is a position in the raw line (for `Edit`).
    """
    lines = ctx.source.lines
    for lineno in range(stmt.line, stmt.end_line + 1):
        raw = lines[lineno - 1] if lineno - 1 < len(lines) else ""
        if ctx.source.fixed_form:
            if raw[:1] in ("c", "C", "*", "!"):
                continue
            raw = raw[:72]
        code_part, _ = _scan(raw, None)
        yield lineno, mask_strings(code_part)


def replacements(ctx: LintContext, stmt: Statement, pattern: re.Pattern, replace) -> tuple[Edit, ...]:
    """Edits replacing every match of *pattern* in the code of *stmt* by ``replace(match)``."""
    edits = []
    for lineno, masked in physical_code(ctx, stmt):
        for match in pattern.finditer(masked):
            edits.append(Edit(line=lineno, start=match.start(), end=match.end(), text=replace(match)))
    return tuple(edits)


def uses_parallelism(ctx: LintContext) -> bool:
    """The file contains OpenMP/OpenACC directives or uses MPI or omp_lib."""
    if any(stmt.sentinel is not None for stmt in ctx.source.statements):
        return True
    if any(name.lower() in ("mpif.h", "omp_lib.h") for _, name in ctx.source.includes):
        return True
    return any(use.module in ("mpi", "mpi_f08", "omp_lib", "openacc") for unit in ctx.units.walk() for use in unit.uses)


_DO_HEAD_RE = re.compile(r"^(?:([a-z_]\w*)\s*:\s*)?do\b(?!\s*=)\s*(?:\d+\s*,?\s*)?(?:([a-z_]\w*)\s*=)?")


@dataclass(frozen=True)
class Loop:
    """A DO loop of a unit: statement indices of its header and closing statement, construct name, DO variable."""

    start: int
    end: int
    name: str | None
    index: str | None
    concurrent: bool


def do_loops(statements: list[Statement]) -> list[Loop]:
    """The DO loops among *statements* (a unit's statement list), in source order."""
    loops = []
    for idx, stmt in enumerate(statements):
        if not is_do(stmt):
            continue
        masked = stmt.masked.strip()
        match = _DO_HEAD_RE.match(masked)
        concurrent = bool(re.match(r"^(?:\w+\s*:\s*)?do\s+concurrent\b", masked))
        index = None if concurrent or match is None else match.group(2)
        loops.append(Loop(idx, loop_end(statements, idx), match.group(1) if match else None, index, concurrent))
    return loops


def innermost_loop(loops: list[Loop], index: int) -> Loop | None:
    """The innermost loop whose body contains the statement at *index*."""
    inside = [loop for loop in loops if loop.start < index <= loop.end]
    return max(inside, key=lambda loop: loop.start) if inside else None


def lookup(unit: Unit | None, name: str) -> tuple[Unit, Decl] | None:
    """The declaration of *name* visible from *unit* (own scope first, then hosts)."""
    while unit is not None:
        if name in unit.decls:
            return unit, unit.decls[name]
        unit = unit.parent
    return None


def is_array(unit: Unit, name: str, module_arrays: set[str] = frozenset()) -> bool:
    """*name* is an array in the scope of *unit*: declared with a shape locally or by a host, or a module array."""
    found = lookup(unit, name)
    if found is not None:
        return bool(found[1].dims) or "dimension" in found[1].attrs
    return name in module_arrays
