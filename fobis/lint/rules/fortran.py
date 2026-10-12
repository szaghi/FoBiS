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
import struct
from collections.abc import Iterator

from ...analysis import Unit, split_top
from ...analysis.regions import assignment, call_name, regions, strip_if
from ...analysis.units import balanced_end
from ..rule import Hit, LintContext, rule
from ._common import code, declared_in_scope, do_loops, is_array, lookup, unit_name, uses_parallelism

_NAME_CALL_RE = re.compile(r"(?<![%\w])([a-z_]\w*)\s*\(")
_REAL_LITERAL_RE = re.compile(r"(?<![\w.])((?:\d+\.\d*|\.\d+)(?:e[-+]?\d+)?|\d+e[-+]?\d+)(?![\w.])")
_REAL_KIND_RE = re.compile(r"^real\((?:kind=)?(\w+)\)$|^real\*(\d+)$")
_ALLOCATE_RE = re.compile(r"^allocate\s*\(")
_GLOBAL_SUM_RE = re.compile(r"^call\s+(mpi_allreduce|mpi_reduce|mpi_iallreduce|mpi_ireduce)\s*\(")
_DIAGNOSTIC_NAME_RE = re.compile(r"res|norm|err|l2|linf|mass|energ|conserv|drift|integral|total|budget")


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


def _subscripts_with(args: list[str], index: str) -> list[int]:
    """Positions of the subscripts in *args* that are *index* itself or *index* plus/minus an offset."""
    pattern = re.compile(rf"^{index}\s*(?:[-+]\s*\w+)?$")
    return [pos for pos, arg in enumerate(args) if pattern.match(arg.strip())]


@rule(
    "FOR002",
    "loop-order-not-column-major",
    summary="The innermost loop runs over a non-leading array dimension while an outer loop runs over the leading one.",
    rationale="""
        Fortran stores arrays column-major: `a(i, j)` and `a(i+1, j)` are adjacent in memory, `a(i, j)` and
        `a(i, j+1)` are a whole column apart. The innermost loop must run over the leftmost subscript to
        walk memory with stride 1; the swapped order makes every access a cache miss and stops
        vectorisation. Reported when, for most array references of the innermost loop, its index is in a
        later dimension and the enclosing loop's index in the first.
        """,
    bad="""
        do i = 1, ni
          do j = 1, nj
            a(i, j) = b(i, j) + c(i, j)
          end do
        end do
        """,
    good="""
        do j = 1, nj
          do i = 1, ni
            a(i, j) = b(i, j) + c(i, j)
          end do
        end do
        """,
    default=False,
)
def check_loop_order(ctx: LintContext) -> Iterator[Hit]:
    module_arrays = ctx.project.module_arrays
    for unit in ctx.units.walk():
        if unit.name and unit.name in ctx.project.device_routines:
            continue
        statements = unit.statements
        loops = do_loops(statements)
        device = [r for r in regions(statements) if r.is_acc_compute or "target" in r.directive.construct.split()]
        for loop in loops:
            if loop.index is None or any(loop.start < other.start <= loop.end for other in loops):
                continue  # not innermost
            if any(r.first <= loop.start <= r.last for r in device):
                continue  # on a GPU the parallel index leads (coalescing); per-thread loops come after it
            outer = max((o for o in loops if o.start < loop.start <= o.end), key=lambda o: o.start, default=None)
            if outer is None or outer.index is None:
                continue
            swapped, ordered, example = 0, 0, ""
            for stmt in statements[loop.start + 1 : loop.end]:
                if stmt.sentinel is not None:
                    continue
                masked = stmt.masked
                for match in _NAME_CALL_RE.finditer(masked):
                    name = match.group(1)
                    if name in (loop.index, outer.index) or not is_array(unit, name, module_arrays):
                        continue
                    found = lookup(unit, name)
                    if found is not None and "device" in found[1].attrs:
                        continue  # CUDA Fortran device array: GPU layout, the thread index leads
                    args = split_top(masked[match.end() : balanced_end(masked, match.end() - 1) - 1])
                    if len(args) < 2:
                        continue
                    inner_at = _subscripts_with(args, loop.index)
                    if 0 in inner_at:
                        ordered += 1
                    elif inner_at and 0 in _subscripts_with(args, outer.index):
                        swapped += 1
                        example = example or name
            if swapped and swapped > ordered:
                yield ctx.hit(
                    statements[loop.start],
                    f"innermost loop over '{loop.index}' strides through '{example}' (its first subscript is the "
                    f"outer index '{outer.index}'): swap the loops",
                )


