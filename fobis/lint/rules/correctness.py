"""correctness.py — COR rules: bug-prone constructs (wave G1)."""

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

from ...analysis import Decl, Unit, split_top
from ...analysis.units import balanced_end
from ..rule import Hit, LintContext, rule

INTRINSIC_MODULES = frozenset(
    ("iso_fortran_env", "iso_c_binding", "ieee_arithmetic", "ieee_exceptions", "ieee_features")
)
_ALLOC_RE = re.compile(r"^(allocate|deallocate)\s*\(")
_ALLOC_KEYWORDS = ("stat", "errmsg", "source", "mold")


def _unit_name(unit: Unit) -> str:
    return f"{unit.kind} '{unit.name}'" if unit.name else unit.kind


def _header_hit(ctx: LintContext, unit: Unit, message: str) -> Hit:
    if unit.header is not None:
        return ctx.hit(unit.header, message)
    return Hit(line=unit.line, message=message)


def _decl_hit(unit: Unit, decl: Decl, message: str) -> Hit:
    return Hit(line=decl.line or unit.line, message=message, snippet=f"{unit.name}:{decl.name}")


def _is_procedure_dummy(unit: Unit, name: str) -> bool:
    """*name* is a dummy procedure of *unit*: declared ``procedure(...)``, ``external`` or by an interface body."""
    decl = unit.decls.get(name)
    if decl is not None and (decl.type_spec.startswith("procedure") or "external" in decl.attrs):
        return True
    return any(body.name == name for block in unit.children if block.kind == "interface" for body in block.children)


def _top_level(ctx: LintContext) -> Iterator[Unit]:
    """Units that need their own implicit rules: modules, programs, external procedures."""
    for unit in ctx.units.units:
        if unit.kind in ("module", "program") or unit.is_external:
            yield unit


@rule(
    "COR001",
    "implicit-typing",
    summary="A module, program or external procedure has no `implicit none`.",
    rationale="""
        Without `implicit none` an undeclared or misspelled name silently becomes a new variable typed by
        its first letter (`i`-`n` integer, otherwise real). The program compiles and computes with garbage.
        `implicit none` in a module or program also covers every procedure they contain. An `implicit`
        statement mapping letters to types is reported too: it keeps implicit typing alive.
        """,
    bad="""
        module solver
        contains
          subroutine step(n)
            integer, intent(in) :: n
            itr = n + 1   ! typo of 'iter': a new implicit integer
          end subroutine step
        end module solver
        """,
    good="""
        module solver
        implicit none
        ...
        """,
    equivalent="C001",
)
def check_implicit_typing(ctx: LintContext) -> Iterator[Hit]:
    for unit in _top_level(ctx):
        if not unit.implicit_none:
            yield _header_hit(ctx, unit, f"{_unit_name(unit)} has no 'implicit none'")
    for unit in ctx.units.walk():
        for stmt in unit.implicit_mappings:
            yield ctx.hit(stmt, f"implicit typing mapping in {_unit_name(unit)}")


@rule(
    "COR002",
    "interface-implicit-typing",
    summary="An interface body has no `implicit none`.",
    rationale="""
        An interface body is a separate scoping unit: it does not inherit the `implicit none` of the module
        or procedure that contains the interface block. Dummy arguments left undeclared in the body are
        typed implicitly, and the interface then disagrees with the procedure it describes.
        """,
    bad="""
        interface
          subroutine callback(x)
            real :: x
          end subroutine callback
        end interface
        """,
    good="""
        interface
          subroutine callback(x)
            implicit none
            real, intent(inout) :: x
          end subroutine callback
        end interface
        """,
    equivalent="C002",
)
def check_interface_implicit_typing(ctx: LintContext) -> Iterator[Hit]:
    for unit in ctx.units.walk():
        if unit.is_interface_body and unit.kind in ("subroutine", "function") and not unit.implicit_none:
            yield _header_hit(ctx, unit, f"interface body {_unit_name(unit)} has no 'implicit none'")


