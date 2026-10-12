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
from itertools import pairwise

from ...analysis import Decl, Statement, Unit, split_top
from ...analysis.regions import strip_if
from ...analysis.units import _TYPE_DEF_RE, _find_top, _parse_attrs, _parse_entity, _type_spec_end, balanced_end
from ..rule import Hit, LintContext, rule
from ._common import code, do_loops, innermost_loop, physical_code

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


@rule(
    "COR022",
    "missing-default-pointer-initialisation",
    summary="A pointer component of a derived type has no default initialisation (`=> null()`).",
    rationale="""
        A pointer component without default initialisation starts with an *undefined* association status,
        not a disassociated one: `associated(obj%p)` on a fresh object is not allowed and returns garbage
        in practice, so code that tests it before use crashes or follows a wild pointer. `=> null()` in
        the component declaration makes every new object start disassociated.
        """,
    bad="""
        type :: node
          type(node), pointer :: next
        end type node
        """,
    good="""
        type :: node
          type(node), pointer :: next => null()
        end type node
        """,
    equivalent="C101",
)
def check_pointer_component_init(ctx: LintContext) -> Iterator[Hit]:
    for unit in ctx.units.walk():
        depth, bindings = 0, False
        for stmt in unit.statements:
            if stmt.sentinel is not None:
                continue
            masked = stmt.masked.strip()
            if _TYPE_DEF_RE.match(masked):
                depth, bindings = depth + 1, False
                continue
            if re.match(r"^end\s*type\b", masked):
                depth = max(depth - 1, 0)
                continue
            if not depth or bindings:
                continue
            if masked == "contains":
                bindings = True
                continue
            sep = _find_top(masked, "::")
            if sep < 0:
                continue
            attrs = _parse_attrs(masked[_type_spec_end(masked) : sep].lstrip().lstrip(","))
            if "pointer" not in attrs:
                continue
            for item in split_top(masked[sep + 2 :]):
                parsed = _parse_entity(item)
                if parsed is not None and parsed[2] is None:
                    yield ctx.hit(stmt, f"pointer component '{parsed[0]}' has no default initialisation")


@rule(
    "COR062",
    "stat-without-errmsg",
    summary="An `allocate`/`deallocate` has `stat=` but no `errmsg=`.",
    rationale="""
        `stat=` only tells that the statement failed; `errmsg=` gets the runtime's explanation (already
        allocated, out of memory, ...). Without it the error handler can only print a number.
        """,
    bad="allocate(a(n), stat=ierr)",
    good="allocate(a(n), stat=ierr, errmsg=msg)",
    equivalent="C183",
    default=False,
)
def check_stat_without_errmsg(ctx: LintContext) -> Iterator[Hit]:
    for unit, idx in _allocations(ctx):
        stmt = unit.statements[idx]
        _, stat = _alloc_items(stmt.masked)
        if stat and not re.search(r"\berrmsg\s*=", stmt.masked):
            yield ctx.hit(stmt, f"stat variable '{stat}' without errmsg")


_SELECT_RE = re.compile(r"^(?:\w+\s*:\s*)?select\s*(case|type|rank)\s*\(")
_DEFAULT_RE = {"case": r"^case\s+default\b", "type": r"^class\s+default\b", "rank": r"^rank\s+default\b"}


def _missing_default(ctx: LintContext, which: str) -> Iterator[Statement]:
    """``select <which>`` constructs without a default branch."""
    for unit in ctx.units.walk():
        stack: list[list] = []  # [kind, statement, has default]
        for stmt in unit.statements:
            if stmt.sentinel is not None:
                continue
            masked = stmt.masked.strip()
            opened = _SELECT_RE.match(masked)
            if opened:
                stack.append([opened.group(1), stmt, False])
            elif re.match(r"^end\s*select\b", masked) and stack:
                kind, start, has_default = stack.pop()
                if kind == which and not has_default:
                    yield start
            elif stack and re.match(_DEFAULT_RE[stack[-1][0]], masked):
                stack[-1][2] = True


