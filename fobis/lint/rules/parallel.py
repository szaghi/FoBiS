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
from ._common import declared_in_scope, do_loops, innermost_loop, is_array

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


def _thread_guarded(statements: list[Statement], first: int, idx: int) -> bool:
    """Whether statement *idx* runs on one thread only: inside an ``if`` comparing ``omp_get_thread_num()`` (or a
    variable assigned from it in the region) with ``==``, the hand-written form of ``masked``/``master``."""
    ids = {
        m.group(1)
        for s in statements[first:idx]
        for m in [re.match(r"^\s*(\w+)\s*=\s*omp_get_thread_num\s*\(\s*\)\s*$", s.masked)]
        if m
    }
    names = "|".join(["omp_get_thread_num\\s*\\(\\s*\\)", *map(re.escape, sorted(ids))])
    guard = re.compile(rf"(?:\b(?:{names})\s*(?:==|\.eq\.))|(?:(?:==|\.eq\.)\s*(?:{names}))")

    def condition(masked: str) -> tuple[str, str] | None:
        found = re.match(r"^\s*(?:\w+\s*:\s*)?if\s*\(", masked)
        if not found:
            return None
        start = masked.index("(", found.start())
        close = balanced_end(masked, start)
        return masked[start:close], masked[close:]

    own = condition(statements[idx].masked)
    if own and guard.search(own[0]):
        return True  # a one-line if
    stack: list[bool] = []
    for stmt in statements[first:idx]:
        masked = stmt.masked.strip()
        test = condition(masked)
        if test and re.match(r"^\s*then\s*$", test[1]):
            stack.append(bool(guard.search(test[0])))
        elif re.match(r"^else\b", masked) and stack:
            stack[-1] = False  # the other threads
        elif re.match(r"^end\s*if\b", masked) and stack:
            stack.pop()
    return any(stack)


@dataclass(frozen=True)
class _SharedWrite:
    unit: Unit
    statement: Statement
    name: str
    accumulation: bool
    rhs: str