@rule(
    "COR003",
    "implicit-external-procedures",
    summary="`implicit none` does not forbid implicit external procedures (`implicit none (type, external)`).",
    rationale="""
        Plain `implicit none` still lets a call to an unknown name compile as a reference to an external
        procedure with an implicit interface: a misspelled procedure name surfaces only at link time, and
        argument mismatches never. Fortran 2018 `implicit none (type, external)` turns both into compile
        errors.
        """,
    bad="implicit none",
    good="implicit none (type, external)",
    equivalent="C003",
    default=False,
)
def check_implicit_external(ctx: LintContext) -> Iterator[Hit]:
    for unit in _top_level(ctx):
        if unit.implicit_none and not unit.implicit_none_external:
            yield _header_hit(ctx, unit, f"{_unit_name(unit)} allows implicit external procedures")


@rule(
    "COR010",
    "missing-intent",
    summary="A dummy argument has no `intent`.",
    rationale="""
        `intent` documents how a procedure uses each argument and lets the compiler reject writes to
        `intent(in)` data and reads of `intent(out)` data before definition. Without it, an argument the
        caller passes as a constant or expression can be modified, which is undefined behaviour. Dummy
        procedures are exempt (`intent` does not apply to them), and so are `value` dummies (the procedure
        works on a copy: the caller's actual argument cannot change).
        """,
    bad="""
        subroutine scale(a, s)
          real :: a(:), s
        """,
    good="""
        subroutine scale(a, s)
          real, intent(inout) :: a(:)
          real, intent(in)    :: s
        """,
    equivalent="C061",
)
def check_missing_intent(ctx: LintContext) -> Iterator[Hit]:
    for unit in ctx.units.walk():
        if unit.kind not in ("subroutine", "function"):
            continue
        for arg in unit.args:
            decl = unit.decls.get(arg)
            if decl is not None and ("intent" in decl.attrs or "value" in decl.attrs):
                continue
            if _is_procedure_dummy(unit, arg):
                continue
            message = f"dummy argument '{arg}' of {_unit_name(unit)} has no intent"
            yield _decl_hit(unit, decl, message) if decl is not None else _header_hit(ctx, unit, message)


@rule(
    "COR011",
    "assumed-size",
    summary="A dummy array is assumed-size (`a(*)`, `a(n,*)`).",
    rationale="""
        An assumed-size array carries no extent for its last dimension: the procedure cannot check bounds,
        whole-array operations on it are forbidden, and the compiler cannot verify the caller. Use an
        assumed-shape (`a(:)`) or explicit-shape (`a(n)`) dummy instead. Procedures with `bind(c)` are
        exempt: there an assumed-size array (e.g. `character(c_char) :: s(*)`) is the idiomatic C array.
        """,
    bad="real, intent(in) :: a(*)",
    good="real, intent(in) :: a(:)",
    equivalent="C071",
)
def check_assumed_size(ctx: LintContext) -> Iterator[Hit]:
    for unit in ctx.units.walk():
        if unit.header is not None and re.search(r"\bbind\s*\(\s*c\b", unit.header.masked):
            continue
        for arg in unit.args:
            decl = unit.decls.get(arg)
            if decl is None or not decl.dims:
                continue
            dims = split_top(decl.dims)
            if dims and (dims[-1] == "*" or dims[-1].endswith(":*")):
                yield _decl_hit(unit, decl, f"dummy argument '{arg}' of {_unit_name(unit)} is assumed-size")


def _implicitly_saved(unit: Unit, pointer: bool) -> Iterator[Decl]:
    if not unit.is_procedure or unit.save_all:
        return
    for decl in unit.decls.values():
        if decl.init is None or decl.pointer_init != pointer:
            continue
        if decl.name in unit.args or "parameter" in decl.attrs or "save" in decl.attrs:
            continue
        yield decl