@rule(
    "COR070",
    "missing-default-case",
    summary="A `select case` construct has no `case default`.",
    rationale="""
        When no case matches, a `select case` without `case default` does nothing, silently. A value that
        was not foreseen (a new option, a corrupted input) then flows on unhandled. Add `case default`, even
        if only to stop with an error that names the unexpected value.
        """,
    bad="""
        select case (scheme)
        case ('weno5')
          call weno5(q)
        case ('weno7')
          call weno7(q)
        end select
        """,
    good="""
        select case (scheme)
        case ('weno5')
          call weno5(q)
        case ('weno7')
          call weno7(q)
        case default
          error stop 'unknown scheme: '//scheme
        end select
        """,
    equivalent="C011",
)
def check_missing_default_case(ctx: LintContext) -> Iterator[Hit]:
    for stmt in _missing_default(ctx, "case"):
        yield ctx.hit(stmt, "select case without 'case default'")


@rule(
    "COR071",
    "missing-class-default",
    summary="A `select type` construct has no `class default`.",
    rationale="""
        A `select type` without `class default` silently skips every dynamic type it does not list: an
        extension added later, or an unexpected argument, is ignored instead of reported. Add
        `class default` with an error, unless ignoring the other types is the intent.
        """,
    bad="""
        select type (q)
        type is (real(R8P))
          call apply(q)
        end select
        """,
    good="""
        select type (q)
        type is (real(R8P))
          call apply(q)
        class default
          error stop 'unsupported type'
        end select
        """,
    default=False,
)
def check_missing_class_default(ctx: LintContext) -> Iterator[Hit]:
    for stmt in _missing_default(ctx, "type"):
        yield ctx.hit(stmt, "select type without 'class default'")


@rule(
    "COR072",
    "missing-rank-default",
    summary="A `select rank` construct has no `rank default`.",
    rationale="""
        An assumed-rank dummy can have any rank up to 15: a `select rank` listing only some ranks silently
        does nothing for the others. Add `rank default` that reports the unsupported rank.
        """,
    bad="""
        select rank (a)
        rank (1)
          call apply_1d(a)
        end select
        """,
    good="""
        select rank (a)
        rank (1)
          call apply_1d(a)
        rank default
          error stop 'unsupported rank'
        end select
        """,
    default=False,
)
def check_missing_rank_default(ctx: LintContext) -> Iterator[Hit]:
    for stmt in _missing_default(ctx, "rank"):
        yield ctx.hit(stmt, "select rank without 'rank default'")


@rule(
    "COR080",
    "magic-number-in-array-size",
    summary="An array is declared with a literal size other than 0 or 1.",
    rationale="""
        `real :: flux(5)` hard-codes a size that other code must repeat, and the copies drift apart. Name
        it once (`integer, parameter :: nvar = 5`) and declare `flux(nvar)`.
        """,
    bad="real(R8P) :: q(5, 100)",
    good="real(R8P) :: q(nvar, ncell)",
    equivalent="C031",
    default=False,
)
def check_magic_array_size(ctx: LintContext) -> Iterator[Hit]:
    for unit in ctx.units.walk():
        for decl in unit.decls.values():
            if not decl.dims:
                continue
            literals = [
                bound
                for extent in split_top(decl.dims)
                for bound in extent.split(":")
                if bound.strip().lstrip("+-").isdigit() and bound.strip().lstrip("+-") not in ("0", "1")
            ]
            if literals:
                yield _decl_hit(unit, decl, f"'{decl.name}' is declared with the literal size {literals[0].strip()}")


_IO_RE = re.compile(r"^(read|write|open|close|inquire|rewind|backspace|endfile|flush|wait)\s*\(")


@rule(
    "COR081",
    "magic-io-unit",
    summary="An I/O statement uses a literal unit number.",
    rationale="""
        Literal unit numbers collide: a library and the program both opening unit 10 silently share (or
        close) one file, and units 5 and 6 are only conventionally the terminal. Open files with
        `newunit=` and use `input_unit`/`output_unit`/`error_unit` from `iso_fortran_env`.
        """,
    bad="""
        open(10, file='mesh.dat')
        read(10, *) n
        """,
    good="""
        open(newunit=u, file='mesh.dat')
        read(u, *) n
        """,
    equivalent="C032",
    default=False,
)
def check_magic_io_unit(ctx: LintContext) -> Iterator[Hit]:
    for _, stmt in code(ctx):
        masked = strip_if(stmt.masked.strip())
        match = _IO_RE.match(masked)
        if not match:
            continue
        start = masked.index("(")
        specs = split_top(masked[start + 1 : balanced_end(masked, start) - 1])
        unit = next((s.split("=", 1)[1] for s in specs if re.match(r"^unit\s*=", s)), None)
        if unit is None and specs and "=" not in specs[0]:
            unit = specs[0]
        if unit is not None and unit.strip().isdigit():
            yield ctx.hit(stmt, f"{match.group(1)} on the literal unit {unit.strip()}")