def _shared_writes(ctx: LintContext) -> Iterator[_SharedWrite]:
    """The first assignment to each shared scalar in each OpenMP parallel region.

    Writes inside serialising constructs (critical, atomic, single, ...) or guarded by a thread-number test
    (``if (omp_get_thread_num() == 0)``) do not count. A write is an
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
            if _thread_guarded(unit.statements, outer.first, idx):
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


_WORKSHARING = frozenset(("do", "do simd", "sections", "single", "workshare"))
_TARGET_DATA = frozenset(("target data", "target enter data", "target exit data", "target update"))


def _nowait(statements: list[Statement], region: Region) -> bool:
    """The worksharing *region* ends without a barrier (``nowait`` on the directive or on its end directive)."""
    if "nowait" in region.directive.clauses:
        return True
    after = region.last + 1
    if after < len(statements) and statements[after].sentinel == "omp":
        end = parse_directive(statements[after])
        return end.is_end and "nowait" in end.clauses
    return False


def _reads(stmt: Statement, name: str) -> bool:
    """*stmt* reads *name* (a write as assignment target alone is not a read)."""
    pattern = re.compile(rf"(?<![%\w]){name}\b")
    target = assignment(stmt)
    if target is None:
        return bool(pattern.search(strip_if(stmt.masked)))
    full = stmt.masked.strip()
    masked = strip_if(full)
    condition = full[: len(full) - len(masked)]  # the condition of a one-line if, '' otherwise
    subscripts = masked[len(target[0]) : len(masked) - len(target[3])].rsplit("=", 1)[0]
    return any(pattern.search(text) for text in (condition, subscripts, target[3]))


def _same_static_loops(statements: list[Statement], first: Region, second: Region) -> bool:
    """Both loops have ``schedule(static)`` and identical headers: OpenMP maps their iterations alike."""
    static = all(
        any(arg.strip().startswith("static") for arg in r.directive.clauses.get("schedule", []))
        for r in (first, second)
    )
    if not static or not (first.is_loop and second.is_loop):
        return False
    heads = []
    for region in (first, second):
        start = next((i for i in range(region.first, region.last + 1) if is_do(statements[i])), None)
        heads.append(re.sub(r"^\w+\s*:\s*", "", statements[start].masked.strip()) if start is not None else None)
    return heads[0] is not None and heads[0] == heads[1]


@rule(
    "OMP004",
    "nowait-dependent-read",
    summary="Data written by a `nowait` worksharing construct is read before the next barrier.",
    rationale="""
        `nowait` removes the barrier at the end of a worksharing construct: a thread that finished its
        share goes on while others are still writing. Reading what the construct wrote, before an explicit
        `!$omp barrier` or the barrier of a later construct, reads values that may not be written yet.
        The one exception the standard guarantees is two loops with `schedule(static)` and the same
        iteration space, where each thread gets the same iterations: such pairs are not reported.
        """,
    bad="""
        !$omp parallel
        !$omp do
        do i = 1, n
          a(i) = f(i)
        end do
        !$omp end do nowait
        !$omp do
        do i = 1, n
          b(i) = a(n - i + 1)    ! another thread may not have written it yet
        end do
        !$omp end do
        !$omp end parallel
        """,
    good="""
        !$omp end do            ! keep the barrier, or add !$omp barrier before the read
        """,
    default=False,
)
def check_nowait_dependent_read(ctx: LintContext) -> Iterator[Hit]:
    for unit in ctx.units.walk():
        statements = unit.statements
        omp = [r for r in regions(statements) if r.directive.sentinel == "omp"]
        worksharing = {r.first: r for r in omp if r.directive.construct in _WORKSHARING}
        by_directive = {r.directive.statement.line: r for r in omp if r.directive.construct in _WORKSHARING}
        for region in worksharing.values():
            if not _nowait(statements, region):
                continue
            parallel = [p for p in omp if p.is_omp_parallel and p.first <= region.first and region.last <= p.last]
            if not parallel or parallel[-1] is region:
                continue
            private = region.directive.variables(*_PRIVATE_CLAUSES) | _do_indices(region.statements)
            written = {t[0] for s in region.statements if (t := assignment(s)) and t[0] not in private}
            if not written:
                continue
            reported: set[str] = set()
            stop_at, current = None, None
            for idx in range(region.last + 1, parallel[-1].last + 1):
                stmt = statements[idx]
                if stmt.sentinel == "omp":
                    directive = parse_directive(stmt)
                    if directive.construct == "barrier":
                        break
                    following = by_directive.get(stmt.line)
                    if following is not None and following is not region:
                        current = following
                        if not _nowait(statements, following):
                            stop_at = following.last
                    continue
                if stmt.sentinel is not None:
                    continue
                if current is not None and _same_static_loops(statements, region, current) and idx <= current.last:
                    continue
                for name in sorted(written - reported):
                    if _reads(stmt, name):
                        reported.add(name)
                        yield ctx.hit(
                            stmt,
                            f"'{name}' is written by the nowait construct at line {region.directive.statement.line} "
                            "and read here before a barrier",
                        )
                if stop_at is not None and idx >= stop_at:
                    break


@rule(
    "OMP005",
    "serialisation-in-innermost-loop",
    summary="An OpenMP `critical` or `atomic` is inside the innermost loop of a parallel loop.",
    rationale="""
        `critical` lets one thread at a time through, `atomic` serialises the threads that update the same
        location: inside the innermost loop they run once per iteration and the parallel loop runs at the
        speed of its serial part, or slower. Accumulate in a private variable (or a `reduction` clause) and
        combine once per thread, outside the loop.
        """,
    bad="""
        !$omp parallel do
        do i = 1, n
          !$omp critical
          total = total + w(i)
          !$omp end critical
        end do
        """,
    good="""
        !$omp parallel do reduction(+:total)
        do i = 1, n
          total = total + w(i)
        end do
        """,
)
def check_serialisation_in_loop(ctx: LintContext) -> Iterator[Hit]:
    for unit in ctx.units.walk():
        statements = unit.statements
        omp = [r for r in regions(statements) if r.directive.sentinel == "omp" and (r.is_loop or r.is_omp_parallel)]
        if not omp:
            continue
        loops = do_loops(statements)
        for idx, stmt in enumerate(statements):
            if stmt.sentinel != "omp":
                continue
            construct = parse_directive(stmt).construct
            if construct not in ("critical", "atomic"):
                continue
            loop = innermost_loop(loops, idx)
            if loop is None or any(loop.start < other.start <= loop.end for other in loops):
                continue
            if any(r.first <= loop.start and loop.end <= r.last for r in omp):
                yield ctx.hit(
                    stmt,
                    f"{construct} inside the innermost loop (line {statements[loop.start].line}) "
                    "of a parallel loop: runs once per iteration",
                )


@rule(
    "OMP006",
    "target-map-in-loop",
    summary="An OpenMP `target` region inside a loop maps data on every iteration, with no `target data` around it.",
    rationale="""
        `map(to: a)` / `map(tofrom: a)` on a `target` construct copies the array to the device when the
        region starts and back when it ends, unless the data is already present. Inside a time or iteration
        loop that means two full transfers per iteration, usually far more expensive than the kernel.
        Make the data resident once: a `!$omp target data` region around the loop, or
        `!$omp target enter data` at allocation and `exit data` at deallocation, then `target update` only
        for what the host really needs.
        """,
    bad="""
        do it = 1, nsteps
          !$omp target teams distribute parallel do map(tofrom: u) map(to: f)
          do i = 1, n
            u(i) = u(i) + dt * f(i)
          end do
        end do
        """,
    good="""
        !$omp target data map(tofrom: u) map(to: f)
        do it = 1, nsteps
          !$omp target teams distribute parallel do
          do i = 1, n
            u(i) = u(i) + dt * f(i)
          end do
        end do
        !$omp end target data
        """,
    default=False,
)
def check_target_map_in_loop(ctx: LintContext) -> Iterator[Hit]:
    resident = ctx.project.enter_data
    for unit in ctx.units.walk():
        statements = unit.statements
        all_regions = regions(statements)
        data = [r for r in all_regions if r.directive.sentinel == "omp" and r.directive.construct == "target data"]
        loops = do_loops(statements)
        for region in all_regions:
            construct = region.directive.construct
            if region.directive.sentinel != "omp" or not construct.startswith("target") or construct in _TARGET_DATA:
                continue
            idx = statements.index(region.directive.statement)
            loop = innermost_loop(loops, idx)
            if loop is None or any(d.first <= idx <= d.last for d in data):
                continue
            mapped = sorted(region.directive.variables("map") - resident)
            if mapped:
                yield ctx.hit(
                    region.directive.statement,
                    f"target region in the loop at line {statements[loop.start].line} maps "
                    f"{', '.join(repr(m) for m in mapped)} on every iteration",
                )


def _device_code(ctx: LintContext, unit: Unit) -> Iterator[tuple[Statement, set[str]]]:
    """Statements executed on the device (in compute regions, or the whole body of a device routine), with the
    variables private to them."""
    if unit.name and unit.name in ctx.project.device_routines and unit.is_procedure:
        for stmt in unit.statements:
            if stmt.sentinel is None:
                yield stmt, set(unit.decls) - set(unit.args)
        return
    for region in _compute_regions(unit):
        private = region.directive.variables("private", "firstprivate", "reduction")
        for stmt in region.statements:
            if stmt.sentinel is None:
                yield stmt, private


def _strided(section: str) -> bool:
    """The array section *section* (``a(i, 1:3)``) is not contiguous: a scalar subscript before a range, or a
    stride."""
    start = section.index("(")
    subscripts = split_top(section[start + 1 : balanced_end(section, start) - 1])
    seen_scalar = False
    for sub in subscripts:
        if ":" in sub:
            if seen_scalar or sub.count(":") == 2:
                return True
        else:
            seen_scalar = True
    return False


@rule(
    "ACC005",
    "strided-section-argument-in-kernel",
    summary="A non-contiguous section of a shared array is passed to a procedure inside OpenACC device code.",
    rationale="""
        A non-contiguous section (`q(b, 1:3)`, `a(i, :)`, `a(1:n:2)`) passed to a procedure is copied into
        a contiguous temporary. Inside a kernel that temporary is not privatised by nvfortran: all threads
        share it and race. The race is invisible while every thread writes the same values (uniform grids,
        constant coefficients) and corrupts results as soon as the values differ. Copy the elements into a
        private fixed-size local before the call, or pass the whole array and the indices.
        """,
    bad="""
        !$acc parallel loop
        do b = 1, nb
          call cell_metrics(dxyz=dxyz_gpu(b, 1:3), vol=vol(b))
        end do
        """,
    good="""
        !$acc parallel loop private(dxyz_b)
        do b = 1, nb
          dxyz_b(1) = dxyz_gpu(b, 1); dxyz_b(2) = dxyz_gpu(b, 2); dxyz_b(3) = dxyz_gpu(b, 3)
          call cell_metrics(dxyz=dxyz_b, vol=vol(b))
        end do
        """,
)
def check_strided_section_in_kernel(ctx: LintContext) -> Iterator[Hit]:
    project = ctx.project
    functions = project.functions()
    for unit in ctx.units.walk():
        for stmt, private in _device_code(ctx, unit):
            masked = strip_if(stmt.masked.strip())
            calls = []
            called = call_name(stmt)
            if called:
                calls.append(masked.find("(", masked.index(called)))
            for match in _FUNCTION_REF_RE.finditer(masked):
                if match.group(1) in functions and not declared_in_scope(unit, match.group(1)):
                    calls.append(match.end() - 1)
            for start in calls:
                if start < 0:
                    continue
                for arg in split_top(masked[start + 1 : balanced_end(masked, start) - 1]):
                    arg = re.sub(r"^[a-z_]\w*\s*=(?!=)\s*", "", arg)
                    match = re.match(r"^([a-z_]\w*)\s*\(", arg)
                    if not match or match.group(1) in private or balanced_end(arg, match.end() - 1) != len(arg):
                        continue
                    if _strided(arg):
                        yield ctx.hit(stmt, f"non-contiguous section '{arg}' passed in device code: a shared temporary")


@rule(
    "ACC007",
    "device-routine-assumed-shape-lower-bound",
    summary="A device routine has an assumed-shape dummy with a non-default lower bound (`q(0:)`, `q(1-ng:)`).",
    rationale="""
        In device code, assumed-shape dummies with explicit lower bounds go through array descriptors that
        nvfortran handles unreliably (wrong offsets, failing launches). Pass the bounds as integer
        arguments and declare the dummy with explicit shape (`q(lo:hi)`), indexing with them.
        """,
    bad="""
        subroutine stencil(q, i)
          !$acc routine seq
          real, intent(in) :: q(1-ng:)
        """,
    good="""
        subroutine stencil(q, lo, hi, i)
          !$acc routine seq
          integer, intent(in) :: lo, hi, i
          real, intent(in) :: q(lo:hi)
        """,
    default=False,
)
def check_device_routine_lower_bound(ctx: LintContext) -> Iterator[Hit]:
    device = ctx.project.device_routines
    for unit in ctx.units.walk():
        if not unit.is_procedure or unit.name not in device:
            continue
        for arg in unit.args:
            decl = unit.decls.get(arg)
            if decl is None or not decl.dims or {"allocatable", "pointer"} & set(decl.attrs):
                continue
            extents = split_top(decl.dims)
            if not all(re.fullmatch(r"[^:]*:", e.strip()) for e in extents):
                continue  # not assumed-shape
            lower = [e.strip()[:-1].strip() for e in extents if e.strip()[:-1].strip() not in ("", "1")]
            if lower:
                yield Hit(
                    line=decl.line or unit.line,
                    message=f"dummy '{arg}' of device routine '{unit.name}' is assumed-shape with lower bound "
                    f"{lower[0]}: pass the bounds explicitly",
                    snippet=f"{unit.name}:{arg}",
                )


_SEND_BUFFERS = {
    "mpi_send": (0,),
    "mpi_ssend": (0,),
    "mpi_bsend": (0,),
    "mpi_rsend": (0,),
    "mpi_isend": (0,),
    "mpi_issend": (0,),
    "mpi_ibsend": (0,),
    "mpi_irsend": (0,),
    "mpi_sendrecv": (0,),
    "mpi_allreduce": (0,),
    "mpi_reduce": (0,),
    "mpi_iallreduce": (0,),
    "mpi_ireduce": (0,),
    "mpi_allgather": (0,),
    "mpi_gather": (0,),
    "mpi_scatter": (0,),
    "mpi_alltoall": (0,),
    "mpi_bcast": (0,),
}
_RECV_BUFFERS = {
    "mpi_recv": (0,),
    "mpi_irecv": (0,),
    "mpi_sendrecv": (5,),
    "mpi_allreduce": (1,),
    "mpi_reduce": (1,),
    "mpi_iallreduce": (1,),
    "mpi_ireduce": (1,),
    "mpi_allgather": (3,),
    "mpi_gather": (3,),
    "mpi_scatter": (3,),
    "mpi_alltoall": (3,),
    "mpi_bcast": (0,),
}
_DATA_CLAUSES = ("copy", "copyin", "copyout", "create", "present", "deviceptr", "pcopy", "pcopyin", "pcreate")


def _updates(statements: list[Statement]) -> list[tuple[int, str, set[str]]]:
    """(index, direction, variables) of the host/device update directives: 'host' (device -> host) or 'device'."""
    found = []
    for idx, stmt in enumerate(statements):
        if stmt.sentinel is None:
            continue
        directive = parse_directive(stmt)
        if directive.construct == "update" and stmt.sentinel == "acc":
            found.append((idx, "host", directive.variables("self", "host")))
            found.append((idx, "device", directive.variables("device")))
        elif directive.construct == "target update":
            found.append((idx, "host", directive.variables("from")))
            found.append((idx, "device", directive.variables("to")))
    return found


@rule(
    "ACC009",
    "mpi-on-device-data-without-update",
    summary="MPI sends or receives a device-resident array with no host update around the call and no `host_data`.",
    rationale="""
        When an array lives on the GPU, the host copy is stale until `!$acc update self(buf)` and the device
        copy is stale after a receive until `!$acc update device(buf)`. An MPI call on the host copy without
        those updates sends old data or leaves the received data on the host only: results look right on
        one rank and diverge as the decomposition is refined. Either stage through the host (update self
        before sending, update device after receiving) or give MPI the device address with
        `!$acc host_data use_device(buf)` (GPU-aware MPI). Reported in the unit of the call only: updates
        done in another procedure are not seen.
        """,
    bad="""
        !$acc data copy(halo)
        call mpi_sendrecv(halo, n, MPI_REAL8, dst, 0, halo_in, n, MPI_REAL8, src, 0, comm, st, ierr)
        """,
    good="""
        !$acc update self(halo)
        call mpi_sendrecv(halo, n, MPI_REAL8, dst, 0, halo_in, n, MPI_REAL8, src, 0, comm, st, ierr)
        !$acc update device(halo_in)
        """,
    default=False,
)
def check_mpi_device_coherence(ctx: LintContext) -> Iterator[Hit]:
    project = ctx.project
    for unit in ctx.units.walk():
        statements = unit.statements
        acc = [r for r in regions(statements) if r.directive.sentinel == "acc"]
        data = [r for r in acc if r.directive.construct == "data"]
        host_data = [r for r in acc if r.directive.construct == "host_data"]
        updates = None
        for idx, stmt in enumerate(statements):
            name = call_name(stmt)
            if name not in _SEND_BUFFERS and name not in _RECV_BUFFERS:
                continue
            args = _call_arguments(strip_if(stmt.masked.strip()))
            resident = set(project.enter_data) | set(project.device_variables)
            for region in data:
                if region.first <= idx <= region.last:
                    resident |= region.directive.variables(*_DATA_CLAUSES)
            use_device = set().union(
                *(r.directive.variables("use_device") for r in host_data if r.first <= idx <= r.last)
            )
            if updates is None:
                updates = _updates(statements)
            for direction, table in (("host", _SEND_BUFFERS), ("device", _RECV_BUFFERS)):
                for position in table.get(name, ()):
                    if position >= len(args):
                        continue
                    base = re.match(r"\s*([a-z_]\w*)", args[position])
                    buf = base.group(1) if base else ""
                    if buf not in resident or buf in use_device:
                        continue
                    if direction == "host":
                        synced = any(i < idx and d == "host" and buf in v for i, d, v in updates)
                    else:
                        synced = any(i > idx and d == "device" and buf in v for i, d, v in updates)
                    if not synced:
                        need = "update self(...) before" if direction == "host" else "update device(...) after"
                        yield ctx.hit(stmt, f"{name} on device-resident '{buf}' without '!$acc {need}' or host_data")


@rule(
    "ACC010",
    "private-array-in-contained-kernel",
    summary="A compute region of a contained (internal) procedure has a private array.",
    rationale="""
        nvfortran has been observed to mis-privatise arrays listed in `private` inside OpenACC kernels of
        *contained* procedures: runtime-sized private arrays get garbage that depends on the gang count,
        and even fixed-size ones can bleed between threads. Advisory: prefer scalar accumulation, or move
        the kernel to a module procedure, and verify against a CPU run.
        """,
    bad="""
        contains
          subroutine fill()
            real :: buf(5)
            !$acc parallel loop private(buf)
        """,
    good="""
        ! module procedure, or scalar temporaries instead of buf(5)
        """,
    severity="info",
    default=False,
)
def check_private_array_contained(ctx: LintContext) -> Iterator[Hit]:
    module_arrays = ctx.project.module_arrays
    for unit in ctx.units.walk():
        parent = unit.parent
        if (
            not unit.is_procedure
            or parent is None
            or parent.kind not in ("subroutine", "function", "program", "module procedure")
        ):
            continue
        for region in _compute_regions(unit):
            arrays = sorted(n for n in region.directive.variables("private") if is_array(unit, n, module_arrays))
            if arrays:
                yield ctx.hit(
                    region.directive.statement,
                    f"private array(s) {', '.join(repr(a) for a in arrays)} in a kernel of contained {unit.kind} "
                    f"'{unit.name}'",
                )
