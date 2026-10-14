"""mpi.py — MPI rules beyond MPI001: buffers of pending requests, collectives in rank branches, deadlocks (wave A3).

The checks follow the statements of one program unit in source order: a request is pending from its
non-blocking call to the first later statement that completes it (or hands it to another procedure). Loops are
not unrolled, so a hazard that needs a second iteration is not seen; what is reported is visible in straight-line
order.
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

from ...analysis import Statement, Unit
from ...analysis.regions import assignment, call_name, strip_if
from ...analysis.units import balanced_end
from ..rule import Hit, LintContext, rule
from ._common import do_loops, innermost_loop, lookup
from .parallel import _REQUEST_POSITION, _call_arguments

_ISEND = frozenset(("mpi_isend", "mpi_issend", "mpi_ibsend", "mpi_irsend"))
_COLLECTIVES = frozenset(
    (
        *(name for name in _REQUEST_POSITION if name not in _ISEND | {"mpi_irecv"}),
        "mpi_barrier",
        "mpi_bcast",
        "mpi_reduce",
        "mpi_allreduce",
        "mpi_gather",
        "mpi_gatherv",
        "mpi_allgather",
        "mpi_allgatherv",
        "mpi_scatter",
        "mpi_scatterv",
        "mpi_alltoall",
        "mpi_alltoallv",
        "mpi_alltoallw",
        "mpi_reduce_scatter",
        "mpi_reduce_scatter_block",
        "mpi_scan",
        "mpi_exscan",
        "mpi_comm_split",
        "mpi_comm_dup",
        "mpi_comm_create",
        "mpi_cart_create",
        "mpi_file_open",
        "mpi_file_close",
        "mpi_win_create",
        "mpi_win_fence",
        "mpi_finalize",
    )
)
_IF_THEN_RE = re.compile(r"^(?:\w+\s*:\s*)?if\s*\(")
_END_IF_RE = re.compile(r"^end\s*if\b")
_SELECT_RE = re.compile(r"^(?:\w+\s*:\s*)?select\s*case\s*\(")
_END_SELECT_RE = re.compile(r"^end\s*select\b")
_ELSE_RE = re.compile(r"^else\b(?!\s*if\b)")
_ELSE_IF_RE = re.compile(r"^else\s*if\s*\(")
_CASE_RE = re.compile(r"^case\s*(?:\(|default\b)")


def _argument(args: list[str], position: int, keyword: str) -> str:
    """The actual argument by keyword or by position ('' when absent)."""
    for arg in args:
        match = re.match(rf"^{keyword}\s*=(?!=)\s*(.*)$", arg)
        if match:
            return match.group(1)
    return args[position] if position < len(args) and "=" not in args[position].split("(")[0] else ""


def _base(designator: str) -> str:
    match = re.match(r"\s*([a-z_]\w*)", designator)
    return match.group(1) if match else ""


def _pending(unit: Unit, idx: int, request: str) -> Iterator[tuple[int, Statement]]:
    """Statements after *idx* while the request *request* is still pending."""
    used = re.compile(rf"(?<![%\w]){request}\b")
    for later in range(idx + 1, len(unit.statements)):
        stmt = unit.statements[later]
        if stmt.sentinel is None and used.search(stmt.masked) and (call_name(stmt) or "") not in _REQUEST_POSITION:
            return  # completed here, or handed to a procedure that may complete it
        yield later, stmt


def _requests(ctx: LintContext, names: frozenset[str]) -> Iterator[tuple[Unit, int, Statement, str, str, str]]:
    """(unit, index, statement, call, buffer, request) of the non-blocking point-to-point calls in *names*.

    Only calls whose buffer is a whole variable: with ``buf(k)`` the message covers part of ``buf`` and accesses to
    other parts are legal.
    """
    for unit in ctx.units.walk():
        for idx, stmt in enumerate(unit.statements):
            name = call_name(stmt)
            if name not in names:
                continue
            args = _call_arguments(strip_if(stmt.masked.strip()))
            buffer = _argument(args, 0, "buf").strip()
            buf = _base(buffer)
            request = _base(_argument(args, _REQUEST_POSITION[name], "request"))
            if buf and request and buffer == buf:  # whole array: an element or section is only part of it
                yield unit, idx, stmt, name, buf, request


@rule(
    "MPI002",
    "isend-buffer-modified-before-completion",
    summary="The buffer of a pending `mpi_isend` is written before the request is completed.",
    rationale="""
        A non-blocking send may read its buffer at any time until `mpi_wait`/`mpi_test` completes the
        request. Writing the buffer in between changes what is sent, depending on timing: the receiver gets
        old values, new values, or a mix, and the run is not reproducible. Complete the request before
        reusing the buffer, or double-buffer.
        """,
    bad="""
        call mpi_isend(halo, n, MPI_REAL8, dst, 0, comm, req, ierr)
        halo = q(1:n)               ! the send may still be reading halo
        call mpi_wait(req, MPI_STATUS_IGNORE, ierr)
        """,
    good="""
        call mpi_isend(halo, n, MPI_REAL8, dst, 0, comm, req, ierr)
        call mpi_wait(req, MPI_STATUS_IGNORE, ierr)
        halo = q(1:n)
        """,
)
def check_isend_buffer_write(ctx: LintContext) -> Iterator[Hit]:
    for unit, idx, stmt, name, buf, request in _requests(ctx, _ISEND):
        for _, later in _pending(unit, idx, request):
            target = assignment(later)
            if target is not None and target[0] == buf:
                yield ctx.hit(later, f"'{buf}' is written while the {name} at line {stmt.line} may still read it")
                break


@rule(
    "MPI003",
    "irecv-buffer-used-before-completion",
    summary="The buffer of a pending `mpi_irecv` is used before the request is completed.",
    rationale="""
        Until `mpi_wait`/`mpi_test` completes an `mpi_irecv`, its buffer holds undefined data: the message
        may arrive before, during or after the access. Reading it gives stale or partial values, writing it
        may be overwritten by the incoming message. Complete the request first.
        """,
    bad="""
        call mpi_irecv(halo, n, MPI_REAL8, src, 0, comm, req, ierr)
        q(0) = halo(1)              ! the message may not be there yet
        call mpi_wait(req, MPI_STATUS_IGNORE, ierr)
        """,
    good="""
        call mpi_irecv(halo, n, MPI_REAL8, src, 0, comm, req, ierr)
        call mpi_wait(req, MPI_STATUS_IGNORE, ierr)
        q(0) = halo(1)
        """,
)
def check_irecv_buffer_use(ctx: LintContext) -> Iterator[Hit]:
    for unit, idx, stmt, _, buf, request in _requests(ctx, frozenset(("mpi_irecv",))):
        used = re.compile(rf"(?<![%\w]){buf}\b")
        for _, later in _pending(unit, idx, request):
            if later.sentinel is None and not (call_name(later) or "").startswith("mpi_") and used.search(later.masked):
                yield ctx.hit(later, f"'{buf}' is used while the mpi_irecv at line {stmt.line} is pending")
                break


def _rank_conditions(unit: Unit, rank_names: set[str]) -> list[str | None]:
    """For each statement of *unit*, the rank variable of the innermost enclosing rank-dependent branch (or None)."""
    rank_re = re.compile(r"(?<!\w)(" + "|".join(map(re.escape, sorted(rank_names))) + r")\b") if rank_names else None

    def on_rank(text: str) -> str | None:
        match = rank_re.search(text) if rank_re else None
        return match.group(1) if match else None

    stack: list[str | None] = []
    result: list[str | None] = []
    for stmt in unit.statements:
        masked = stmt.masked.strip() if stmt.sentinel is None else ""
        enclosing = next((s for s in reversed(stack) if s), None)
        if _IF_THEN_RE.match(masked):
            start = masked.index("(")
            close = balanced_end(masked, start)
            rank = on_rank(masked[start:close])
            if re.match(r"^\s*then\s*$", masked[close:]):
                stack.append(rank)
                result.append(enclosing)
            else:
                result.append(enclosing or rank)  # one-line if: the action depends on the condition
            continue
        if _SELECT_RE.match(masked):
            start = masked.index("(")
            stack.append(on_rank(masked[start : balanced_end(masked, start)]))
            result.append(enclosing)
            continue
        if (_END_IF_RE.match(masked) or _END_SELECT_RE.match(masked)) and stack:
            stack.pop()
        result.append(enclosing)
    return result


def _balanced_collectives(unit: Unit, rank_names: set[str]) -> set[int]:
    """Indices of the collective calls of rank-dependent constructs whose branches ALL call the same collectives in
    the same order (an ``else``/``case default`` included): every rank reaches them, nothing hangs."""
    rank_re = re.compile(r"(?<!\w)(" + "|".join(map(re.escape, sorted(rank_names))) + r")\b")
    balanced: set[int] = set()
    stack: list[dict] = []
    for index, stmt in enumerate(unit.statements):
        masked = stmt.masked.strip() if stmt.sentinel is None else ""
        if _IF_THEN_RE.match(masked):
            start = masked.index("(")
            close = balanced_end(masked, start)
            if re.match(r"^\s*then\s*$", masked[close:]):
                rank = bool(rank_re.search(masked[start:close]))
                stack.append({"rank": rank, "branches": [[]], "default": False})
            continue
        if _SELECT_RE.match(masked):
            start = masked.index("(")
            rank = bool(rank_re.search(masked[start : balanced_end(masked, start)]))
            stack.append({"rank": rank, "branches": [], "default": False})
            continue
        if stack and (_ELSE_IF_RE.match(masked) or _ELSE_RE.match(masked) or _CASE_RE.match(masked)):
            stack[-1]["branches"].append([])
            stack[-1]["default"] |= bool(_ELSE_RE.match(masked)) or masked.startswith(("case default", "casedefault"))
            continue
        if stack and (_END_IF_RE.match(masked) or _END_SELECT_RE.match(masked)):
            frame = stack.pop()
            calls = [item for branch in frame["branches"] for item in branch]
            sequences = [[name for _, name in branch] for branch in frame["branches"]]
            if frame["rank"] and frame["default"] and len(sequences) > 1 and all(s == sequences[0] for s in sequences):
                balanced.update(i for i, _ in calls)
            if stack and stack[-1]["branches"]:
                stack[-1]["branches"][-1].extend(calls)  # a nested construct's calls belong to the enclosing branch
            continue
        name = call_name(stmt)
        if name in _COLLECTIVES and stack and stack[-1]["branches"]:
            stack[-1]["branches"][-1].append((index, name))
    return balanced


@rule(
    "MPI004",
    "collective-in-rank-branch",
    summary="An MPI collective is called inside a branch that depends on the rank.",
    rationale="""
        Every process of the communicator must call a collective (`mpi_bcast`, `mpi_allreduce`,
        `mpi_barrier`, ...), in the same order. Called inside `if (rank == 0)`, the other ranks never reach
        it and the program hangs, or matches it with a different collective and computes garbage. Move the
        collective out of the branch; if the branch selects exactly the members of a sub-communicator
        passed to the call, suppress with a reason. Not reported when every branch of the construct (an
        `else` or `case default` included) calls the same collectives in the same order: every rank reaches
        them. The rank variables are those filled by `mpi_comm_rank` anywhere in the project.
        """,
    bad="""
        if (myrank == 0) then
          read(u, *) dt
          call mpi_bcast(dt, 1, MPI_REAL8, 0, comm, ierr)
        end if
        """,
    good="""
        if (myrank == 0) read(u, *) dt
        call mpi_bcast(dt, 1, MPI_REAL8, 0, comm, ierr)
        """,
)
def check_collective_in_rank_branch(ctx: LintContext) -> Iterator[Hit]:
    rank_names = ctx.project.rank_variables
    if not rank_names:
        return
    for unit in ctx.units.walk():
        conditions = _rank_conditions(unit, rank_names)
        balanced = _balanced_collectives(unit, rank_names)
        for index, (stmt, rank) in enumerate(zip(unit.statements, conditions, strict=True)):
            name = call_name(stmt)
            if rank and name in _COLLECTIVES and index not in balanced:
                yield ctx.hit(stmt, f"collective {name} inside a branch on '{rank}': the other ranks never call it")


@rule(
    "MPI005",
    "blocking-send-before-receive",
    summary="Every rank does a blocking `mpi_send` and then the matching `mpi_recv`: a deadlock for large messages.",
    rationale="""
        `mpi_send` may block until the matching receive starts (always for messages above the eager limit,
        which depends on the MPI library and the network). When all ranks send first and receive after, as
        in a halo exchange written send-then-recv, every rank waits in `mpi_send` for a receive that is
        never posted: the code works on small cases and hangs on large ones. Use `mpi_sendrecv`, or
        non-blocking calls completed by `mpi_waitall`. Reported when the send and the receive are not in
        rank-dependent branches.
        """,
    bad="""
        call mpi_send(sbuf, n, MPI_REAL8, right, 0, comm, ierr)
        call mpi_recv(rbuf, n, MPI_REAL8, left, 0, comm, status, ierr)
        """,
    good="""
        call mpi_sendrecv(sbuf, n, MPI_REAL8, right, 0, rbuf, n, MPI_REAL8, left, 0, comm, status, ierr)
        """,
    default=False,
)
def check_send_before_recv(ctx: LintContext) -> Iterator[Hit]:
    rank_names = ctx.project.rank_variables
    for unit in ctx.units.walk():
        conditions = _rank_conditions(unit, rank_names)
        pending: Statement | None = None
        for stmt, rank in zip(unit.statements, conditions, strict=True):
            name = call_name(stmt)
            if rank:
                continue
            if name in ("mpi_send", "mpi_ssend"):
                pending = pending or stmt
            elif name == "mpi_recv" and pending is not None:
                yield ctx.hit(pending, f"blocking send before the mpi_recv at line {stmt.line} on every rank")
                pending = None
            elif name and name.startswith("mpi_"):
                pending = None


@rule(
    "MPI006",
    "any-source-order-dependent-sum",
    summary="Messages received from `MPI_ANY_SOURCE` are summed in arrival order: the result is not reproducible.",
    rationale="""
        With `MPI_ANY_SOURCE` the messages are processed in the order they arrive, which changes from run to
        run. Floating-point addition is not associative, so a sum accumulated in that order changes in its
        last bits each run, and regression tests at round-off level fail randomly. Receive from each source
        in a fixed order, or store the contributions by `status%MPI_SOURCE` and sum them in rank order.
        """,
    bad="""
        do k = 1, nproc - 1
          call mpi_recv(part, 1, MPI_REAL8, MPI_ANY_SOURCE, 0, comm, status, ierr)
          total = total + part
        end do
        """,
    good="""
        do k = 1, nproc - 1
          call mpi_recv(parts(k), 1, MPI_REAL8, k, 0, comm, status, ierr)
        end do
        total = total + sum(parts)       ! fixed order
        """,
    severity="info",
    default=False,
)
def check_any_source_sum(ctx: LintContext) -> Iterator[Hit]:
    for unit in ctx.units.walk():
        statements = unit.statements
        loops = do_loops(statements)
        for idx, stmt in enumerate(statements):
            if call_name(stmt) != "mpi_recv":
                continue
            args = _call_arguments(strip_if(stmt.masked.strip()))
            if _argument(args, 3, "source").strip() != "mpi_any_source":
                continue
            loop = innermost_loop(loops, idx)
            buf = _base(_argument(args, 0, "buf"))
            if loop is None or not buf:
                continue
            for later in statements[idx + 1 : loop.end]:
                target = assignment(later)
                if target is None or not re.search(rf"\b{buf}\b", target[3]):
                    continue
                if not re.search(rf"(?<![%\w]){target[0]}\b", target[3]):
                    continue
                found = lookup(unit, target[0])
                if found is not None and re.match(r"^(real|doubleprecision|complex)", found[1].type_spec):
                    yield ctx.hit(stmt, f"'{target[0]}' accumulates messages from MPI_ANY_SOURCE in arrival order")
                    break