@rule(
    "COR082",
    "missing-action-specifier",
    summary="An `open` statement has no `action=` specifier.",
    rationale="""
        Without `action=` the file is opened with a processor-dependent action, usually read-write: an
        input file can be modified by mistake, and opening a read-only file may fail. State the intent
        with `action='read'`, `'write'` or `'readwrite'`.
        """,
    bad="open(newunit=u, file='mesh.dat')",
    good="open(newunit=u, file='mesh.dat', action='read')",
    equivalent="C043",
    default=False,
)
def check_missing_action(ctx: LintContext) -> Iterator[Hit]:
    for _, stmt in code(ctx):
        masked = strip_if(stmt.masked.strip())
        if re.match(r"^open\s*\(", masked) and not re.search(r"\baction\s*=", masked):
            yield ctx.hit(stmt, "open without action=")


_EXIT_CYCLE_RE = re.compile(r"^(exit|cycle)\s*(\w*)\s*$")


def _exit_cycle(ctx: LintContext) -> Iterator[tuple[Statement, str, str | None]]:
    """(statement, keyword, name of the innermost enclosing loop) of each exit/cycle without a construct name."""
    for unit in ctx.units.walk():
        loops = do_loops(unit.statements)
        for idx, stmt in enumerate(unit.statements):
            if stmt.sentinel is not None:
                continue
            match = _EXIT_CYCLE_RE.match(strip_if(stmt.masked.strip()))
            if not match or match.group(2):
                continue
            loop = innermost_loop(loops, idx)
            if loop is not None:
                yield stmt, match.group(1), loop.name


@rule(
    "COR090",
    "missing-exit-or-cycle-label",
    summary="An `exit` or `cycle` inside a named DO loop does not name the loop.",
    rationale="""
        A loop was given a name to make control flow explicit; a bare `exit`/`cycle` inside it refers to
        the innermost loop, which is that loop today but silently changes when an inner loop is added.
        Write `exit name` / `cycle name`.
        """,
    bad="""
        cells: do i = 1, n
          if (done(i)) cycle
        end do cells
        """,
    good="""
        cells: do i = 1, n
          if (done(i)) cycle cells
        end do cells
        """,
    equivalent="C141",
)
def check_missing_exit_label(ctx: LintContext) -> Iterator[Hit]:
    for stmt, keyword, name in _exit_cycle(ctx):
        if name:
            yield ctx.hit(stmt, f"'{keyword}' in the named loop '{name}' should be '{keyword} {name}'")


@rule(
    "COR091",
    "exit-or-cycle-in-unlabelled-loop",
    summary="An `exit` or `cycle` appears in a DO loop that has no construct name.",
    rationale="""
        In nested loops a bare `exit`/`cycle` acts on the innermost loop only, which is easy to misread.
        Naming the loop and the statement (`exit cells`) states which loop is meant.
        """,
    bad="""
        do i = 1, n
          if (done(i)) exit
        end do
        """,
    good="""
        cells: do i = 1, n
          if (done(i)) exit cells
        end do cells
        """,
    equivalent="C142",
    default=False,
)
def check_exit_in_unlabelled_loop(ctx: LintContext) -> Iterator[Hit]:
    for stmt, keyword, name in _exit_cycle(ctx):
        if not name:
            yield ctx.hit(stmt, f"'{keyword}' in a loop without a construct name")


_NAMED_OPEN_RE = re.compile(
    r"^([a-z_]\w*)\s*:\s*(if\s*\(.*\)\s*then|select\s*(?:case|type|rank)|associate|block|critical|where|forall)\b"
)
_OPEN_RE = {
    "if": re.compile(r"^(?:\w+\s*:\s*)?if\s*\(.*\)\s*then$"),
    "select": re.compile(r"^(?:\w+\s*:\s*)?select\s*(?:case|type|rank)\b"),
    "associate": re.compile(r"^(?:\w+\s*:\s*)?associate\s*\("),
    "block": re.compile(r"^(?:\w+\s*:\s*)?block$"),
    "critical": re.compile(r"^(?:\w+\s*:\s*)?critical\b"),
    "where": re.compile(r"^(?:\w+\s*:\s*)?where\s*\(.*\)$"),
    "forall": re.compile(r"^(?:\w+\s*:\s*)?forall\s*\(.*\)$"),
}
_CONSTRUCT_END_RE = re.compile(r"^end\s*(if|select|associate|block|critical|where|forall|do)\b\s*(\w*)")


