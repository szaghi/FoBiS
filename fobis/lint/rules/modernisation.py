"""modernisation.py — MDN and PRT rules: modern syntax and portability (wave G3)."""

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

from ...analysis.lexer import _scan
from ...analysis.regions import call_name, strip_if
from ...analysis.units import _ATTR_STMT_RE, _PARAMETER_STMT_RE
from ..rule import Hit, LintContext, rule
from ._common import code, declared_in_scope, replacements

_FORMAT_RE = re.compile(r"^format\s*\(")
_RELATIONAL = {"eq": "==", "ne": "/=", "lt": "<", "le": "<=", "gt": ">", "ge": ">="}
_RELATIONAL_RE = re.compile(r"\.(eq|ne|lt|le|gt|ge)\.")
_CONSTRUCTOR_RE = re.compile(r"\(/|/\)")
_DOUBLE_RE = re.compile(r"^double\s*(precision|complex)\b")
_DOUBLE_LITERAL_RE = re.compile(r"(?<![\w.])(?:\d+\.\d*|\.\d+|\d+)d[+-]?\d+(?!\w)")
_LITERAL_KIND_RE = re.compile(r"^(real|integer|complex|logical)\s*\(\s*(?:kind\s*=\s*)?\d+\s*\)")
_KIND_SUFFIX_RE = re.compile(r"(?<![\w.])(?:\d+\.?\d*(?:[ed][+-]?\d+)?|\.\d+(?:[ed][+-]?\d+)?)_\d+(?!\w)")
_STAR_KIND_RE = re.compile(r"^(real|integer|complex|logical)\s*\*\s*\d+")
_GNU_RANDOM_RE = re.compile(r"(?<![%\w])(rand|srand|irand)\s*\(")
_SYSTEM_RE = re.compile(r"(?<![%\w])system\s*\(")


@rule(
    "MDN001",
    "double-precision",
    summary="A `double precision` (or `double complex`) declaration.",
    rationale="""
        `double precision` fixes the precision in the type name: changing the working precision means
        editing every declaration. A named kind parameter (`real(rk)`, with `rk` from `iso_fortran_env` or
        a project kind module) changes everywhere at once.
        """,
    bad="double precision :: x",
    good="real(real64) :: x",
    equivalent="MOD001",
    default=False,
)
def check_double_precision(ctx: LintContext) -> Iterator[Hit]:
    for _, stmt in code(ctx):
        if _DOUBLE_RE.match(stmt.masked.strip()):
            yield ctx.hit(stmt, "double precision declaration: use real with a named kind parameter")


@rule(
    "MDN002",
    "double-precision-literal",
    summary="A double precision literal with exponent letter `d` (`1.0d0`).",
    rationale="""
        `1.0d0` ties the constant to double precision whatever the kind of the expression it appears in;
        `1.0_rk` follows the project's kind parameter.
        """,
    bad="x = 1.0d-3",
    good="x = 1.0e-3_rk",
    equivalent="MOD002",
    default=False,
)
def check_double_literal(ctx: LintContext) -> Iterator[Hit]:
    for _, stmt in code(ctx):
        if _DOUBLE_LITERAL_RE.search(stmt.masked) and not _FORMAT_RE.match(stmt.masked.strip()):
            yield ctx.hit(stmt, "double precision literal: use a kind suffix (1.0_rk)")


@rule(
    "MDN011",
    "old-style-array-constructor",
    summary="An array constructor written `(/ ... /)` instead of `[ ... ]`.",
    rationale="""
        The square-bracket form has been standard since Fortran 2003; it is shorter and does not look like
        a division. Fixable automatically (`fobis lint --fix`).
        """,
    bad="a = (/ 1, 2, 3 /)",
    good="a = [1, 2, 3]",
    equivalent="MOD011",
)
def check_array_constructor(ctx: LintContext) -> Iterator[Hit]:
    for _, stmt in code(ctx):
        masked = stmt.masked
        if "(/" not in masked or _FORMAT_RE.match(masked.strip()):
            continue
        fixes = replacements(ctx, stmt, _CONSTRUCTOR_RE, lambda m: "[" if m.group(0) == "(/" else "]")
        yield ctx.hit(stmt, "old-style array constructor (/ ... /): use [ ... ]", fixes=fixes)