@rule(
    "COR020",
    "initialisation-in-declaration",
    summary="A procedure's local variable is initialised in its declaration, which implies `save`.",
    rationale="""
        In Fortran an initialiser in a declaration is not executed at each call: it gives the variable the
        SAVE attribute and sets it once, before the program starts. `integer :: count = 0` keeps the value
        of the previous call, and in multi-threaded code (OpenMP, OpenACC) the single static copy is shared
        by every thread, a data race. Assign the initial value in an executable statement, or write `save`
        explicitly when persistence is intended.
        """,
    bad="""
        subroutine accumulate(x)
          real, intent(in) :: x
          real :: total = 0.0   ! set once, then keeps growing across calls
        """,
    good="""
        subroutine accumulate(x)
          real, intent(in) :: x
          real :: total
          total = 0.0
        """,
    equivalent="C081",
)
def check_initialisation_in_declaration(ctx: LintContext) -> Iterator[Hit]:
    for unit in ctx.units.walk():
        for decl in _implicitly_saved(unit, pointer=False):
            yield _decl_hit(
                unit, decl, f"'{decl.name}' in {_unit_name(unit)} is initialised in its declaration (implicit save)"
            )


@rule(
    "COR021",
    "pointer-initialisation-in-declaration",
    summary="A procedure's local pointer is initialised in its declaration (`=> null()`), which implies `save`.",
    rationale="""
        Pointer initialisation in a declaration gives the pointer the SAVE attribute: after the first call
        it keeps whatever association the previous call left, possibly to deallocated memory. Nullify it
        with an executable statement instead.
        """,
    bad="real, pointer :: p(:) => null()",
    good="""
        real, pointer :: p(:)
        nullify(p)
        """,
    equivalent="C082",
)
def check_pointer_initialisation(ctx: LintContext) -> Iterator[Hit]:
    for unit in ctx.units.walk():
        for decl in _implicitly_saved(unit, pointer=True):
            yield _decl_hit(
                unit, decl, f"pointer '{decl.name}' in {_unit_name(unit)} is initialised in its declaration"
            )


@rule(
    "COR030",
    "external-procedure",
    summary="A procedure is declared `external`.",
    rationale="""
        An `external` declaration gives the procedure an implicit interface: the compiler checks neither
        the number nor the type of the arguments of its calls. Put the procedure in a module (or declare an
        explicit interface) so that every call is checked.
        """,
    bad="external solve",
    good="use solvers, only: solve",
    equivalent="C091",
)
def check_external_procedure(ctx: LintContext) -> Iterator[Hit]:
    for unit in ctx.units.walk():
        for decl in unit.decls.values():
            if "external" in decl.attrs:
                yield _decl_hit(unit, decl, f"'{decl.name}' is declared external in {_unit_name(unit)}")


@rule(
    "COR031",
    "procedure-not-in-module",
    summary="A subroutine or function is defined outside a module (an external procedure).",
    rationale="""
        External procedures have implicit interfaces at every call site that does not repeat an interface
        block, so argument mismatches go undetected. Module procedures get explicit interfaces for free.
        """,
    bad="""
        subroutine helper(x)
          ...
        end subroutine helper
        """,
    good="""
        module helpers
        contains
          subroutine helper(x)
            ...
          end subroutine helper
        end module helpers
        """,
    equivalent="C092",
)
def check_procedure_not_in_module(ctx: LintContext) -> Iterator[Hit]:
    for unit in ctx.units.units:
        if unit.is_external and unit.kind != "module procedure":
            yield _header_hit(ctx, unit, f"{_unit_name(unit)} is not in a module")


@rule(
    "COR040",
    "use-all",
    summary="A `use` statement imports everything (no `only:` list).",
    rationale="""
        Without `only:` every public entity of the module enters the scope: names collide or shadow local
        ones silently, and a reader cannot tell where a name comes from. `only:` makes the dependency
        explicit and keeps scopes small.
        """,
    bad="use penf",
    good="use penf, only: R8P, I4P",
    equivalent="C121",
)
def check_use_all(ctx: LintContext) -> Iterator[Hit]:
    for unit in ctx.units.walk():
        for use in unit.uses:
            if not use.only:
                yield ctx.hit(use.statement, f"'use {use.module}' has no 'only:' list")


@rule(
    "COR041",
    "missing-intrinsic",
    summary="An intrinsic module is used without the `intrinsic` keyword.",
    rationale="""
        `use iso_fortran_env` picks up a user module of the same name if one is on the module path.
        `use, intrinsic :: iso_fortran_env` always gets the compiler's module.
        """,
    bad="use iso_fortran_env, only: real64",
    good="use, intrinsic :: iso_fortran_env, only: real64",
    equivalent="C122",
)
def check_missing_intrinsic(ctx: LintContext) -> Iterator[Hit]:
    for unit in ctx.units.walk():
        for use in unit.uses:
            if use.module in INTRINSIC_MODULES and use.nature != "intrinsic":
                yield ctx.hit(use.statement, f"intrinsic module '{use.module}' used without 'intrinsic'")


