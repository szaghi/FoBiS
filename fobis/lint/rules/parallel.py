"""parallel.py — OMP, ACC and MPI rules: parallel-programming defects (wave A2).

Distilled from the OpenMP 6.0, OpenACC 3.4 and MPI 5.0 specifications and from GPU/MPI practice. The checks
work on the statements of one program unit (regions do not cross procedure boundaries) plus the project
index for cross-file facts (device routines, device-declared module variables, MPI initialisation).
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
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import pairwise

from ...analysis import Decl, Statement, Unit, split_top
from ...analysis.regions import Region, assignment, call_name, is_do, loop_end, parse_directive, regions, strip_if
from ...analysis.units import balanced_end
from ..rule import Hit, LintContext, rule
from ._common import declared_in_scope

_PRIVATE_CLAUSES = ("private", "firstprivate", "lastprivate", "reduction", "linear")
_SERIALISING = frozenset(("critical", "atomic", "single", "master", "masked", "ordered", "section", "sections"))
_DO_INDEX_RE = re.compile(r"^(?:\w+\s*:\s*)?do\s*(?:\d+\s*,?\s*)?([a-z_]\w*)\s*=")
_DO_CONCURRENT_RE = re.compile(r"^(?:\w+\s*:\s*)?do\s+concurrent\s*\((.*)\)")
_ASSOCIATE_RE = re.compile(r"^(?:\w+\s*:\s*)?associate\s*\(")
_END_ASSOCIATE_RE = re.compile(r"^end\s*associate\b")
_TIMER_RE = re.compile(r"\b(omp_get_wtime|mpi_wtime)\s*\(|^call\s+(system_clock|cpu_time)\b")
_ACC_WAIT_CALL_RE = re.compile(r"^call\s+acc_wait\w*\b")
_FUNCTION_REF_RE = re.compile(r"(?<![%\w])([a-z_]\w*)\s*\(")
# Position of the request argument (0-based) in the non-blocking MPI calls.
_REQUEST_POSITION = {
    "mpi_isend": 6,
    "mpi_issend": 6,
    "mpi_ibsend": 6,
    "mpi_irsend": 6,
    "mpi_irecv": 6,
    "mpi_ibarrier": 1,
    "mpi_ibcast": 5,
    "mpi_ireduce": 7,
    "mpi_iallreduce": 6,
    "mpi_iscan": 6,
    "mpi_iexscan": 6,
    "mpi_ireduce_scatter": 6,
    "mpi_ireduce_scatter_block": 6,
    "mpi_igather": 8,
    "mpi_iscatter": 8,
    "mpi_iallgather": 7,
    "mpi_ialltoall": 7,
    "mpi_igatherv": 9,
    "mpi_iscatterv": 9,
    "mpi_iallgatherv": 8,
    "mpi_ialltoallv": 9,
}


def _lookup(unit: Unit | None, name: str) -> tuple[Unit, Decl] | None:
    """The declaration of *name* visible from *unit* (own scope first, then hosts)."""
    while unit is not None:
        if name in unit.decls:
            return unit, unit.decls[name]
        unit = unit.parent
    return None


def _do_indices(statements: list[Statement]) -> set[str]:
    """Loop variables of the DO and DO CONCURRENT loops among *statements*."""
    names = set()
    for stmt in statements:
        if stmt.sentinel is not None:
            continue
        masked = stmt.masked.strip()
        concurrent = _DO_CONCURRENT_RE.match(masked)
        if concurrent:
            names.update(m.group(1) for m in re.finditer(r"([a-z_]\w*)\s*=", concurrent.group(1)))
            continue
        match = _DO_INDEX_RE.match(masked)
        if match:
            names.add(match.group(1))
    return names


def _threadprivate(unit: Unit) -> set[str]:
    names: set[str] = set()
    scope: Unit | None = unit
    while scope is not None:
        for stmt in scope.statements:
            if stmt.sentinel == "omp" and parse_directive(stmt).construct == "threadprivate":
                inner = re.search(r"\((.*)\)", stmt.masked)
                if inner:
                    names.update(n.strip() for n in inner.group(1).split(",") if re.fullmatch(r"\s*\w+\s*", n))
        scope = scope.parent
    return names


@dataclass(frozen=True)
class _SharedWrite:
    unit: Unit
    statement: Statement
    name: str
    accumulation: bool
    rhs: str


def _shared_writes(ctx: LintContext) -> Iterator[_SharedWrite]:
    """The first assignment to each shared scalar in each OpenMP parallel region.

    Writes inside serialising constructs (critical, atomic, single, ...) do not count. A write is an
    accumulation when the variable's *first* write in the region reads it (``s = s + x``); a variable first
    assigned and then updated in the same iteration is a shared temporary, not an accumulation.
    """
    for unit in ctx.units.walk():
        omp = [r for r in regions(unit.statements) if r.directive.sentinel == "omp"]
        if not any(r.is_omp_parallel for r in omp):
            continue
        threadprivate = _threadprivate(unit)
        seen: set[tuple[int, str]] = set()
        for idx, stmt in enumerate(unit.statements):
            enclosing = [r for r in omp if r.first <= idx <= r.last]
            parallel = [r for r in enclosing if r.is_omp_parallel]
            if not parallel:
                continue
            target = assignment(stmt)
            if target is None:
                continue
            name, subscripted, component, rhs = target
            outer = parallel[0]
            if subscripted or component or (outer.first, name) in seen:
                continue
            if any(set(r.directive.construct.split()) & _SERIALISING for r in enclosing):
                continue
            if any(d in ("private", "firstprivate") for r in enclosing for d in r.directive.clauses.get("default", [])):
                continue
            private = set().union(*(r.directive.variables(*_PRIVATE_CLAUSES) for r in enclosing))
            private |= _do_indices(unit.statements[outer.first : outer.last + 1])
            if name in private or name in threadprivate:
                continue
            found = _lookup(unit, name)
            if found is None:
                continue  # unknown: possibly an array from a used module
            _, decl = found
            if decl.dims or "dimension" in decl.attrs or "parameter" in decl.attrs:
                continue
            seen.add((outer.first, name))
            yield _SharedWrite(unit, stmt, name, bool(re.search(rf"\b{name}\b", rhs)), rhs)


@rule(
    "OMP001",
    "shared-scalar-written-in-parallel-region",
    summary="A shared scalar is assigned inside an OpenMP parallel region: a data race.",
    rationale="""
        Inside a parallel region every variable of the enclosing procedure is shared unless a clause
        says otherwise, so a scalar temporary assigned in the loop body is written by all threads at
        once: each thread may read another thread's value. The loop variables of the region's DO loops
        are private automatically (Fortran rule), nothing else is. List the variable in `private` (or use
        `default(none)` to make the compiler ask for every variable), or protect the write with
        `critical`/`atomic` when the sharing is intended. Offload regions are no exception: in
        `target teams distribute parallel do`, an unmapped scalar is firstprivate to the target region,
        and that single copy is shared by all the threads of its teams. Compilers often privatise such
        scalars as an optimisation, which hides the race until a compiler or a flag changes. Writing the
        same value from every thread (`n = omp_get_num_threads()`) is a race too: use `single`.
        """,
    bad="""
        !$omp parallel do
        do i = 1, n
          tmp = a(i) * 2      ! tmp is shared: race
          b(i) = tmp + 1
        end do
        """,
    good="""
        !$omp parallel do private(tmp)
        do i = 1, n
          tmp = a(i) * 2
          b(i) = tmp + 1
        end do
        """,
)
def check_shared_scalar_write(ctx: LintContext) -> Iterator[Hit]:
    for write in _shared_writes(ctx):
        if not write.accumulation:
            yield ctx.hit(write.statement, f"'{write.name}' is shared and written by every thread (missing private?)")


def _reduction_operator(name: str, rhs: str) -> str:
    rhs = rhs.strip()
    for func in ("max", "min"):
        if re.match(rf"^{func}\s*\(", rhs):
            return func
    match = re.match(rf"^{name}\s*([-+*])", rhs)
    return match.group(1) if match else "+"


@rule(
    "OMP002",
    "accumulation-without-reduction",
    summary="A shared scalar is accumulated inside an OpenMP parallel region without `reduction`.",
    rationale="""
        `s = s + x(i)` in a parallel loop reads and writes the shared `s` from every thread: updates are
        lost and the result changes from run to run. A `reduction(+:s)` clause gives each thread a private
        partial sum and combines them at the end of the region; `atomic` is correct but serialises every
        update.
        """,
    bad="""
        !$omp parallel do
        do i = 1, n
          s = s + x(i)
        end do
        """,
    good="""
        !$omp parallel do reduction(+:s)
        do i = 1, n
          s = s + x(i)
        end do
        """,
)
def check_accumulation(ctx: LintContext) -> Iterator[Hit]:
    for write in _shared_writes(ctx):
        if write.accumulation:
            op = _reduction_operator(write.name, write.rhs)
            yield ctx.hit(
                write.statement, f"'{write.name}' is accumulated by every thread: use reduction({op}:{write.name})"
            )


def _collapse_problem(statements: list[Statement], region: Region) -> str | None:
    """Why the loop nest of *region* cannot be collapsed as requested, None when it can."""
    values = region.directive.clauses.get("collapse", [])
    if not values or not values[0].strip().isdigit():
        return None
    depth = int(values[0])
    first = region.first
    if first >= len(statements) or not is_do(statements[first]):
        return None
    starts = [first]
    for _ in range(depth - 1):
        nxt = starts[-1] + 1
        if nxt >= len(statements) or not is_do(statements[nxt]):
            return f"collapse({depth}) but the loop at line {statements[starts[-1]].line} is not tightly nested"
        starts.append(nxt)
    ends = [loop_end(statements, start) for start in starts]
    for outer, inner in pairwise(ends):
        if outer != inner + 1:
            return f"collapse({depth}) but statements follow the inner loop ending at line {statements[inner].line}"
    return None


def _check_collapse(ctx: LintContext, sentinel: str) -> Iterator[Hit]:
    for unit in ctx.units.walk():
        for region in regions(unit.statements):
            if region.directive.sentinel == sentinel and region.is_loop:
                problem = _collapse_problem(unit.statements, region)
                if problem:
                    yield ctx.hit(region.directive.statement, problem)


_COLLAPSE_RATIONALE = """
    `collapse(n)` merges the iteration spaces of n nested loops into one. The specification requires the
    loops to be tightly nested: no statement between the loop headers or between the `end do`s. Compilers
    reject some violations and mishandle others (the extra statements executed once per collapsed
    iteration, or not at all). Move the statements inside the innermost loop, or collapse fewer levels.
    """
_COLLAPSE_GOOD = """
    do j = 1, m
      do i = 1, n
        a(i, j) = coef(j) * b(i, j)
      end do
    end do
    """


@rule(
    "OMP003",
    "collapse-imperfect-nest",
    summary="`collapse(n)` on OpenMP loops that are not tightly nested.",
    rationale=_COLLAPSE_RATIONALE,
    bad="""
        !$omp parallel do collapse(2)
        do j = 1, m
          c = coef(j)          ! between the loop headers
          do i = 1, n
            a(i, j) = c * b(i, j)
          end do
        end do
        """,
    good="!$omp parallel do collapse(2)\n" + _COLLAPSE_GOOD,
    severity="error",
)
def check_omp_collapse(ctx: LintContext) -> Iterator[Hit]:
    yield from _check_collapse(ctx, "omp")


@rule(
    "ACC011",
    "acc-collapse-imperfect-nest",
    summary="`collapse(n)` on OpenACC loops that are not tightly nested.",
    rationale=_COLLAPSE_RATIONALE,
    bad="""
        !$acc parallel loop collapse(2)
        do j = 1, m
          c = coef(j)          ! between the loop headers
          do i = 1, n
            a(i, j) = c * b(i, j)
          end do
        end do
        """,
    good="!$acc parallel loop collapse(2)\n" + _COLLAPSE_GOOD,
    severity="error",
)
def check_acc_collapse(ctx: LintContext) -> Iterator[Hit]:
    yield from _check_collapse(ctx, "acc")


@rule(
    "OMP007",
    "mpi-in-threaded-region-without-thread-support",
    summary="MPI is called inside an OpenMP parallel region but initialised with `mpi_init`, not `mpi_init_thread`.",
    rationale="""
        `mpi_init` provides the `MPI_THREAD_SINGLE` level: only one thread may exist, let alone call MPI.
        MPI calls made by threads of a parallel region (even in `master`/`single`) need
        `mpi_init_thread` requesting `MPI_THREAD_FUNNELED`, `SERIALIZED` or `MULTIPLE`, and a check of the
        level actually provided. Reported only when the project calls `mpi_init` and never
        `mpi_init_thread`.
        """,
    bad="""
        call mpi_init(ierr)
        ...
        !$omp parallel
        call mpi_send(buf, n, MPI_REAL, dest, tag, comm, ierr)
        !$omp end parallel
        """,
    good="""
        call mpi_init_thread(MPI_THREAD_MULTIPLE, provided, ierr)
        if (provided < MPI_THREAD_MULTIPLE) error stop 'MPI thread level'
        """,
)
def check_mpi_in_threads(ctx: LintContext) -> Iterator[Hit]:
    if not ctx.project.mpi_init or ctx.project.mpi_init_thread:
        return
    for unit in ctx.units.walk():
        parallel = [r for r in regions(unit.statements) if r.is_omp_parallel]
        for idx, stmt in enumerate(unit.statements):
            name = call_name(stmt)
            if name and name.startswith("mpi_") and name not in ("mpi_wtime", "mpi_wtick"):
                if any(r.first <= idx <= r.last for r in parallel):
                    yield ctx.hit(stmt, f"{name} called by OpenMP threads, but MPI was initialised by mpi_init")


def _compute_regions(unit: Unit) -> list[Region]:
    return [r for r in regions(unit.statements) if r.is_acc_compute]


@rule(
    "ACC002",
    "atomic-in-compute-region",
    summary="An `!$acc atomic` inside an OpenACC compute region or device routine.",
    rationale="""
        Atomics serialise the threads that hit the same address and are a frequent sign of a
        parallelisation that does not match the data flow (a scatter where a gather would do, a missing
        reduction). They are correct, but on a GPU they can cost more than the whole kernel. Treat each one
        as a red flag: restructure as a gather or a `reduction` clause when possible, keep it only where
        the scatter is inherent.
        """,
    bad="""
        !$acc parallel loop
        do e = 1, nedges
          !$acc atomic update
          flux(node(e)) = flux(node(e)) + f(e)
        end do
        """,
    good="""
        !$acc parallel loop
        do n = 1, nnodes            ! gather over the edges of each node
          flux(n) = sum(f(edges_of(:, n)))
        end do
        """,
)
def check_acc_atomic(ctx: LintContext) -> Iterator[Hit]:
    device = ctx.project.device_routines
    for unit in ctx.units.walk():
        compute = _compute_regions(unit)
        in_routine = unit.name in device
        for idx, stmt in enumerate(unit.statements):
            if stmt.sentinel != "acc" or parse_directive(stmt).construct != "atomic":
                continue
            if in_routine or any(r.first <= idx <= r.last for r in compute):
                yield ctx.hit(stmt, "atomic in device code: check whether a gather or a reduction can replace it")


def _associate_names(unit: Unit) -> list[tuple[int, int, set[str]]]:
    """(first, last, names) of the associate blocks of *unit* (statement indices)."""
    blocks, stack = [], []
    for idx, stmt in enumerate(unit.statements):
        if stmt.sentinel is not None:
            continue
        masked = stmt.masked.strip()
        if _ASSOCIATE_RE.match(masked):
            start = masked.index("(")
            inner = masked[start + 1 : balanced_end(masked, start) - 1]
            names = {item.split("=>")[0].strip() for item in split_top(inner) if "=>" in item}
            stack.append((idx, names))
        elif _END_ASSOCIATE_RE.match(masked) and stack:
            first, names = stack.pop()
            blocks.append((first, idx, names))
    return blocks


@rule(
    "ACC003",
    "firstprivate-associate-name",
    summary="An `associate` name appears in an OpenACC `firstprivate` clause.",
    rationale="""
        Some compilers (nvfortran among them) mishandle `firstprivate` of an associate name: the private
        copy is not initialised from the associated entity, and the kernel computes with garbage.
        `copyin` gives each gang the value reliably.
        """,
    bad="""
        associate (dx => grid%dx)
          !$acc parallel loop firstprivate(dx)
        """,
    good="""
        associate (dx => grid%dx)
          !$acc parallel loop copyin(dx)
        """,
)
def check_firstprivate_associate(ctx: LintContext) -> Iterator[Hit]:
    for unit in ctx.units.walk():
        blocks = _associate_names(unit)
        if not blocks:
            continue
        for idx, stmt in enumerate(unit.statements):
            if stmt.sentinel != "acc":
                continue
            listed = parse_directive(stmt).variables("firstprivate")
            for first, last, names in blocks:
                if first < idx < last:
                    for name in sorted(listed & names):
                        yield ctx.hit(stmt, f"associate name '{name}' in firstprivate: use copyin")


@rule(
    "ACC004",
    "reduction-into-device-module-variable",
    summary="An OpenACC `reduction` targets a module allocatable declared `!$acc declare create`.",
    rationale="""
        A reduction whose target is a module allocatable made device-resident by `!$acc declare create`
        fails with nvfortran (the kernel does not launch or the result is wrong), while the same code
        works with a local variable. Reduce into a local scalar and assign it to the module variable
        afterwards.
        """,
    bad="""
        module state
          real, allocatable :: total
          !$acc declare create(total)
        ...
        !$acc parallel loop reduction(+:total)
        """,
    good="""
        real :: partial
        partial = 0.0
        !$acc parallel loop reduction(+:partial)
        ...
        total = partial
        """,
    severity="error",
)
def check_reduction_into_device_variable(ctx: LintContext) -> Iterator[Hit]:
    device_vars = ctx.project.device_variables
    if not device_vars:
        return
    for unit in ctx.units.walk():
        for stmt in unit.statements:
            if stmt.sentinel != "acc":
                continue
            for name in sorted(parse_directive(stmt).variables("reduction")):
                var = device_vars.get(name)
                if var is None or not var.allocatable:
                    continue
                found = _lookup(unit, name)
                if found is not None and found[0].kind != "module":
                    continue  # a local variable with the same name
                yield ctx.hit(stmt, f"reduction into '{name}', a declare-create allocatable of module '{var.module}'")


@rule(
    "ACC006",
    "missing-acc-routine",
    summary="A project procedure is called inside an OpenACC compute region but has no `!$acc routine`.",
    rationale="""
        Code executed on the device can only call procedures compiled for the device: each needs an
        `!$acc routine` directive (with its parallelism level, usually `seq`). Without it the compiler
        either fails, or inlines the call only when it can see the body, so the build breaks as soon as
        the procedure moves to another file or the optimisation level changes.
        """,
    bad="""
        !$acc parallel loop
        do i = 1, n
          call flux_cell(q(:, i))      ! flux_cell has no !$acc routine
        end do
        """,
    good="""
        subroutine flux_cell(q)
          !$acc routine seq
          ...
        """,
)
def check_missing_routine(ctx: LintContext) -> Iterator[Hit]:
    project = ctx.project
    functions = project.functions()
    for unit in ctx.units.walk():
        seen: set[tuple[int, str]] = set()
        for region in _compute_regions(unit):
            for stmt in region.statements:
                names = set()
                called = call_name(stmt)
                if called:
                    names.add(called)
                if stmt.sentinel is None:
                    for match in _FUNCTION_REF_RE.finditer(strip_if(stmt.masked)):
                        name = match.group(1)
                        if name in functions and not declared_in_scope(unit, name):
                            names.add(name)
                for name in sorted(names):
                    if (
                        name in project.procedures
                        and name not in project.device_routines
                        and (stmt.line, name) not in seen
                    ):
                        seen.add((stmt.line, name))
                        yield ctx.hit(stmt, f"'{name}' is called on the device but has no '!$acc routine'")


@rule(
    "ACC008",
    "timer-without-acc-wait",
    summary="A timer is read while asynchronous OpenACC work may still be running.",
    rationale="""
        `async` compute and data constructs return immediately: reading the clock right after them
        measures only the launch, not the work. Put `!$acc wait` (or `call acc_wait(...)`) before every
        stop-time read.
        """,
    bad="""
        !$acc parallel loop async(1)
        ...
        call system_clock(t1)
        """,
    good="""
        !$acc parallel loop async(1)
        ...
        !$acc wait
        call system_clock(t1)
        """,
)
def check_timer_without_wait(ctx: LintContext) -> Iterator[Hit]:
    for unit in ctx.units.walk():
        pending: Statement | None = None
        for stmt in unit.statements:
            if stmt.sentinel == "acc":
                directive = parse_directive(stmt)
                if directive.construct == "wait" or "wait" in directive.clauses:
                    pending = None
                elif "async" in directive.clauses:
                    pending = stmt
                continue
            if stmt.sentinel is not None:
                continue
            masked = strip_if(stmt.masked.strip())
            if _ACC_WAIT_CALL_RE.match(masked):
                pending = None
            elif pending is not None and _TIMER_RE.search(masked):
                yield ctx.hit(stmt, f"timer read after async work started at line {pending.line} without '!$acc wait'")


def _call_arguments(masked: str) -> list[str]:
    start = masked.find("(")
    if start < 0:
        return []
    return split_top(masked[start + 1 : balanced_end(masked, start) - 1])


@rule(
    "MPI001",
    "request-never-completed",
    summary="A non-blocking MPI operation stores its request in a local variable that is never completed.",
    rationale="""
        A non-blocking operation (`mpi_isend`, `mpi_irecv`, `mpi_iallreduce` ...) is finished only by a
        completion call on its request (`mpi_wait`, `mpi_waitall`, `mpi_test` ...). If the request lives in
        a local variable that nothing uses afterwards, the buffer may be reused or deallocated while MPI
        still uses it, and the request leaks. Requests kept in dummy arguments or module variables are not
        reported (they may be completed elsewhere).
        """,
    bad="""
        call mpi_isend(buf, n, MPI_DOUBLE_PRECISION, dest, tag, comm, req, ierr)
        ! ... returns without mpi_wait
        """,
    good="""
        call mpi_isend(buf, n, MPI_DOUBLE_PRECISION, dest, tag, comm, req, ierr)
        ...
        call mpi_wait(req, MPI_STATUS_IGNORE, ierr)
        """,
)
def check_request_completed(ctx: LintContext) -> Iterator[Hit]:
    for unit in ctx.units.walk():
        if not unit.is_procedure and unit.kind != "program":
            continue
        for idx, stmt in enumerate(unit.statements):
            name = call_name(stmt)
            position = _REQUEST_POSITION.get(name or "")
            if position is None:
                continue
            args = _call_arguments(strip_if(stmt.masked.strip()))
            keyword = [a.split("=", 1)[1].strip() for a in args if re.match(r"^request\s*=", a)]
            request = keyword[0] if keyword else (args[position] if position < len(args) else "")
            base = re.match(r"[a-z_]\w*", request)
            if base is None:
                continue
            base_name = base.group(0)
            if base_name in unit.args or base_name not in unit.decls:
                continue  # dummy, module or host variable: may be completed elsewhere
            used = re.compile(rf"\b{base_name}\b")
            later = unit.statements[idx + 1 :]
            if not any(used.search(s.masked) and (call_name(s) or "") not in _REQUEST_POSITION for s in later):
                yield ctx.hit(stmt, f"request '{base_name}' of {name} is never completed (mpi_wait/mpi_test)")