def _lower_bounds(dims: str) -> list[str | None]:
    """Lower bound of each dimension of an array spec ('1' when implicit, None when deferred/assumed)."""
    bounds: list[str | None] = []
    for extent in split_top(dims):
        if ":" not in extent:
            bounds.append("1" if extent.strip() not in ("*", "..") else None)
            continue
        lower = extent.split(":", 1)[0].strip()
        bounds.append(lower or None)
    return bounds


def _allocated_bounds(unit: Unit, name: str) -> list[str | None] | None:
    """Lower bounds given to *name* by an ``allocate`` in *unit*, None when it is not allocated there."""
    pattern = re.compile(rf"^{name}\s*\(")
    for stmt in unit.statements:
        masked = stmt.masked.strip()
        if stmt.sentinel is not None or not _ALLOCATE_RE.match(masked):
            continue
        start = masked.index("(")
        for item in split_top(masked[start + 1 : balanced_end(masked, start) - 1]):
            if pattern.match(item):
                return _lower_bounds(item[item.index("(") + 1 : balanced_end(item, item.index("(")) - 1])
    return None


def _actual_lower_bounds(unit: Unit, name: str) -> list[str | None] | None:
    found = lookup(unit, name)
    if found is None or not found[1].dims:
        return None
    decl = found[1]
    if "allocatable" in decl.attrs or "pointer" in decl.attrs:
        return _allocated_bounds(found[0], name)
    return _lower_bounds(decl.dims)


def _subscripted(unit: Unit, name: str) -> bool:
    """*name* is subscripted somewhere in the executable statements of *unit*."""
    pattern = re.compile(rf"(?<![%\w]){name}\s*\(")
    return any(
        s.sentinel is None and pattern.search(s.masked) for s in unit.statements if s.line != unit.decls[name].line
    )


@rule(
    "FOR003",
    "lower-bounds-lost-in-assumed-shape",
    summary="An array with non-default lower bounds is passed to an assumed-shape dummy: inside, its bounds restart at 1.",
    rationale="""
        An assumed-shape dummy (`u(:, :)`) takes the *shape* of the actual argument, not its bounds: every
        lower bound becomes 1. When the caller declares an array with ghost cells, `q(1-ng:ni+ng)`, the
        callee's `u(1:ni)` is no longer the interior but starts in the lower ghost layer. Nothing fails:
        indices are in range, just shifted, so neither the compiler nor bounds checking reports it. Declare
        the dummy with the same lower bounds (`u(1-ng:, :)` or explicit shape), or pass the bounds and use
        them. Reported for calls to project procedures whose dummy is assumed-shape without lower bounds.
        """,
    bad="""
        real :: q(1-ng:ni+ng)
        call smooth(q)        ! subroutine smooth(u); real, intent(inout) :: u(:)
        """,
    good="""
        subroutine smooth(u, ng)
          integer, intent(in) :: ng
          real, intent(inout) :: u(1-ng:)
        """,
    default=False,
)
def check_lower_bounds_lost(ctx: LintContext) -> Iterator[Hit]:
    project = ctx.project
    for unit, stmt in code(ctx):
        name = call_name(stmt)
        callee = project.procedure(name) if name else None
        if callee is None or callee.kind != "subroutine":
            continue
        masked = strip_if(stmt.masked.strip())
        start = masked.find("(")
        if start < 0:
            continue
        for position, actual in enumerate(split_top(masked[start + 1 : balanced_end(masked, start) - 1])):
            keyword = re.match(r"^([a-z_]\w*)\s*=(?!=)\s*(.*)$", actual)
            dummy = keyword.group(1) if keyword else (callee.args[position] if position < len(callee.args) else None)
            actual = keyword.group(2) if keyword else actual
            if dummy is None or not re.fullmatch(r"[a-z_]\w*", actual.strip()):
                continue
            dummy_decl = callee.decls.get(dummy)
            if dummy_decl is None or not dummy_decl.dims or {"allocatable", "pointer"} & set(dummy_decl.attrs):
                continue
            if any(extent.strip() != ":" for extent in split_top(dummy_decl.dims)):
                continue
            if not _subscripted(callee, dummy):
                continue  # only passed on: the next callee's dummy decides the bounds
            bounds = _actual_lower_bounds(unit, actual.strip())
            shifted = [b for b in (bounds or []) if b is not None and b.replace(" ", "") != "1"]
            if shifted:
                yield ctx.hit(
                    stmt,
                    f"'{actual.strip()}' has lower bound {shifted[0]}, but dummy '{dummy}' of '{name}' is assumed-shape: "
                    "its bounds restart at 1",
                )