@rule(
    "MDN021",
    "deprecated-relational-operator",
    summary="A relational operator written `.eq.`, `.ne.`, `.lt.`, `.le.`, `.gt.`, `.ge.`.",
    rationale="""
        The symbolic operators `==`, `/=`, `<`, `<=`, `>`, `>=` have been standard since Fortran 90 and read
        like mathematics. Fixable automatically (`fobis lint --fix`).
        """,
    bad="if (a .eq. b .and. c .ge. 0) then",
    good="if (a == b .and. c >= 0) then",
    equivalent="MOD021",
)
def check_relational_operator(ctx: LintContext) -> Iterator[Hit]:
    for _, stmt in code(ctx):
        found = sorted({m.group(1) for m in _RELATIONAL_RE.finditer(stmt.masked)})
        if found:
            fixes = replacements(ctx, stmt, _RELATIONAL_RE, lambda m: _RELATIONAL[m.group(1)])
            names = ", ".join(f".{op}." for op in found)
            yield ctx.hit(stmt, f"old relational operator {names}: use symbolic operators", fixes=fixes)


@rule(
    "MDN031",
    "include-statement",
    summary="A Fortran `include` line.",
    rationale="""
        `include` pastes text: the included declarations are compiled again in every includer, and nothing
        checks they stay consistent. A module provides the same entities once, with explicit interfaces.
        """,
    bad="include 'constants.inc'",
    good="use constants, only: pi",
    equivalent="MOD031",
    default=False,
)
def check_include(ctx: LintContext) -> Iterator[Hit]:
    for _, stmt in code(ctx):
        if re.match(r"^include\s*['\"]", stmt.masked.strip()):
            yield ctx.hit(stmt, "include line: prefer a module")


@rule(
    "MDN041",
    "out-of-line-attribute",
    summary="An attribute given in a separate statement (`dimension a(n)`, `intent(in) :: x`, `parameter (...)`).",
    rationale="""
        Attribute statements scatter the description of one variable over several lines: the reader must
        collect them to know what the variable is. Give the attributes in its type declaration.
        """,
    bad="""
        real :: a
        dimension a(10)
        intent(in) :: a
        """,
    good="real, dimension(10), intent(in) :: a",
    equivalent="MOD041",
)
def check_out_of_line_attribute(ctx: LintContext) -> Iterator[Hit]:
    for _, stmt in code(ctx):
        masked = stmt.masked.strip()
        match = _ATTR_STMT_RE.match(masked)
        if match:
            attr = re.match(r"\w+", match.group(1)).group(0)
            if attr in ("external", "intrinsic") or (attr == "save" and not match.group(2).strip()):
                continue
            if re.match(r"^\w+\s*(?:\(.*\))?\s*=(?!=)", masked):
                continue  # an assignment to a variable named like an attribute
            yield ctx.hit(stmt, f"'{attr}' given in a separate statement: put it in the type declaration")
        elif _PARAMETER_STMT_RE.match(masked):
            yield ctx.hit(stmt, "parameter statement: use the parameter attribute in the declaration")


@rule(
    "MDN051",
    "superfluous-save",
    summary="`save` in a module specification part.",
    rationale="Module variables are saved implicitly since Fortran 2008: the `save` adds nothing.",
    bad="""
        module state
          real, save :: t
        """,
    good="""
        module state
          real :: t
        """,
    equivalent="MOD051",
)
def check_superfluous_save(ctx: LintContext) -> Iterator[Hit]:
    for unit in ctx.units.walk():
        if unit.kind != "module":
            continue
        for stmt in unit.statements:
            if stmt.sentinel is not None:
                continue
            masked = stmt.masked.strip()
            attributes = masked.split("::")[0] if "::" in masked else ""
            if re.match(r"^save\b(?!\s*=)", masked) or re.search(r",\s*save\s*(?:,|$)", attributes.strip()):
                yield ctx.hit(stmt, "save is implicit for module variables")


@rule(
    "MDN201",
    "old-mpi-module",
    summary="`use mpi` instead of `use mpi_f08`.",
    rationale="""
        The `mpi` module gives only partial argument checking (handles are plain integers, buffers are
        untyped); `mpi_f08` provides typed handles (`type(MPI_Comm)` ...) and optional `ierror`, so the
        compiler catches mismatched arguments.
        """,
    bad="use mpi",
    good="use mpi_f08",
    equivalent="MOD201",
    default=False,
)
def check_old_mpi_module(ctx: LintContext) -> Iterator[Hit]:
    for unit in ctx.units.walk():
        for use in unit.uses:
            if use.module == "mpi":
                yield ctx.hit(use.statement, "use mpi: prefer use mpi_f08")


