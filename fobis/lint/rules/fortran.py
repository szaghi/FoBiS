"""fortran.py — FOR rules: Fortran practice distilled from HPC experience (wave A2)."""

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

from ...analysis.regions import call_name
from ...analysis.units import balanced_end
from ..rule import Hit, LintContext, rule
from ._common import code, declared_in_scope, unit_name, uses_parallelism

_NAME_CALL_RE = re.compile(r"(?<![%\w])([a-z_]\w*)\s*\(")


@rule(
    "FOR001",
    "saved-local-in-parallel-procedure",
    summary="A procedure that runs in parallel has a saved local variable (one copy shared by all threads).",
    rationale="""
        A local variable with the SAVE attribute exists once, statically, not once per call. When the
        procedure is called from inside an OpenMP parallel region or an OpenACC compute region, or is a
        device routine (`!$acc routine`, `!$omp declare target`), every thread works on that single copy:
        writes race, and on a GPU the variable is a global, not a per-thread temporary. SAVE is often
        implicit: an initialiser in the declaration (`real :: d(3) = [h, h, h]`) gives it. Declare the
        variable without initialiser and assign it in the procedure body.
        """,
    bad="""
        subroutine kernel_cell(q)
          !$acc routine seq
          real, intent(inout) :: q(:)
          real :: w(3) = [0.25, 0.5, 0.25]   ! implicit save: one copy for all GPU threads
        """,
    good="""
        subroutine kernel_cell(q)
          !$acc routine seq
          real, intent(inout) :: q(:)
          real :: w(3)
          w = [0.25, 0.5, 0.25]
        """,
)
def check_saved_local_in_parallel(ctx: LintContext) -> Iterator[Hit]:
    project = ctx.project
    for unit in ctx.units.walk():
        if not unit.is_procedure or not unit.name or unit.is_interface_body:
            continue
        if unit.name in project.device_routines:
            reason = "is a device routine"
        elif unit.name in project.parallel_callees:
            reason = "is called inside a parallel region"
        else:
            continue
        for decl in unit.decls.values():
            if decl.name in unit.args or "parameter" in decl.attrs or decl.name == unit.result:
                continue
            explicit = "save" in decl.attrs or unit.save_all
            if not explicit and decl.init is None:
                continue
            how = "saved" if explicit else "initialised in its declaration (implicit save)"
            yield Hit(
                line=decl.line or unit.line,
                message=f"'{decl.name}' is {how}, but {unit_name(unit)} {reason}: all threads share one copy",
                snippet=f"{unit.name}:{decl.name}",
            )


@rule(
    "FOR004",
    "function-result-component",
    summary="A component of a function result is referenced directly: `f(x)%c`.",
    rationale="""
        Fortran does not allow a component (or a type-bound procedure) to be selected from a function
        reference: `f(x)%c` is not a valid designator. Some compilers accept it as an extension, others
        reject it or miscompile it. Assign the result to a variable, or use `associate (r => f(x))` and
        then `r%c`.
        """,
    bad="n = grid_of(level)%ni",
    good="""
        associate (grid => grid_of(level))
          n = grid%ni
        end associate
        """,
    severity="error",
)
def check_function_result_component(ctx: LintContext) -> Iterator[Hit]:
    functions = ctx.project.functions()
    if not functions:
        return
    for unit, stmt in code(ctx):
        masked = stmt.masked
        for match in _NAME_CALL_RE.finditer(masked):
            name = match.group(1)
            if name not in functions or declared_in_scope(unit, name):
                continue
            close = balanced_end(masked, match.end() - 1)
            if re.match(r"\s*%", masked[close:]):
                yield ctx.hit(stmt, f"component selected from the result of function '{name}'")


@rule(
    "FOR005",
    "cpu-time-for-wall-clock",
    summary="`cpu_time` measures time in code that runs in parallel (OpenMP, OpenACC, MPI).",
    rationale="""
        `cpu_time` returns processor time of the calling process or thread, not elapsed time. With
        threads it adds up (or not, depending on the compiler) the time of all threads; with a GPU it
        reports almost nothing, because the host thread just waits. Measure elapsed time with
        `system_clock` (count and count_rate), `omp_get_wtime()` or `MPI_Wtime()`, after synchronising
        asynchronous work (`!$acc wait`).
        """,
    bad="call cpu_time(t0)",
    good="""
        call system_clock(c0, rate)
        ...
        call system_clock(c1)
        elapsed = real(c1 - c0) / rate
        """,
)
def check_cpu_time(ctx: LintContext) -> Iterator[Hit]:
    if not uses_parallelism(ctx):
        return
    for _, stmt in code(ctx):
        if call_name(stmt) == "cpu_time":
            yield ctx.hit(stmt, "cpu_time measures processor time, not elapsed time, in parallel code")
