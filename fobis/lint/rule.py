"""rule.py — lint rules, findings and the rule registry."""

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

import hashlib
import re
import textwrap
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..analysis import FileUnits, SourceFile, Statement
    from ..analysis.project import ProjectIndex

SEVERITIES = ("error", "warning", "info")
FAMILIES = {
    "COR": "Correctness",
    "OBS": "Obsolescent",
    "MDN": "Modernisation",
    "PRT": "Portability",
    "FOR": "Fortran practice",
    "OMP": "OpenMP",
    "ACC": "OpenACC",
    "MPI": "MPI",
    "LNT": "Linter",
}


@dataclass(frozen=True)
class Edit:
    """A mechanical fix: replace columns ``[start, end)`` of physical line *line* (1-based) by *text*."""

    line: int
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class Hit:
    """What a rule check reports: where, what, and the code it is about."""

    line: int
    message: str
    end_line: int | None = None
    snippet: str = ""
    fixes: tuple[Edit, ...] = ()


@dataclass(frozen=True)
class Finding:
    """A rule violation in a file.

    Attributes
    ----------
    rule : str
        Rule id.
    path : str
        File path as reported.
    line, end_line : int
        Lines spanned by the offending statement.
    message : str
    severity : str
    snippet : str
        Normalised offending code; with the rule and path it identifies the finding independently of its
        line number (baseline fingerprint).
    """

    rule: str
    path: str
    line: int
    message: str
    severity: str
    end_line: int = 0
    snippet: str = ""
    fixes: tuple[Edit, ...] = ()

    @property
    def fingerprint(self) -> str:
        """Line-independent identity of the finding."""
        basis = f"{self.rule}|{self.path}|{' '.join((self.snippet or self.message).split())}"
        return hashlib.sha1(basis.encode()).hexdigest()[:16]


@dataclass
class LintContext:
    """What a rule check receives for one file."""

    path: str
    source: SourceFile
    units: FileUnits
    project: ProjectIndex

    def hit(self, stmt: Statement, message: str, fixes: tuple[Edit, ...] = ()) -> Hit:
        """A `Hit` on the lines of *stmt*."""
        return Hit(line=stmt.line, end_line=stmt.end_line, message=message, snippet=stmt.masked, fixes=fixes)


Check = Callable[[LintContext], Iterable[Hit]]


@dataclass(frozen=True)
class Rule:
    """A lint rule.

    Attributes
    ----------
    id : str
        Family prefix + number, e.g. ``COR010``.
    name : str
        Kebab-case name, e.g. ``missing-intent``.
    severity : str
        One of `SEVERITIES`.
    summary : str
        One-line description of what is reported.
    rationale : str
        Why it matters (markdown).
    bad, good : str
        Fortran examples: code that is reported and the preferred form.
    equivalent : str
        The equivalent Fortitude rule code, '' when none.
    default : bool
        Enabled when no explicit selection is made.
    check : callable
        ``check(ctx) -> iterable of Hit``.
    """

    id: str
    name: str
    severity: str
    summary: str
    rationale: str
    bad: str
    good: str
    check: Check
    equivalent: str = ""
    default: bool = True

    @property
    def family(self) -> str:
        return re.match(r"[A-Z]+", self.id).group(0)

    def explain(self) -> str:
        """Plain-text documentation of the rule (``fobis lint --explain``)."""
        lines = [
            f"{self.id} {self.name} [{self.severity}]{'' if self.default else ' (not enabled by default)'}",
            "",
            self.summary,
            "",
            textwrap.dedent(self.rationale).strip(),
        ]
        if self.bad:
            lines += ["", "Reported:", "", textwrap.indent(textwrap.dedent(self.bad).strip(), "    ")]
        if self.good:
            lines += ["", "Preferred:", "", textwrap.indent(textwrap.dedent(self.good).strip(), "    ")]
        if self.equivalent:
            lines += ["", f"Equivalent Fortitude rule: {self.equivalent}"]
        lines += ["", f"Suppress one occurrence with:  ! fobis: ignore[{self.id}] <reason>"]
        return "\n".join(lines)


RULES: dict[str, Rule] = {}


def rule(
    id: str,
    name: str,
    summary: str,
    rationale: str,
    bad: str = "",
    good: str = "",
    severity: str = "warning",
    equivalent: str = "",
    default: bool = True,
) -> Callable[[Check], Check]:
    """Register the decorated check function as a rule."""

    def register(check: Check) -> Check:
        if id in RULES:
            raise ValueError(f"duplicate rule id {id}")
        if severity not in SEVERITIES:
            raise ValueError(f"rule {id}: unknown severity {severity!r}")
        RULES[id] = Rule(
            id=id,
            name=name,
            severity=severity,
            summary=summary,
            rationale=rationale,
            bad=bad,
            good=good,
            check=check,
            equivalent=equivalent,
            default=default,
        )
        return check

    return register


def select_rules(select: Iterable[str] = (), ignore: Iterable[str] = ()) -> list[Rule]:
    """The rules to run.

    Parameters
    ----------
    select : iterable of str
        Rule ids or prefixes (``COR``, ``COR01``, ``ALL``); empty means the rules enabled by default.
        An explicit selection enables matching rules even when they are off by default.
    ignore : iterable of str
        Rule ids or prefixes removed from the selection.

    Raises
    ------
    ValueError
        A selector matches no rule.
    """
    select = [s.strip().upper() for s in select if s.strip()]
    ignore = [s.strip().upper() for s in ignore if s.strip()]
    for selector in [*select, *ignore]:
        if selector != "ALL" and not any(rid.startswith(selector) for rid in RULES):
            raise ValueError(f"unknown rule or prefix {selector!r}")

    def matches(rid: str, selectors: list[str]) -> bool:
        return any(sel == "ALL" or rid.startswith(sel) for sel in selectors)

    chosen = [r for r in RULES.values() if (matches(r.id, select) if select else r.default)]
    return sorted((r for r in chosen if not matches(r.id, ignore)), key=lambda r: r.id)