@rule(
    "PRT011",
    "literal-kind",
    summary="A kind given as a number in a type declaration (`real(8)`, `integer(kind=4)`).",
    rationale="""
        Kind numbers are compiler-specific: `real(8)` is double precision for gfortran and ifx, but kind
        values are not defined by the standard and differ elsewhere (NAG uses 1, 2, 3). Use named
        constants from `iso_fortran_env` (`real64`, `int32`) or `selected_real_kind`.
        """,
    bad="real(8) :: x",
    good="real(real64) :: x",
    equivalent="PORT011",
)
def check_literal_kind(ctx: LintContext) -> Iterator[Hit]:
    for _, stmt in code(ctx):
        if _LITERAL_KIND_RE.match(stmt.masked.strip()):
            yield ctx.hit(stmt, "numeric kind value: use a named kind parameter")


@rule(
    "PRT012",
    "literal-kind-suffix",
    summary="A literal with a numeric kind suffix (`1.0_8`, `10_4`).",
    rationale="Numeric kind values are compiler-specific; suffix the literal with a named kind (`1.0_rk`).",
    bad="x = 1.0_8",
    good="x = 1.0_rk",
    equivalent="PORT012",
)
def check_literal_kind_suffix(ctx: LintContext) -> Iterator[Hit]:
    for _, stmt in code(ctx):
        if _KIND_SUFFIX_RE.search(stmt.masked) and not _FORMAT_RE.match(stmt.masked.strip()):
            yield ctx.hit(stmt, "numeric kind suffix: use a named kind parameter")


@rule(
    "PRT021",
    "star-kind",
    summary="A non-standard `type*size` declaration (`real*8`, `integer*4`).",
    rationale="""
        `real*8` is a common extension, never part of the standard. Use a kind parameter:
        `real(real64)`.
        """,
    bad="real*8 :: x",
    good="real(real64) :: x",
    equivalent="PORT021",
)
def check_star_kind(ctx: LintContext) -> Iterator[Hit]:
    for _, stmt in code(ctx):
        if _STAR_KIND_RE.match(stmt.masked.strip()):
            yield ctx.hit(stmt, "type*size is not standard Fortran: use a kind parameter")


@rule(
    "PRT031",
    "invalid-tab",
    summary="Tab characters in Fortran code (reported once per file).",
    rationale="""
        Tab is not in the Fortran character set. Compilers accept it with a warning (or interpret it
        specially in fixed form), and its width differs between editors, which breaks fixed-form column
        rules. Use spaces.
        """,
    bad="\tx = 1",
    good="    x = 1",
    equivalent="PORT031",
)
def check_tabs(ctx: LintContext) -> Iterator[Hit]:
    lines = []
    for stmt in ctx.source.statements:
        for lineno in range(stmt.line, stmt.end_line + 1):
            if lineno - 1 < len(ctx.source.lines) and lineno not in lines:
                code_part, _ = _scan(ctx.source.lines[lineno - 1], None)
                if "\t" in code_part:
                    lines.append(lineno)
    if lines:
        more = f" (and {len(lines) - 1} more line(s))" if len(lines) > 1 else ""
        yield Hit(line=lines[0], message=f"tab character in code{more}", snippet="tabs")


@rule(
    "PRT061",
    "non-portable-system-call",
    summary="`system()` (a compiler extension) runs a shell command.",
    rationale="The standard `execute_command_line` (Fortran 2008) runs a command portably and reports its status.",
    bad="call system('mkdir -p out')",
    good="call execute_command_line('mkdir -p out', exitstat=status)",
    equivalent="PORT061",
    default=False,
)
def check_system_call(ctx: LintContext) -> Iterator[Hit]:
    for unit, stmt in code(ctx):
        if call_name(stmt) == "system" or (
            _SYSTEM_RE.search(strip_if(stmt.masked)) and not declared_in_scope(unit, "system")
        ):
            yield ctx.hit(stmt, "system() is an extension: use execute_command_line")


@rule(
    "PRT062",
    "gfortran-random-extension",
    summary="The extensions `rand`, `srand`, `irand` generate random numbers.",
    rationale="""
        `rand`/`srand`/`irand` are GNU extensions with a poor generator. The standard `random_number` and
        `random_seed` (or `random_init`, Fortran 2018) are portable.
        """,
    bad="x = rand()",
    good="call random_number(x)",
    equivalent="PORT062",
    default=False,
)
def check_gnu_random(ctx: LintContext) -> Iterator[Hit]:
    for unit, stmt in code(ctx):
        names = {m.group(1) for m in _GNU_RANDOM_RE.finditer(strip_if(stmt.masked))}
        if call_name(stmt) == "srand":
            names.add("srand")
        for name in sorted(n for n in names if not declared_in_scope(unit, n)):
            yield ctx.hit(stmt, f"{name}() is a GNU extension: use random_number")
