"""obsolescent.py — OBS rules: obsolescent and deleted features (wave G2)."""

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

import os
import re
from collections.abc import Iterator

from ...analysis import Statement, Unit
from ...analysis.regions import strip_if
from ...analysis.units import balanced_end
from ..rule import Hit, LintContext, rule

# Specific names of intrinsic functions that are not also generic names (obsolescent since Fortran 2018).
SPECIFIC_INTRINSICS = frozenset(
    [
        "alog",
        "alog10",
        "amax0",
        "amax1",
        "amin0",
        "amin1",
        "amod",
        "cabs",
        "ccos",
        "cexp",
        "clog",
        "csin",
        "csqrt",
        "dabs",
        "dacos",
        "dasin",
        "datan",
        "datan2",
        "dcos",
        "dcosh",
        "ddim",
        "dexp",
        "dint",
        "dlog",
        "dlog10",
        "dmax1",
        "dmin1",
        "dmod",
        "dnint",
        "dsign",
        "dsin",
        "dsinh",
        "dsqrt",
        "dtan",
        "dtanh",
        "float",
        "iabs",
        "idim",
        "idint",
        "idnint",
        "ifix",
        "isign",
        "max0",
        "max1",
        "min0",
        "min1",
        "sngl",
    ]
)
_SPECIFIC_RE = re.compile(r"\b(" + "|".join(sorted(SPECIFIC_INTRINSICS)) + r")\s*\(")
_NOT_ASSIGNMENT = r"(?!\s*(?:\(.*\))?\s*=(?!=))"


def _code(ctx: LintContext) -> Iterator[tuple[Unit, Statement]]:
    """Every code statement (directives excluded) with the unit owning it."""
    for unit in ctx.units.walk():
        for stmt in unit.statements:
            if stmt.sentinel is None:
                yield unit, stmt


def _statement_rule(regex: str, message: str):
    """A check reporting every code statement matching *regex*."""
    pattern = re.compile(regex)

    def check(ctx: LintContext) -> Iterator[Hit]:
        for _, stmt in _code(ctx):
            if pattern.match(stmt.masked):
                yield ctx.hit(stmt, message)

    return check


rule(
    "OBS001",
    "common-block",
    summary="A `common` block.",
    rationale="""
        Common blocks share storage by position, not by name: every program unit must repeat the same
        layout, and a mismatch silently reinterprets memory. They are obsolescent since Fortran 2018. Put
        the shared data in a module.
        """,
    bad="common /state/ t, dt",
    good="""
        module state
          real :: t, dt
        end module state
        """,
    equivalent="OB011",
)(_statement_rule(rf"^common\b{_NOT_ASSIGNMENT}", "common block (obsolescent): use a module"))

rule(
    "OBS002",
    "equivalence-statement",
    summary="An `equivalence` statement.",
    rationale="""
        `equivalence` makes different variables share storage, defeating type checking and optimisation
        (aliasing). It is obsolescent since Fortran 2018. Use `transfer`, pointers, or separate variables.
        """,
    bad="equivalence (a, b)",
    good="b = transfer(a, b)",
    equivalent="OB012",
)(_statement_rule(r"^equivalence\s*\(", "equivalence statement (obsolescent)"))


@rule(
    "OBS003",
    "block-data",
    summary="A `block data` program unit.",
    rationale="""
        `block data` exists only to initialise common blocks and is obsolescent since Fortran 2018.
        Initialise module variables in their module instead.
        """,
    bad="block data init",
    good="""
        module state
          real :: t = 0.0
        end module state
        """,
    equivalent="OB013",
)
def check_block_data(ctx: LintContext) -> Iterator[Hit]:
    for unit in ctx.units.walk():
        if unit.kind == "block data" and unit.header is not None:
            yield ctx.hit(unit.header, "block data unit (obsolescent)")


rule(
    "OBS004",
    "entry-statement",
    summary="An `entry` statement.",
    rationale="""
        `entry` gives a procedure several entry points sharing local variables, which makes control and
        data flow hard to follow. It is obsolescent since Fortran 2008. Write separate procedures that share
        a module-level helper.
        """,
    bad="entry reset(x)",
    good="subroutine reset(x)",
    equivalent="OB021",
)(_statement_rule(rf"^entry\s+\w+\s*(?:\(|$){_NOT_ASSIGNMENT}", "entry statement (obsolescent)"))


