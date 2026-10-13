"""feedback_diff.py — what the compiler did differently between two revisions (``fobis bench --feedback``).

Both sides are built with the benchmark's own flags plus the compiler's report flags; the reports (gfortran
``-fopt-info``, nvfortran ``-Minfo``) are reduced to events per procedure — loop vectorised, loop not vectorised,
implicit host/device copy of a variable, sequential device loop — and the counts are compared per procedure, so
line numbers that moved do not matter. A loop that lost vectorisation, a new implicit copy or a new sequential
device loop is a regression, located at the new side's lines.
"""

from __future__ import annotations

import os
import re
from collections import Counter
from dataclasses import dataclass, field

from ..lint.feedback import _same_file, parse_log

REPORT_FLAGS = {
    "gnu": "-fopt-info-vec-optimized -fopt-info-vec-missed",
    "opencoarrays-gnu": "-fopt-info-vec-optimized -fopt-info-vec-missed",
    "nvfortran": "-Minfo=accel,mp,vect",
    "pgi": "-Minfo=accel,mp,vect",
}
VECTORIZED, NOT_VECTORIZED, IMPLICIT_COPY, SEQUENTIAL = (
    "vectorized loop",
    "loop not vectorized",
    "implicit copy",
    "sequential device loop",
)
WORSE_WHEN_FEWER = {VECTORIZED}  # a drop is a regression; for the others a rise is

_NV_IMPLICIT = re.compile(r"^Generating implicit (copy|copyin|copyout|create)\(([A-Za-z_]\w*)")


@dataclass(frozen=True)
class Event:
    procedure: str
    category: str
    detail: str
    path: str
    line: int


def classify(compiler: str, kind: str, text: str) -> tuple[str, str] | None:
    """(category, detail) of a report message, None when it is not one of the compared events."""
    if compiler == "gfortran":
        if kind == "optimized" and text.startswith("loop vectorized"):
            return VECTORIZED, ""
        if kind == "missed" and text.startswith("couldn't vectorize loop"):
            return NOT_VECTORIZED, ""
        return None
    if text.startswith("Generated vector simd code for the loop"):
        return VECTORIZED, ""
    if text.startswith("Loop not vectorized") or text.endswith("prevents vectorization"):
        return NOT_VECTORIZED, ""
    match = _NV_IMPLICIT.match(text)
    if match:  # per variable: copy(y) becoming copyin(y) + copyout(y) moves the same data
        return IMPLICIT_COPY, match.group(2).lower()
    if text.startswith(("!$acc loop seq", "Accelerator serial kernel generated")):
        return SEQUENTIAL, ""
    return None


def events(log: str, units: dict, project, root: str = "") -> list[Event]:
    """The compared events of a build log, each in its procedure (innermost unit enclosing its line; nvfortran
    names it), one per (procedure, category, detail, line); paths relative to *root* when given."""
    found: set[Event] = set()
    for message in parse_log(log):
        kind = classify(message.compiler, message.kind, message.text)
        if kind is None:
            continue
        procedure, path = message.procedure or "", message.path or ""
        if message.compiler == "gfortran":
            for display, file_units in units.items():
                if _same_file(display, path):
                    path = display
                    inner = [u for u in file_units.walk() if u.line <= message.line <= (u.end_line or u.line)]
                    procedure = min(inner, key=lambda u: u.end_line - u.line).name if inner else ""
                    break
        else:
            for unit, unit_path in project.procedures.get(procedure, []):
                if unit.line <= message.line <= (unit.end_line or message.line):
                    path = unit_path
                    break
        if root and path:
            path = os.path.relpath(os.path.abspath(path), root)
        found.add(Event(procedure, kind[0], kind[1], path, message.line))
    return sorted(found, key=lambda e: (e.procedure, e.category, e.detail, e.path, e.line))


@dataclass
class Change:
    procedure: str
    category: str
    detail: str
    old: int
    new: int
    lines: list[str] = field(default_factory=list)  # new side's locations (old side's when the events vanished)
    scope: str = "both"  # the procedure exists on both sides, or only "added" / "removed"

    @property
    def regression(self) -> bool:
        if self.scope != "both":
            return False  # a loop of a new procedure did not lose anything
        return self.new < self.old if self.category in WORSE_WHEN_FEWER else self.new > self.old

    def to_dict(self) -> dict:
        return {
            "procedure": self.procedure,
            "category": self.category,
            "detail": self.detail,
            "old": self.old,
            "new": self.new,
            "regression": self.regression,
            "scope": self.scope,
            "lines": self.lines,
        }

    def text(self) -> str:
        what = self.category + (f" {self.detail}" if self.detail else "")
        where = f" {'at' if self.new else 'was at'} {', '.join(self.lines[:4])}" if self.lines else ""
        mark = {"added": "added procedure", "removed": "removed procedure"}.get(self.scope) or (
            "REGRESSION" if self.regression else "change"
        )
        return f"{mark}: {self.procedure or '?'}: {what} {self.old} -> {self.new}{where}"


def diff(
    old: list[Event], new: list[Event], old_procedures: set[str] | None = None, new_procedures: set[str] | None = None
) -> list[Change]:
    """Per (procedure, category, detail): the count on each side, when it changed; regressions first. With the
    procedure names of each side, a change in a procedure that exists on one side only is not a regression."""

    def counts(found: list[Event]) -> Counter:
        return Counter((e.procedure, e.category, e.detail) for e in found)

    before, after = counts(old), counts(new)
    changes = []
    for key in sorted(set(before) | set(after)):
        if before[key] == after[key]:
            continue
        side = new if after[key] else old
        lines = [f"{e.path}:{e.line}" for e in side if (e.procedure, e.category, e.detail) == key]
        scope = "both"
        if old_procedures is not None and new_procedures is not None:
            if key[0] not in old_procedures:
                scope = "added"
            elif key[0] not in new_procedures:
                scope = "removed"
        changes.append(Change(*key, before[key], after[key], lines, scope))
    order = {"both": 0, "added": 1, "removed": 2}
    return sorted(changes, key=lambda c: (not c.regression, order[c.scope], c.procedure, c.category, c.detail))