@rule(
    "COR050",
    "missing-accessibility-statement",
    summary="A module has no default accessibility statement (`private` or `public`).",
    rationale="""
        Without a default the module exports everything it declares or uses, including helpers and the
        entities of every module it uses. Start with `private` and mark the API `public` explicitly.
        """,
    bad="""
        module grid
        implicit none
        """,
    good="""
        module grid
        implicit none
        private
        public :: grid_t
        """,
    equivalent="C131",
)
def check_missing_accessibility(ctx: LintContext) -> Iterator[Hit]:
    for unit in ctx.units.units:
        if unit.kind == "module" and unit.default_access is None:
            yield _header_hit(ctx, unit, f"{_unit_name(unit)} has no default accessibility statement")


def _alloc_items(masked: str) -> tuple[list[str], str | None]:
    """Objects and ``stat=`` variable of an allocate/deallocate statement."""
    start = masked.index("(")
    inner = masked[start + 1 : balanced_end(masked, start) - 1]
    objects, stat = [], None
    for item in split_top(inner):
        key = re.match(r"^(\w+)\s*=(?!=)", item)
        if key and key.group(1) in _ALLOC_KEYWORDS:
            if key.group(1) == "stat":
                stat = item[key.end() :].strip()
        elif not re.match(r"^\w+(\s*\(.*\))?\s*::", item):  # skip a type-spec "real ::"
            objects.append(item)
    return objects, stat


def _allocations(ctx: LintContext) -> Iterator[tuple[Unit, int]]:
    """(unit, index) of every allocate/deallocate statement."""
    for unit in ctx.units.walk():
        for idx, stmt in enumerate(unit.statements):
            if stmt.sentinel is None and _ALLOC_RE.match(stmt.masked):
                yield unit, idx


@rule(
    "COR060",
    "unchecked-stat",
    summary="The `stat=` variable of an `allocate`/`deallocate` is never read afterwards.",
    rationale="""
        Passing `stat=` tells the runtime not to stop on failure: the error is reported only through the
        variable. If nothing reads it, an allocation failure is silently ignored and the program continues
        with an unallocated array.
        """,
    bad="""
        allocate(a(n), stat=ierr)
        a = 0.0
        """,
    good="""
        allocate(a(n), stat=ierr)
        if (ierr /= 0) error stop 'cannot allocate a'
        """,
    equivalent="C181",
)
def check_unchecked_stat(ctx: LintContext) -> Iterator[Hit]:
    for unit, idx in _allocations(ctx):
        stmt = unit.statements[idx]
        _, stat = _alloc_items(stmt.masked)
        base = re.match(r"\w+", stat or "")
        if base is None:
            continue
        used = re.compile(rf"\b{base.group(0)}\b")
        if not any(used.search(later.masked) for later in unit.statements[idx + 1 :]):
            yield ctx.hit(stmt, f"stat variable '{stat}' is never checked")


@rule(
    "COR061",
    "multiple-allocations-with-stat",
    summary="One `allocate`/`deallocate` with `stat=` handles several objects.",
    rationale="""
        When the statement fails, `stat` does not say which object failed, and the others may or may not
        have been allocated: the error handling cannot know what to clean up. Allocate one object per
        statement when checking `stat`.
        """,
    bad="allocate(a(n), b(n), stat=ierr)",
    good="""
        allocate(a(n), stat=ierr)
        ...
        allocate(b(n), stat=ierr)
        """,
    equivalent="C182",
)
def check_multiple_allocations(ctx: LintContext) -> Iterator[Hit]:
    for unit, idx in _allocations(ctx):
        stmt = unit.statements[idx]
        objects, stat = _alloc_items(stmt.masked)
        if stat and len(objects) > 1:
            yield ctx.hit(stmt, f"{len(objects)} objects share one stat variable '{stat}'")