@rule(
    "OBS005",
    "specific-intrinsic-name",
    summary="A specific intrinsic name (`dsqrt`, `dabs`, `amax1`, `float` ...) instead of the generic one.",
    rationale="""
        Specific names fix the argument kind (`dsqrt` only accepts double precision), so changing the kind
        of a variable breaks or silently converts the call. The generic names (`sqrt`, `abs`, `max`,
        `real`) work for every kind. Specific names are obsolescent since Fortran 2018.
        """,
    bad="y = dsqrt(x) + float(n)",
    good="y = sqrt(x) + real(n, kind(x))",
    equivalent="OB031",
)
def check_specific_intrinsic(ctx: LintContext) -> Iterator[Hit]:
    for unit, stmt in _code(ctx):
        names = {m.group(1) for m in _SPECIFIC_RE.finditer(stmt.masked)}
        scope: Unit | None = unit
        while scope is not None and names:
            names -= set(scope.decls)  # an array or user function with that name is not the intrinsic
            scope = scope.parent
        for name in sorted(names):
            yield ctx.hit(stmt, f"specific intrinsic name '{name}' (obsolescent): use the generic name")


rule(
    "OBS006",
    "computed-go-to",
    summary="A computed `go to (l1, l2, ...), i`.",
    rationale="""
        A computed GO TO jumps to the i-th label of a list; it is obsolescent since Fortran 95. A
        `select case` construct expresses the same choice with structure.
        """,
    bad="go to (10, 20, 30) mode",
    good="""
        select case (mode)
        case (1)
          ...
        end select
        """,
    equivalent="OB041",
)(_statement_rule(r"^go\s*to\s*\(", "computed go to (obsolescent): use select case"))

rule(
    "OBS007",
    "pause-statement",
    summary="A `pause` statement.",
    rationale="`pause` was deleted from the language in Fortran 95; compilers accept it only as an extension.",
    bad="pause",
    good="read(*, *)   ! or remove it",
    equivalent="OB051",
)(_statement_rule(rf"^pause\b{_NOT_ASSIGNMENT}", "pause statement (deleted in Fortran 95)"))

rule(
    "OBS008",
    "deprecated-character-syntax",
    summary="Old-style character length `character*n` / `character*(*)`.",
    rationale="""
        The `character*n` form is obsolescent since Fortran 95. `character(len=n)` is the modern form and
        is consistent with every other kind and length parameter.
        """,
    bad="character*20 :: name",
    good="character(len=20) :: name",
    equivalent="OB061",
)(_statement_rule(r"^character\s*\*", "character*n length syntax (obsolescent): use character(len=n)"))

rule(
    "OBS009",
    "forall",
    summary="A `forall` statement or construct.",
    rationale="""
        `forall` is obsolescent since Fortran 2018. Its semantics (every right-hand side evaluated before
        any assignment) often forces temporaries and rarely parallelises; `do concurrent` or plain array
        syntax are the replacements.
        """,
    bad="forall (i = 1:n) a(i) = b(i) * 2",
    good="""
        do concurrent (i = 1:n)
          a(i) = b(i) * 2
        end do
        """,
    equivalent="OB071",
)(_statement_rule(r"^(?:\w+\s*:\s*)?forall\s*\(", "forall (obsolescent): use do concurrent or array syntax"))


@rule(
    "OBS010",
    "arithmetic-if",
    summary="An arithmetic `if (x) l1, l2, l3`.",
    rationale="""
        The arithmetic IF branches on the sign of an expression to one of three labels. It was deleted in
        Fortran 2018. Use a block `if` / `select case`.
        """,
    bad="if (x) 10, 20, 30",
    good="""
        if (x < 0) then
          ...
        else if (x == 0) then
          ...
        end if
        """,
    equivalent="OB081",
)
def check_arithmetic_if(ctx: LintContext) -> Iterator[Hit]:
    for _, stmt in _code(ctx):
        masked = stmt.masked
        match = re.match(r"^if\s*\(", masked)
        if not match:
            continue
        rest = masked[balanced_end(masked, match.end() - 1) :]
        if re.fullmatch(r"\s*\d+\s*,\s*\d+\s*,\s*\d+\s*", rest):
            yield ctx.hit(stmt, "arithmetic if (deleted in Fortran 2018)")


_LABELLED_DO = r"^(?:\w+\s*:\s*)?do\s*,?\s*(\d+)\b"
_LABELLED_DO_RE = re.compile(_LABELLED_DO)


def _labelled_dos(unit: Unit) -> Iterator[tuple[Statement, str]]:
    for stmt in unit.statements:
        if stmt.sentinel is None:
            match = _LABELLED_DO_RE.match(stmt.masked)
            if match:
                yield stmt, match.group(1).lstrip("0") or "0"


rule(
    "OBS011",
    "labelled-do-loop",
    summary="A labelled `do 10 i = ...` loop.",
    rationale="""
        The label form of DO is obsolescent since Fortran 2018. `do ... end do` (optionally with a
        construct name) states the loop's extent without a label to match.
        """,
    bad="""
        do 10 i = 1, n
          a(i) = 0.0
        10 continue
        """,
    good="""
        do i = 1, n
          a(i) = 0.0
        end do
        """,
    equivalent="OB091",
)(_statement_rule(_LABELLED_DO, "labelled do loop (obsolescent): use do ... end do"))