def _block_construct_end(statements: list[Statement], start: int, kind: str) -> int | None:
    """Index of the ``end <kind>`` closing the construct opened at *start*, honouring nesting."""
    depth = 0
    for idx in range(start + 1, len(statements)):
        masked = statements[idx].masked.strip()
        if statements[idx].sentinel is not None:
            continue
        if kind in ("where", "forall"):
            opener = _OPEN_RE[kind].match(masked) and masked.endswith(")")
            opener = opener and balanced_end(masked, masked.index("(")) == len(masked)
        else:
            opener = _OPEN_RE[kind].match(masked)
        if opener:
            depth += 1
            continue
        end = _CONSTRUCT_END_RE.match(masked)
        if end and end.group(1) == kind:
            if depth == 0:
                return idx
            depth -= 1
    return None


@rule(
    "COR092",
    "missing-end-label",
    summary="The `end` statement of a named construct does not repeat the construct name.",
    rationale="""
        When a construct has a name (`outer: do`), the standard requires its `end` statement to repeat it
        (`end do outer`); compilers reject the code otherwise. Reported here so the error shows up with the
        other findings, before a build.
        """,
    bad="""
        outer: do i = 1, n
        end do
        """,
    good="""
        outer: do i = 1, n
        end do outer
        """,
    severity="error",
    equivalent="C143",
)
def check_missing_end_label(ctx: LintContext) -> Iterator[Hit]:
    for unit in ctx.units.walk():
        statements = unit.statements
        loops = {loop.start: loop for loop in do_loops(statements)}
        for idx, stmt in enumerate(statements):
            if stmt.sentinel is not None:
                continue
            masked = stmt.masked.strip()
            if idx in loops and loops[idx].name:
                name, end = loops[idx].name, loops[idx].end
                kind = "do"
            else:
                opened = _NAMED_OPEN_RE.match(masked)
                if not opened:
                    continue
                name, kind = opened.group(1), re.match(r"\w+", opened.group(2)).group(0)
                if kind in ("where", "forall") and balanced_end(masked, masked.index("(")) != len(masked):
                    continue  # a where/forall statement, not a construct
                end = _block_construct_end(statements, idx, kind)
            if end is None or end == idx:
                continue
            closing = _CONSTRUCT_END_RE.match(statements[end].masked.strip())
            if closing and closing.group(1) == kind and closing.group(2) != name:
                yield ctx.hit(statements[end], f"'end {kind}' of the construct '{name}' does not repeat its name")


def _logical_if(stmt: Statement) -> bool:
    masked = stmt.masked.strip()
    return stmt.sentinel is None and re.match(r"^if\s*\(", masked) is not None and strip_if(masked) != masked


@rule(
    "COR100",
    "misleading-inline-if-semicolon",
    summary="A statement follows a one-line `if` after a semicolon: it is not conditional.",
    rationale="""
        In `if (c) a = 1; b = 2` only `a = 1` depends on the condition: the semicolon ends the `if`
        statement, and `b = 2` always executes, although the line reads as if both were guarded. Use an
        `if ... then ... end if` block or put the second statement on its own line.
        """,
    bad="if (err /= 0) print *, 'failed'; stop",
    good="""
        if (err /= 0) then
          print *, 'failed'
          stop
        end if
        """,
    equivalent="C151",
)
def check_inline_if_semicolon(ctx: LintContext) -> Iterator[Hit]:
    statements = ctx.source.statements
    for stmt, nxt in pairwise(statements):
        if _logical_if(stmt) and nxt.sentinel is None and nxt.line == stmt.end_line:
            yield ctx.hit(nxt, "this statement follows a one-line if on the same line, but always executes")


