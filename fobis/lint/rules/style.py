"""style.py — STY rules: structure and readability that formatters do not fix (wave G4).

Pure formatting (line length, whitespace, keyword case, quotes) is left to formatters such as fprettify and is
not checked. These rules are about how code is organised: units per file, declaration shapes, size of
procedures.
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

from ...analysis import Statement, split_top
from ...analysis.units import _DECL_RE, _find_top, _parse_attrs, _parse_entity, _type_spec_end
from ..rule import Hit, LintContext, rule
from ._common import code, unit_name

MAX_COMPLEXITY = 10
MAX_ARGUMENTS = 8
_DECISION_RE = re.compile(
    r"^(?:\w+\s*:\s*)?(?:if\s*\(|else\s*if\b|do\b(?!\s*=)|case\s*\((?!\s*default)|type\s+is\b|class\s+is\b|rank\s*\("
    r"|where\s*\(|else\s*where\s*\()"
)


def _header_hit(ctx: LintContext, unit, message: str) -> Hit:
    if unit.header is not None:
        return ctx.hit(unit.header, message)
    return Hit(line=unit.line, message=message)


@rule(
    "STY001",
    "multiple-modules",
    summary="A file defines more than one module or submodule.",
    rationale="""
        One module per file makes the file name tell where a module lives, keeps recompilation cascades
        small (every module of a file is rebuilt when any of them changes) and lets a build tool order
        compilation per file without false dependencies.
        """,
    bad="""
        module grid
        end module grid
        module solver
        end module solver
        """,
    good="""
        ! grid.f90
        module grid
        end module grid
        """,
    equivalent="S211",
    default=False,
)
def check_multiple_modules(ctx: LintContext) -> Iterator[Hit]:
    modules = [u for u in ctx.units.units if u.kind in ("module", "submodule")]
    for unit in modules[1:]:
        yield _header_hit(ctx, unit, f"{unit_name(unit)} is not the first module of this file")


@rule(
    "STY002",
    "program-with-module",
    summary="A file defines both a program and a module.",
    rationale="""
        A module in the same file as a program cannot be used by anything else without compiling the
        program too, and the file mixes a library with its driver. Keep modules in their own files.
        """,
    bad="""
        module helpers
        end module helpers
        program main
        end program main
        """,
    good="""
        ! helpers.f90 holds the module, main.f90 the program
        """,
    equivalent="S212",
    default=False,
)
def check_program_with_module(ctx: LintContext) -> Iterator[Hit]:
    kinds = [u.kind for u in ctx.units.units]
    if "program" in kinds and ("module" in kinds or "submodule" in kinds):
        program = next(u for u in ctx.units.units if u.kind == "program")
        yield _header_hit(ctx, program, f"{unit_name(program)} shares its file with a module")


@rule(
    "STY003",
    "function-missing-result",
    summary="A function has no `result(...)` clause.",
    rationale="""
        Without `result` the function's name is also its result variable: inside the function, `f` is the
        value, and a recursive call or a reference to the function as a procedure needs other syntax. A
        named result (`result(r)`) separates the two and reads unambiguously.
        """,
    bad="function norm2d(x, y)",
    good="function norm2d(x, y) result(r)",
    equivalent="S221",
    default=False,
)
def check_function_result(ctx: LintContext) -> Iterator[Hit]:
    for unit in ctx.units.walk():
        if unit.kind == "function" and unit.header is not None and not re.search(r"\bresult\s*\(", unit.header.masked):
            yield ctx.hit(unit.header, f"{unit_name(unit)} has no result clause")


def _declarations(ctx: LintContext) -> Iterator[tuple[Statement, dict[str, str], list[tuple[str, str | None]]]]:
    """(statement, attributes, [(entity, dims)]) of each type-declaration statement with ``::``."""
    for _, stmt in code(ctx):
        masked = stmt.masked.strip()
        if not _DECL_RE.match(masked) or masked.startswith("procedure"):
            continue
        sep = _find_top(masked, "::")
        if sep < 0:
            continue
        attrs = _parse_attrs(masked[_type_spec_end(masked) : sep].lstrip().lstrip(","))
        entities = [(p[0], p[1]) for item in split_top(masked[sep + 2 :]) if (p := _parse_entity(item))]
        yield stmt, attrs, entities


@rule(
    "STY010",
    "inconsistent-array-declaration",
    summary="A declaration has a `dimension` attribute and an entity with its own shape.",
    rationale="""
        In `real, dimension(5) :: x, y(2)` the attribute does not apply to `y`: a reader sees `dimension(5)`
        and assumes every entity has that shape. Declare entities with different shapes in separate
        statements.
        """,
    bad="real, dimension(5) :: x, y(2)",
    good="""
        real, dimension(5) :: x
        real :: y(2)
        """,
    equivalent="S261",
)
def check_inconsistent_array_declaration(ctx: LintContext) -> Iterator[Hit]:
    for stmt, attrs, entities in _declarations(ctx):
        if "dimension" not in attrs:
            continue
        own = [name for name, dims in entities if dims is not None]
        if own:
            yield ctx.hit(stmt, f"'{own[0]}' has its own shape despite the dimension attribute")


@rule(
    "STY011",
    "mixed-scalar-array-declaration",
    summary="One declaration statement declares both scalars and arrays.",
    rationale="""
        `real :: x, y(3)` hides the array among scalars: the shape is easy to miss when reading the
        declaration list. Declare arrays and scalars in separate statements.
        """,
    bad="real :: x, y(3)",
    good="""
        real :: x
        real :: y(3)
        """,
    equivalent="S262",
    default=False,
)
def check_mixed_scalar_array(ctx: LintContext) -> Iterator[Hit]:
    for stmt, attrs, entities in _declarations(ctx):
        if "dimension" in attrs or len(entities) < 2:
            continue
        shaped = {dims is not None for _, dims in entities}
        if shaped == {True, False}:
            yield ctx.hit(stmt, "scalars and arrays in one declaration")


def complexity(statements: list[Statement]) -> int:
    """McCabe cyclomatic complexity of a procedure body: 1 + decision points.

    Decision points: ``if`` (block and one-line), ``else if``, ``do`` (any form), each non-default ``case``,
    ``type is``/``class is``/``rank`` guards, masked ``where``/``elsewhere``.
    """
    return 1 + sum(1 for s in statements if s.sentinel is None and _DECISION_RE.match(s.masked.strip()))


@rule(
    "STY020",
    "too-complex",
    summary=f"A procedure's cyclomatic complexity exceeds {MAX_COMPLEXITY}.",
    rationale=f"""
        Cyclomatic complexity counts the independent paths through a procedure (1 + each `if`, `else if`,
        `do`, `case`, type/rank guard). Above about {MAX_COMPLEXITY} (McCabe's threshold) a procedure is
        hard to test path by path and hard to read; split it into smaller procedures. Nested procedures are
        measured separately.
        """,
    bad="subroutine update_everything(...)   ! 25 branches",
    good="! one procedure per step, each with a few branches",
    equivalent="S901",
    default=False,
)
def check_too_complex(ctx: LintContext) -> Iterator[Hit]:
    for unit in ctx.units.walk():
        if not unit.is_procedure or unit.is_interface_body:
            continue
        value = complexity(unit.statements)
        if value > MAX_COMPLEXITY:
            yield _header_hit(ctx, unit, f"{unit_name(unit)} has cyclomatic complexity {value} (> {MAX_COMPLEXITY})")


@rule(
    "STY021",
    "too-many-arguments",
    summary=f"A procedure has more than {MAX_ARGUMENTS} dummy arguments.",
    rationale="""
        Long argument lists are easy to call with arguments in the wrong order (same types, positional
        calls) and usually mean that several arguments belong together: group them in a derived type.
        """,
    bad="subroutine flux(q, ni, nj, nk, ng, dx, dy, dz, gamma, r)",
    good="subroutine flux(q, grid, gas)",
    equivalent="S902",
    default=False,
)
def check_too_many_arguments(ctx: LintContext) -> Iterator[Hit]:
    for unit in ctx.units.walk():
        if unit.kind in ("subroutine", "function") and not unit.is_interface_body and len(unit.args) > MAX_ARGUMENTS:
            yield _header_hit(ctx, unit, f"{unit_name(unit)} has {len(unit.args)} arguments (> {MAX_ARGUMENTS})")