@rule(
    "OBS012",
    "shared-do-termination",
    summary="Several `do` loops end on the same labelled statement.",
    rationale="""
        Nested loops sharing one terminal statement (deleted in Fortran 2018) make jumps to the label
        ambiguous and hide the nesting structure. Give each loop its own `end do`.
        """,
    bad="""
        do 10 i = 1, n
        do 10 j = 1, m
        10 a(i, j) = 0.0
        """,
    good="""
        do i = 1, n
          do j = 1, m
            a(i, j) = 0.0
          end do
        end do
        """,
    equivalent="OB092",
)
def check_shared_do_termination(ctx: LintContext) -> Iterator[Hit]:
    for unit in ctx.units.walk():
        seen: dict[str, Statement] = {}
        for stmt, label in _labelled_dos(unit):
            if label in seen:
                yield ctx.hit(
                    stmt, f"do loop shares terminal statement {label} with the loop at line {seen[label].line}"
                )
            else:
                seen[label] = stmt


@rule(
    "OBS013",
    "bad-do-termination",
    summary="A labelled `do` loop ends on a statement other than `continue` or `end do`.",
    rationale="""
        Ending a loop on an action statement (an assignment, a write) was deleted in Fortran 2018 and
        makes the last iteration's work easy to misread as following the loop.
        """,
    bad="""
        do 10 i = 1, n
        10 a(i) = 0.0
        """,
    good="""
        do i = 1, n
          a(i) = 0.0
        end do
        """,
    equivalent="OB093",
)
def check_bad_do_termination(ctx: LintContext) -> Iterator[Hit]:
    for unit in ctx.units.walk():
        labelled: dict[str, Statement] = {}
        for stmt in unit.statements:
            if stmt.label is not None:
                labelled.setdefault(stmt.label.lstrip("0") or "0", stmt)
        for stmt, label in _labelled_dos(unit):
            target = labelled.get(label)
            if target is not None and not re.match(r"^(continue|end\s*do)\s*$", target.masked):
                yield ctx.hit(stmt, f"do loop terminates on a non-continue statement at line {target.line}")


@rule(
    "OBS014",
    "goto-end-do",
    summary="A `go to` jumps to the `end do` of a loop.",
    rationale="""
        Jumping to the labelled `end do` of a loop is the pre-Fortran 90 way of starting the next
        iteration. `cycle` says the same thing without a label, and keeps working when the loop is moved
        or renamed.
        """,
    bad="""
        do i = 1, n
          if (skip(i)) go to 10
          a(i) = 0.0
        10 end do
        """,
    good="""
        do i = 1, n
          if (skip(i)) cycle
          a(i) = 0.0
        end do
        """,
    equivalent="OB094",
)
def check_goto_end_do(ctx: LintContext) -> Iterator[Hit]:
    for unit in ctx.units.walk():
        end_do = {
            stmt.label.lstrip("0") or "0"
            for stmt in unit.statements
            if stmt.label is not None and stmt.sentinel is None and re.match(r"^end\s*do\b", stmt.masked.strip())
        }
        if not end_do:
            continue
        for stmt in unit.statements:
            if stmt.sentinel is not None:
                continue
            match = re.match(r"^go\s*to\s*(\d+)\s*$", strip_if(stmt.masked.strip()))
            if match and (match.group(1).lstrip("0") or "0") in end_do:
                yield ctx.hit(stmt, f"go to the end do labelled {match.group(1)}: use cycle")


def _include_rule(header: str, message: str):
    def check(ctx: LintContext) -> Iterator[Hit]:
        for line, name in ctx.source.includes:
            if os.path.basename(name).lower() == header:
                yield Hit(line=line, message=message, snippet=f"include {header}")

    return check


rule(
    "OBS020",
    "deprecated-mpi-include",
    summary="`include 'mpif.h'` instead of the `mpi_f08` module.",
    rationale="""
        `mpif.h` declares no interfaces: no MPI call is checked by the compiler, and it is deprecated by the
        MPI standard (4.1). `use mpi_f08` gives type-checked, `ierror`-optional bindings.
        """,
    bad="include 'mpif.h'",
    good="use mpi_f08",
    equivalent="OB201",
)(_include_rule("mpif.h", "include of mpif.h (deprecated): use mpi_f08"))

rule(
    "OBS021",
    "deprecated-omp-include",
    summary="`include 'omp_lib.h'` instead of the `omp_lib` module.",
    rationale="""
        `omp_lib.h` is deprecated by the OpenMP specification; the `omp_lib` module provides the same
        routines with explicit interfaces.
        """,
    bad="include 'omp_lib.h'",
    good="use omp_lib",
    equivalent="OB211",
)(_include_rule("omp_lib.h", "include of omp_lib.h (deprecated): use the omp_lib module"))