def _final_ranks(project, names: list[str]) -> set[int] | None:
    """Ranks finalised by the final procedures *names* (-1 = any rank); None when one cannot be resolved."""
    ranks: set[int] = set()
    for name in names:
        unit = project.procedure(name)
        if unit is None or not unit.args:
            return None
        if "elemental" in unit.prefixes:
            ranks.add(-1)
            continue
        dims = unit.decls.get(unit.args[0]).dims if unit.args[0] in unit.decls else None
        if dims is not None and dims.strip() == "..":
            ranks.add(-1)
        else:
            ranks.add(len(split_top(dims)) if dims else 0)
    return ranks


@rule(
    "FOR006",
    "array-of-finalizable-type-not-finalised",
    summary="An array of a derived type with final procedures, none of which finalises arrays of that rank.",
    rationale="""
        A final procedure runs only for objects whose rank matches its dummy argument: a final subroutine
        with a scalar dummy finalises scalars, not the elements of an array. When an array of the type is
        deallocated or goes out of scope, nothing is finalised and the resources the finaliser releases
        (allocations, files, device memory) leak. Make the final subroutine `elemental` (or `impure
        elemental`), or add one for each array rank in use.
        """,
    bad="""
        type :: field
        contains
          final :: field_free            ! subroutine field_free(self); type(field) :: self
        end type
        type(field), allocatable :: blocks(:)
        """,
    good="""
        impure elemental subroutine field_free(self)
          type(field), intent(inout) :: self
        """,
)
def check_array_finalisation(ctx: LintContext) -> Iterator[Hit]:
    finalisers = ctx.project.finalisers
    if not finalisers:
        return
    for unit in ctx.units.walk():
        for decl in unit.decls.values():
            match = re.match(r"^type\((\w+)\)$", decl.type_spec)
            if not match or match.group(1) not in finalisers or not decl.dims:
                continue
            rank = len(split_top(decl.dims))
            ranks = _final_ranks(ctx.project, finalisers[match.group(1)])
            if ranks is None or -1 in ranks or rank in ranks:
                continue
            yield Hit(
                line=decl.line or unit.line,
                message=f"'{decl.name}' is a rank-{rank} array of type '{match.group(1)}', whose final procedures "
                f"finalise rank(s) {', '.join(map(str, sorted(ranks)))} only",
                snippet=f"{unit.name}:{decl.name}",
            )


def _local_kinds(unit: Unit | None) -> dict[str, str]:
    """Integer named constants visible in *unit* (own scope first)."""
    kinds: dict[str, str] = {}
    while unit is not None:
        for decl in unit.decls.values():
            if "parameter" in decl.attrs and decl.init is not None and decl.type_spec.startswith("integer"):
                kinds.setdefault(decl.name, decl.init)
        unit = unit.parent
    return kinds


def _precision(ctx: LintContext, unit: Unit, type_spec: str, kinds: dict[str, str]) -> int | None:
    if type_spec.startswith("doubleprecision"):
        return 15
    match = _REAL_KIND_RE.match(type_spec)
    if not match:
        return None
    return ctx.project.real_precision(match.group(1) or match.group(2), kinds)


def _inexact_literals(text: str) -> list[str]:
    """Real literals of default kind in *text* whose value a single-precision real cannot represent exactly."""
    inexact = []
    for match in _REAL_LITERAL_RE.finditer(text):
        value = float(match.group(1))
        if abs(value) < 3.4e38 and struct.unpack("f", struct.pack("f", value))[0] != value:
            inexact.append(match.group(1))
    return inexact


