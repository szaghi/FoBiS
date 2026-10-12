"""regions.py — OpenMP/OpenACC directive regions and statement-level helpers for parallel-code rules.

A *region* is the span of statements a directive applies to: up to the matching ``end`` directive for block
constructs (``!$omp parallel`` ... ``!$omp end parallel``), the following loop nest for loop constructs
(``!$acc parallel loop``, ``!$omp do``), the next statement for ``atomic``. Clauses are parsed into
``{name: [arguments]}`` with variable lists split and reduction operators dropped.
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
from dataclasses import dataclass, field

from .lexer import Statement
from .units import balanced_end, split_top

# Construct names, longest first so that "parallel do simd" wins over "parallel".
_OMP_CONSTRUCTS = sorted(
    (
        "parallel",
        "do",
        "simd",
        "do simd",
        "parallel do",
        "parallel do simd",
        "parallel loop",
        "loop",
        "sections",
        "parallel sections",
        "section",
        "single",
        "workshare",
        "parallel workshare",
        "critical",
        "atomic",
        "master",
        "masked",
        "ordered",
        "barrier",
        "flush",
        "task",
        "taskloop",
        "taskloop simd",
        "taskwait",
        "target",
        "target data",
        "target enter data",
        "target exit data",
        "target update",
        "target parallel",
        "target parallel do",
        "target parallel do simd",
        "target parallel loop",
        "target simd",
        "target teams",
        "target teams distribute",
        "target teams distribute simd",
        "target teams distribute parallel do",
        "target teams distribute parallel do simd",
        "target teams loop",
        "teams",
        "teams distribute",
        "teams distribute simd",
        "teams distribute parallel do",
        "teams distribute parallel do simd",
        "teams loop",
        "distribute",
        "distribute simd",
        "distribute parallel do",
        "distribute parallel do simd",
        "declare target",
        "declare simd",
        "declare reduction",
        "threadprivate",
    ),
    key=lambda c: -len(c.split()),
)
_ACC_CONSTRUCTS = sorted(
    (
        "parallel",
        "kernels",
        "serial",
        "loop",
        "parallel loop",
        "kernels loop",
        "serial loop",
        "data",
        "enter data",
        "exit data",
        "host_data",
        "update",
        "wait",
        "routine",
        "declare",
        "atomic",
        "cache",
        "init",
        "shutdown",
        "set",
    ),
    key=lambda c: -len(c.split()),
)
_LOOP_WORDS = frozenset(("do", "loop", "simd", "distribute", "taskloop"))
_ACC_COMPUTE = frozenset(("parallel", "kernels", "serial"))
_DO_RE = re.compile(r"^(?:\w+\s*:\s*)?do\b(?!\s*=)")
_LABELLED_DO_RE = re.compile(r"^(?:\w+\s*:\s*)?do\s*,?\s*(\d+)\b")
_END_DO_RE = re.compile(r"^end\s*do\b")
_IF_PREFIX_RE = re.compile(r"^if\s*\(")
_ASSIGN_RE = re.compile(r"^([a-z_]\w*)\s*(\((?:[^()]|\([^()]*\))*\))?\s*(%[^=]*)?=(?!=)")
_CALL_RE = re.compile(r"^call\s+([a-z_]\w*)")
_REDUCTION_OP_RE = re.compile(r"^\s*[^:]+:\s*")
_CLAUSE_NAME_RE = re.compile(r"[\s,]*([a-z_]\w*)\s*")


@dataclass(frozen=True)
class Directive:
    """A parsed directive statement."""

    sentinel: str  # "omp" or "acc"
    construct: str  # e.g. "parallel do", "end parallel", "atomic"; '' when unknown
    clauses: dict[str, list[str]]
    statement: Statement

    @property
    def is_end(self) -> bool:
        return self.construct.startswith("end ")

    def variables(self, *clause_names: str) -> set[str]:
        """Base variable names listed in the given clauses (``a(1:n)`` -> ``a``, ``s%x`` -> ``s``)."""
        names = set()
        for clause in clause_names:
            for item in self.clauses.get(clause, []):
                match = re.match(r"\s*([a-z_]\w*)", item)
                if match:
                    names.add(match.group(1))
        return names


def parse_directive(stmt: Statement) -> Directive:
    """Parse the directive *stmt* (``stmt.sentinel`` must be set)."""
    text = stmt.masked.strip()
    end = text.startswith("end")
    body = re.sub(r"^end\s*", "", text) if end else text
    words = re.split(r"\s+", re.sub(r"[(,].*$", "", body).strip())
    known = _OMP_CONSTRUCTS if stmt.sentinel == "omp" else _ACC_CONSTRUCTS
    construct = ""
    for candidate in known:
        size = len(candidate.split())
        if " ".join(words[:size]) == candidate:
            construct = candidate
            break
    rest = body
    if construct:
        rest = re.sub(r"^" + r"\s+".join(map(re.escape, construct.split())), "", body).strip()
    clauses: dict[str, list[str]] = {}
    pos = 0
    while pos < len(rest):
        match = _CLAUSE_NAME_RE.match(rest, pos)
        if not match or match.end() == pos:
            break
        name, pos = match.group(1), match.end()
        args: list[str] = []
        if rest[pos : pos + 1] == "(":
            close = balanced_end(rest, pos)
            inner = rest[pos + 1 : close - 1]
            if name in ("reduction", "in_reduction", "task_reduction"):
                inner = _REDUCTION_OP_RE.sub("", inner, count=1)
            elif name == "map":
                inner = re.sub(r"^\s*(?:always\s*,\s*)?(?:to|from|tofrom|alloc|release|delete)\s*:\s*", "", inner)
            args = split_top(inner)
            pos = close
        clauses.setdefault(name, []).extend(args)
    return Directive(
        sentinel=stmt.sentinel,
        construct=("end " + construct) if end and construct else construct,
        clauses=clauses,
        statement=stmt,
    )


@dataclass
class Region:
    """Statements governed by a directive.

    Attributes
    ----------
    directive : Directive
    first, last : int
        Indices, in the owning unit's statement list, of the first and last governed statement (``last <
        first`` for an empty region).
    statements : list of Statement
    """

    directive: Directive
    first: int
    last: int
    statements: list[Statement] = field(default_factory=list)

    @property
    def is_loop(self) -> bool:
        return bool(set(self.directive.construct.split()) & _LOOP_WORDS)

    @property
    def is_acc_compute(self) -> bool:
        return self.directive.sentinel == "acc" and bool(set(self.directive.construct.split()) & _ACC_COMPUTE)

    @property
    def is_omp_parallel(self) -> bool:
        words = set(self.directive.construct.split())
        return self.directive.sentinel == "omp" and bool(words & {"parallel", "teams"})


def strip_if(masked: str) -> str:
    """The action statement of a logical IF (``if (c) x = 1`` -> ``x = 1``); *masked* unchanged otherwise."""
    if _IF_PREFIX_RE.match(masked):
        start = masked.index("(")
        rest = masked[balanced_end(masked, start) :].strip()
        if rest and not rest.startswith("then"):
            return rest
    return masked


def assignment(stmt: Statement) -> tuple[str, bool, bool, str] | None:
    """(target base name, subscripted, component, right-hand side) of an assignment statement, else None."""
    if stmt.sentinel is not None:
        return None
    masked = strip_if(stmt.masked.strip())
    match = _ASSIGN_RE.match(masked)
    if not match or match.group(1) in ("if", "where", "forall", "do", "select", "case", "call", "print", "write"):
        return None
    return match.group(1), bool(match.group(2)), bool(match.group(3)), masked[match.end() :]


def call_name(stmt: Statement) -> str | None:
    """Name of the subroutine called by *stmt* (also inside a logical IF), else None."""
    if stmt.sentinel is not None:
        return None
    match = _CALL_RE.match(strip_if(stmt.masked.strip()))
    return match.group(1) if match else None


def is_do(stmt: Statement) -> bool:
    """*stmt* opens a DO loop."""
    return stmt.sentinel is None and bool(_DO_RE.match(stmt.masked.strip()))


def loop_end(statements: list[Statement], start: int) -> int:
    """Index of the statement closing the DO loop opened at *start* (the last index when unterminated)."""
    label = _LABELLED_DO_RE.match(statements[start].masked)
    if label:
        target = label.group(1).lstrip("0")
        for idx in range(start + 1, len(statements)):
            if statements[idx].label is not None and statements[idx].label.lstrip("0") == target:
                return idx
        return len(statements) - 1
    depth = 0
    for idx in range(start, len(statements)):
        stmt = statements[idx]
        if stmt.sentinel is not None:
            continue
        masked = stmt.masked.strip()
        if _DO_RE.match(masked) and not _LABELLED_DO_RE.match(masked):
            depth += 1
        elif _END_DO_RE.match(masked):
            depth -= 1
            if depth == 0:
                return idx
    return len(statements) - 1


def regions(statements: list[Statement]) -> list[Region]:
    """The directive regions found in *statements* (a unit's statement list), in source order."""
    found: list[Region] = []
    for idx, stmt in enumerate(statements):
        if stmt.sentinel is None:
            continue
        directive = parse_directive(stmt)
        if not directive.construct or directive.is_end:
            continue
        if directive.construct == "atomic":
            last = idx + 1 if idx + 1 < len(statements) and statements[idx + 1].sentinel is None else idx
            found.append(Region(directive, idx + 1, last, statements[idx + 1 : last + 1]))
            continue
        closing = _matching_end(statements, idx, directive)
        if closing is not None:
            found.append(Region(directive, idx + 1, closing - 1, statements[idx + 1 : closing]))
        elif set(directive.construct.split()) & _LOOP_WORDS:
            nxt = next((j for j in range(idx + 1, len(statements)) if statements[j].sentinel is None), None)
            if nxt is not None and is_do(statements[nxt]):
                last = loop_end(statements, nxt)
                found.append(Region(directive, nxt, last, statements[nxt : last + 1]))
    return found


def _matching_end(statements: list[Statement], start: int, directive: Directive) -> int | None:
    """Index of the ``end <construct>`` directive closing the directive at *start*, honouring nesting."""
    depth = 0
    for idx in range(start + 1, len(statements)):
        stmt = statements[idx]
        if stmt.sentinel != directive.sentinel:
            continue
        other = parse_directive(stmt)
        if other.construct == directive.construct:
            depth += 1
        elif other.construct == "end " + directive.construct:
            if depth == 0:
                return idx
            depth -= 1
    return None


def enclosing(regions_list: list[Region], index: int) -> Iterator[Region]:
    """Regions containing the statement at *index*, in source order (outermost first)."""
    for region in regions_list:
        if region.first <= index <= region.last:
            yield region