@rule(
    "COR101",
    "misleading-inline-if-continuation",
    summary="A one-line `if` continues its action on the next line.",
    rationale="""
        `if (c) &` followed by an indented statement on the next line looks like a block `if`. Whoever adds
        a second indented statement below expects it to be conditional too, and it is not. Use an
        `if ... then ... end if` block when the action does not fit on the line.
        """,
    bad="""
        if (verbose) &
          call report(state)
        """,
    good="""
        if (verbose) then
          call report(state)
        end if
        """,
    equivalent="C152",
)
def check_inline_if_continuation(ctx: LintContext) -> Iterator[Hit]:
    for _, stmt in code(ctx):
        if stmt.end_line == stmt.line or not _logical_if(stmt):
            continue
        first = next(physical_code(ctx, stmt), None)
        if first is None:
            continue
        text = first[1]
        match = re.match(r"^\s*(?:\d+\s+)?if\s*\(", text, re.IGNORECASE)
        if not match:
            continue
        close = balanced_end(text, match.end() - 1)
        if close < len(text) or text.rstrip().endswith(")"):
            if text[close:].strip() in ("", "&"):
                yield ctx.hit(stmt, "the action of this one-line if is on a continuation line")


_INQUIRY_RE = re.compile(r"\b(present|allocated|associated)\s*\(")
_CONDITION_RE = re.compile(r"^(?:\w+\s*:\s*)?(?:else\s*if|if|do\s+while)\s*\(")


@rule(
    "COR110",
    "nonportable-shortcircuit-inquiry",
    summary="A condition tests `present`/`allocated`/`associated` and uses the same entity in one expression.",
    rationale="""
        Fortran does not short-circuit `.and.`/`.or.`: in `present(x) .and. x > 0` the compiler may evaluate
        `x > 0` even when `x` is absent, which is invalid and crashes with some compilers and options.
        Nest the tests (`if (present(x)) then; if (x > 0) ...`) or use a local copy set from the optional
        argument.
        """,
    bad="if (present(tol) .and. tol > 0) eps = tol",
    good="""
        if (present(tol)) then
          if (tol > 0) eps = tol
        end if
        """,
    equivalent="C161",
)
def check_shortcircuit_inquiry(ctx: LintContext) -> Iterator[Hit]:
    for _, stmt in code(ctx):
        masked = stmt.masked.strip()
        opened = _CONDITION_RE.match(masked)
        if not opened:
            continue
        start = opened.end() - 1
        condition = masked[start : balanced_end(masked, start)]
        if not re.search(r"\.(and|or)\.", condition):
            continue
        reported = set()
        for match in _INQUIRY_RE.finditer(condition):
            close = balanced_end(condition, match.end() - 1)
            args = split_top(condition[match.end() : close - 1])
            if not args or args[0] in reported:
                continue
            entity = args[0]
            pattern = re.compile(rf"(?<![\w%]){re.escape(entity)}(?!\w)")
            rest = condition
            for other in _INQUIRY_RE.finditer(condition):
                end = balanced_end(condition, other.end() - 1)
                other_args = split_top(condition[other.end() : end - 1])
                if other_args and other_args[0] == entity:
                    rest = rest[: other.start()] + " " * (end - other.start()) + rest[end:]
            if pattern.search(rest):
                reported.add(entity)
                yield ctx.hit(stmt, f"'{entity}' is tested with {match.group(1)}() and used in the same condition")


_TRANSFER_RE = re.compile(r"^(return|stop|error\s*stop|exit|cycle|go\s*to\s*\d+)\b(?!\s*=(?!=))")
_REACHABLE_RE = re.compile(r"^(end|else|case\b|class\s+(is|default)\b|type\s+is\b|rank\b|contains$|entry\b|format\b)")


@rule(
    "COR120",
    "unreachable-statement",
    summary="A statement follows `return`, `stop`, `exit`, `cycle` or `go to` in the same block: it never runs.",
    rationale="""
        Code after an unconditional transfer of control cannot execute unless it carries a label that some
        `go to` targets. It is usually a leftover of debugging (an early `return` above real work) or a
        misplaced statement that was meant to run before the transfer.
        """,
    bad="""
        x = x + 1
        return
        print *, x
        """,
    good="""
        x = x + 1
        print *, x
        return
        """,
    equivalent="C191",
)
def check_unreachable(ctx: LintContext) -> Iterator[Hit]:
    for unit in ctx.units.walk():
        statements = unit.statements
        for stmt, nxt in pairwise(statements):
            if stmt.sentinel is not None or nxt.sentinel is not None or nxt.label is not None:
                continue
            if not _TRANSFER_RE.match(stmt.masked.strip()) or _REACHABLE_RE.match(nxt.masked.strip()):
                continue
            yield ctx.hit(nxt, f"unreachable: follows '{stmt.masked.strip().split()[0]}' at line {stmt.line}")