@rule(
    "FOR007",
    "default-real-literal-precision-loss",
    summary="A real literal without kind is assigned to a higher-precision real and cannot be represented in default precision.",
    rationale="""
        A literal without kind suffix is a *default* (single-precision) real, whatever it is assigned to:
        `x = 0.1` with `x` double precision stores 0.100000001490116..., not 0.1. The error (about 1e-8) is
        far above double-precision round-off and silently caps the accuracy of the whole computation.
        Suffix every real literal with the kind of the computation (`0.1_R8P`); literals exactly
        representable in single precision (`0.5`, `2.0`) are not reported, though the suffix keeps the code
        correct when the working precision changes. Kinds are resolved through the project's named
        constants (`R8P = selected_real_kind(15, 307)`, `real64`, ...).
        """,
    bad="""
        real(R8P) :: dt
        dt = 0.1 * cfl
        """,
    good="""
        real(R8P) :: dt
        dt = 0.1_R8P * cfl
        """,
)
def check_default_real_literal(ctx: LintContext) -> Iterator[Hit]:
    for unit in ctx.units.walk():
        kinds = _local_kinds(unit)
        for decl in unit.decls.values():
            if decl.init is None or decl.pointer_init:
                continue
            precision = _precision(ctx, unit, decl.type_spec, kinds)
            if precision is None or precision <= 6:
                continue
            inexact = _inexact_literals(decl.init)
            if inexact:
                yield Hit(
                    line=decl.line or unit.line,
                    message=f"'{inexact[0]}' is a default-kind real: '{decl.name}' gets it rounded to single precision",
                    snippet=f"{unit.name}:{decl.name}={decl.init}",
                )
        for stmt in unit.statements:
            target = assignment(stmt)
            if target is None or target[2]:
                continue
            found = lookup(unit, target[0])
            if found is None:
                continue
            precision = _precision(ctx, unit, found[1].type_spec, kinds)
            if precision is None or precision <= 6:
                continue
            inexact = _inexact_literals(target[3])
            if inexact:
                yield ctx.hit(
                    stmt,
                    f"'{inexact[0]}' is a default-kind real, rounded to single precision before it reaches "
                    f"'{target[0]}'" + (f" ({len(inexact)} such literals)" if len(inexact) > 1 else ""),
                )


@rule(
    "NUM001",
    "uncompensated-global-sum",
    summary="A diagnostic quantity (residual, norm, mass, energy ...) is summed across ranks with `MPI_SUM`.",
    rationale="""
        A floating-point `MPI_SUM` reduction adds the ranks' values in an order that depends on the
        process count and the MPI implementation: the result changes with the decomposition, and with
        many terms its rounding error grows with their number. For conservation checks, convergence
        histories and regression baselines read at round-off level, that noise can hide or fake the
        effect being measured. Sum locally with a pairwise or compensated (Kahan/Neumaier) algorithm, and
        reduce in a fixed order (gather and sum on one rank, or a reproducible reduction) when the
        diagnostic must not depend on the number of ranks. Heuristic: reported for buffers whose name
        looks like a diagnostic.
        """,
    bad="call mpi_allreduce(res_local, residual, 1, MPI_DOUBLE_PRECISION, MPI_SUM, comm, ierr)",
    good="""
        res_local = pairwise_sum(r2)          ! compensated local sum
        call mpi_gather(res_local, 1, MPI_DOUBLE_PRECISION, parts, 1, MPI_DOUBLE_PRECISION, 0, comm, ierr)
        ! rank 0 sums parts in rank order
        """,
    severity="info",
    default=False,
)
def check_uncompensated_global_sum(ctx: LintContext) -> Iterator[Hit]:
    for _, stmt in code(ctx):
        masked = strip_if(stmt.masked.strip())
        match = _GLOBAL_SUM_RE.match(masked)
        if not match:
            continue
        start = masked.index("(")
        args = split_top(masked[start + 1 : balanced_end(masked, start) - 1])
        if len(args) < 5 or args[4].strip() != "mpi_sum" or "integer" in args[3] or "logical" in args[3]:
            continue
        names = " ".join(args[:2])
        if _DIAGNOSTIC_NAME_RE.search(names):
            yield ctx.hit(stmt, f"{match.group(1)} with MPI_SUM on a diagnostic: the result depends on the rank count")
