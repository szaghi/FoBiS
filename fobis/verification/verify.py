"""verify.py — ``fobis verify``: compare a case's quantities with stored references.

A **reference** is the JSON record of a run accepted by the user (``fobis verify --update``): the quantities and the
provenance of the run that produced them, in ``<references_dir>/<case>.json`` (default
``verification/references``, meant to be versioned with the project). FoBiS never writes a reference implicitly.

A **tolerance** per quantity (fobos ``tolerance = rho: abs 1e-10 rel 1e-8; iters: exact; *: ulp 4``) decides what
counts as equal. Without one the comparison is exact: the report always gives the errors observed, so a tolerance
is set knowing what it allows. For each quantity: the largest absolute and relative errors and where (index in the
quantity's own order: Fortran ``(i,j)`` 1-based for Fortran arrays, ``[i][j]`` 0-based for row-major ones), the
L2 and L-infinity norms of the difference, how many points are out of tolerance, NaN or infinities that appeared.
What changed in the provenance since the reference (compiler, flags, dependencies, code) is reported with the
result: next to a failure it explains it, next to a pass it says the result is robust to that change.

``--repeat N`` runs the case N times and compares the runs with each other, exactly: a difference is
non-determinism (reduction order, uninitialised memory, races), whatever the reference says.
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

import datetime
import json
import math
import os
from dataclasses import dataclass, field

from .probes import Quantity, json_number
from .provenance import differences
from .runner import RunResult

REFERENCE_VERSION = 1


MAX_CHANGES = 20  # provenance changes listed in the text report (all of them in JSON)


class VerifyError(Exception):
    """A tolerance or a reference cannot be used."""


# ── tolerances ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Tolerance:
    """When two values are equal: ``|a - b| <= abs + rel * |reference|``, or within ``ulp`` units in the last place
    of the reference. ``exact`` (the default) is all zero: bitwise equality, NaN equal to NaN."""

    abs: float = 0.0
    rel: float = 0.0
    ulp: int = 0

    @property
    def exact(self) -> bool:
        return self.abs == 0.0 and self.rel == 0.0 and self.ulp == 0

    @classmethod
    def parse(cls, spec: str) -> Tolerance:
        words = spec.split()
        if words in ([], ["exact"]):
            return cls()
        values = {"abs": 0.0, "rel": 0.0, "ulp": 0}
        if len(words) % 2:
            raise VerifyError(f"'{spec.strip()}': expected 'exact' or pairs like 'abs 1e-10 rel 1e-8 ulp 4'")
        for key, value in zip(words[::2], words[1::2], strict=True):
            if key not in values:
                raise VerifyError(f"'{key}' is not abs, rel or ulp")
            try:
                number = int(value) if key == "ulp" else float(value)
            except ValueError:
                raise VerifyError(f"{key} needs a number, not '{value}'") from None
            if not number >= 0:  # negative or NaN
                raise VerifyError(f"{key} must not be negative")
            values[key] = number
        return cls(values["abs"], values["rel"], values["ulp"])

    def text(self) -> str:
        if self.exact:
            return "exact"
        parts = [f"abs {self.abs:g}" if self.abs else "", f"rel {self.rel:g}" if self.rel else ""]
        parts.append(f"ulp {self.ulp}" if self.ulp else "")
        return " ".join(p for p in parts if p)

    def equal(self, value: float, reference: float) -> bool:
        if math.isnan(value) or math.isnan(reference):
            return math.isnan(value) and math.isnan(reference)
        if math.isinf(value) or math.isinf(reference):
            return value == reference
        error = abs(value - reference)
        if error <= self.abs + self.rel * abs(reference):
            return True
        return bool(self.ulp) and error <= self.ulp * math.ulp(reference)


def tolerance_for(tolerances: dict[str, str], name: str) -> Tolerance:
    """The tolerance of quantity *name*: its own, else ``*``, else exact."""
    return Tolerance.parse(tolerances.get(name, tolerances.get("*", "exact")))


# ── comparing one quantity ─────────────────────────────────────────────────────


def index_text(flat: int, shape: list[int] | None, order: str) -> str:
    """The position of element *flat*: ``(i,j)`` 1-based in Fortran order, ``[i][j]`` 0-based in C order."""
    if not shape or len(shape) < 2:
        return f"({flat + 1})" if order == "F" and shape else f"[{flat}]"
    index = []
    rest = flat
    if order == "F":
        for extent in shape:
            index.append(rest % extent + 1)
            rest //= extent
        return "(" + ",".join(map(str, index)) + ")"
    for extent in reversed(shape):
        index.append(rest % extent)
        rest //= extent
    return "".join(f"[{i}]" for i in reversed(index))


@dataclass
class Comparison:
    """A quantity of the run compared with its reference.

    ``status``: ``pass``, ``fail``, ``missing`` (in the reference, not in the run), ``new`` (in the run, not in the
    reference: not a failure, ``--update`` records it), ``shape`` (sizes or shapes differ).
    """

    name: str
    status: str
    tolerance: Tolerance = field(default_factory=Tolerance)
    count: int = 0
    out_of_tolerance: int = 0
    max_abs: float = 0.0
    max_rel: float = 0.0
    l2: float = 0.0
    linf: float = 0.0
    worst: dict | None = None  # index, value, reference of the largest absolute error
    nonfinite: list[str] = field(default_factory=list)  # NaN/Inf that appeared or vanished, where
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.status in ("pass", "new")

    def to_dict(self) -> dict:
        data = {
            "name": self.name,
            "status": self.status,
            "tolerance": self.tolerance.text(),
            "count": self.count,
            "out_of_tolerance": self.out_of_tolerance,
            "max_abs": json_number(self.max_abs),
            "max_rel": json_number(self.max_rel),
            "l2": json_number(self.l2),
            "linf": json_number(self.linf),
        }
        if self.worst:
            data["worst"] = {k: json_number(v) if isinstance(v, float) else v for k, v in self.worst.items()}
        if self.nonfinite:
            data["nonfinite"] = self.nonfinite
        if self.note:
            data["note"] = self.note
        return data


def compare(quantity: Quantity, reference: Quantity, tolerance: Tolerance) -> Comparison:
    """Compare *quantity* with *reference* element by element."""
    result = Comparison(quantity.name, "pass", tolerance, count=len(quantity.values))
    if len(quantity.values) != len(reference.values) or (
        quantity.shape and reference.shape and quantity.shape != reference.shape
    ):
        result.status = "shape"
        mine = f"{len(quantity.values)} value(s)" + (f" shape {quantity.shape}" if quantity.shape else "")
        theirs = f"{len(reference.values)}" + (f" shape {reference.shape}" if reference.shape else "")
        result.note = f"{mine} vs {theirs} in the reference"
        return result
    squares = 0.0
    worst_abs = 0.0
    for flat, (value, ref) in enumerate(zip(quantity.values, reference.values, strict=True)):
        if not tolerance.equal(value, ref):
            result.out_of_tolerance += 1
        if not (math.isfinite(value) and math.isfinite(ref)):
            if not (math.isnan(value) and math.isnan(ref)) and value != ref:
                where = index_text(flat, quantity.shape, quantity.order)
                result.nonfinite.append(f"{where}: {json_number(value)} (reference {json_number(ref)})")
            continue
        error = abs(value - ref)
        squares += error * error
        relative = error / abs(ref) if ref else (math.inf if error else 0.0)
        result.max_rel = max(result.max_rel, relative)
        if error > worst_abs:
            worst_abs = error
            result.worst = {"index": index_text(flat, quantity.shape, quantity.order), "value": value, "reference": ref}
    result.max_abs = result.linf = worst_abs
    result.l2 = math.sqrt(squares)
    if result.out_of_tolerance or result.nonfinite:
        result.status = "fail"
    return result


# ── references ─────────────────────────────────────────────────────────────────


@dataclass
class Reference:
    """The stored record of an accepted run."""

    case: str
    quantities: dict[str, Quantity]
    provenance: dict
    created: str = ""

    def to_dict(self) -> dict:
        return {
            "version": REFERENCE_VERSION,
            "case": self.case,
            "created": self.created,
            "quantities": {name: q.to_dict() for name, q in self.quantities.items()},
            "provenance": self.provenance,
        }


def reference_path(references_dir: str, case: str) -> str:
    return os.path.join(references_dir, f"{case}.json")


def load_reference(path: str) -> Reference | None:
    """The reference at *path*, or None when there is none.

    Raises
    ------
    VerifyError
        The file is not a FoBiS reference.
    """
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        quantities = {name: Quantity.from_dict(name, q) for name, q in data["quantities"].items()}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise VerifyError(f"{path} is not a FoBiS reference: {exc}") from exc
    return Reference(data.get("case", ""), quantities, data.get("provenance", {}), data.get("created", ""))


def save_reference(path: str, result: RunResult) -> Reference:
    """Write *result* as the reference of its case (atomically)."""
    reference = Reference(
        result.case,
        {q.name: q for q in result.quantities},
        result.provenance,
        datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    )
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(reference.to_dict(), handle, indent=1)
        handle.write("\n")
    os.replace(temporary, path)
    return reference


# ── a case ─────────────────────────────────────────────────────────────────────


@dataclass
class Verification:
    """The verification of one case.

    ``status``: ``pass``, ``fail`` (a quantity out of tolerance, missing, or of another shape), ``run-failed`` (the
    run is not usable: build failure, crash, timeout), ``no-reference``, ``nondeterministic`` (``--repeat``: the
    runs differ), ``updated`` (``--update`` wrote the reference).
    """

    case: str
    status: str
    run: RunResult | None = None
    comparisons: list[Comparison] = field(default_factory=list)
    provenance_changes: list[str] = field(default_factory=list)
    reference: str = ""
    repeat: list[Comparison] = field(default_factory=list)
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.status in ("pass", "updated")

    def to_dict(self) -> dict:
        data = {
            "case": self.case,
            "status": self.status,
            "reference": self.reference,
            "quantities": [c.to_dict() for c in self.comparisons],
            "provenance_changes": self.provenance_changes,
        }
        run = self.run
        if run is not None:
            data["run"] = {
                "status": run.status,
                "exit_code": run.exit_code,
                "elapsed": round(run.elapsed, 3),
                "rundir": run.rundir,
                "probe_errors": run.probe_errors,
                "stderr": "\n".join(run.stderr.splitlines()[-20:]),
            }
            if run.build is not None:
                data["run"]["build"] = run.build
        if self.repeat:
            data["repeat"] = [c.to_dict() for c in self.repeat]
        if self.note:
            data["note"] = self.note
        return data


def compare_with_reference(result: RunResult, reference: Reference, tolerances: dict[str, str]) -> list[Comparison]:
    """Every quantity of the reference and of the run, compared."""
    found = {q.name: q for q in result.quantities}
    comparisons = []
    for name, ref in reference.quantities.items():
        tolerance = tolerance_for(tolerances, name)
        if name not in found:
            reason = result.probe_errors.get(name, "not produced by the run")
            comparisons.append(Comparison(name, "missing", tolerance, note=reason))
            continue
        comparisons.append(compare(found[name], ref, tolerance))
    for name, quantity in found.items():
        if name not in reference.quantities:
            note = "not in the reference: --update records it"
            comparisons.append(Comparison(name, "new", count=len(quantity.values), note=note))
    return comparisons


def compare_runs(first: RunResult, other: RunResult) -> list[Comparison]:
    """Two runs of the same case compared exactly (a repeat): any difference is non-determinism."""
    reference = Reference(first.case, {q.name: q for q in first.quantities}, first.provenance)
    return [c for c in compare_with_reference(other, reference, {}) if c.status != "pass"]


def verify(
    results: list[RunResult], reference: Reference | None, tolerances: dict[str, str], path: str = ""
) -> Verification:
    """The verification of a case from its run(s): the first compared with *reference*, the others (``--repeat``)
    with the first."""
    first = results[0]
    outcome = Verification(first.case, "pass", run=first, reference=path)
    if first.status not in ("ok", "probe-error"):
        outcome.status, outcome.note = "run-failed", f"the run is {first.status}"
        return outcome
    for other in results[1:]:
        if other.status not in ("ok", "probe-error"):
            outcome.status, outcome.note = "run-failed", f"a repeated run is {other.status}"
            return outcome
        seen = {r.name for r in outcome.repeat}
        outcome.repeat += [c for c in compare_runs(first, other) if c.name not in seen]
    if reference is None:
        outcome.status, outcome.note = "no-reference", "no reference: accept this run with fobis verify --update"
        return outcome
    outcome.comparisons = compare_with_reference(first, reference, tolerances)
    outcome.provenance_changes = differences(reference.provenance, first.provenance)
    if not all(c.ok for c in outcome.comparisons):
        outcome.status = "fail"
    elif outcome.repeat:
        outcome.status = "nondeterministic"
    return outcome


# ── report ─────────────────────────────────────────────────────────────────────


def _number(value: float) -> str:
    return f"{value:.6g}" if math.isfinite(value) else str(json_number(value))


def render_text(
    outcomes: list[Verification],
    reference: str = "reference",
    statuses: dict[str, str] | None = None,
    summary: str = "verified",
) -> str:
    """The human report; *reference* names the other side (``diff-run``: the revision), *statuses* renames the
    statuses (``pass`` -> ``equivalent``)."""
    lines = []
    for outcome in outcomes:
        status = (statuses or {}).get(outcome.status, outcome.status)
        lines.append(f"{outcome.case}: {status.upper()}" + (f" ({outcome.note})" if outcome.note else ""))
        for c in outcome.comparisons:
            if c.status == "pass" and c.max_abs == 0.0 and not c.out_of_tolerance:
                lines.append(f"  {c.name}: equal ({c.count} value(s), {c.tolerance.text()})")
            elif c.status in ("pass", "fail"):
                head = "within tolerance" if c.status == "pass" else f"{c.out_of_tolerance}/{c.count} out of tolerance"
                lines.append(
                    f"  {c.name}: {head} ({c.tolerance.text()}): max abs {_number(c.max_abs)}, "
                    f"max rel {_number(c.max_rel)}, L2 {_number(c.l2)}"
                )
                if c.worst and c.count == 1:
                    lines.append(f"    got {c.worst['value']!r}, {reference} {c.worst['reference']!r}")
                elif c.worst:
                    lines.append(
                        f"    worst at {c.worst['index']}: {c.worst['value']!r} vs {reference} {c.worst['reference']!r}"
                    )
                lines += [f"    non-finite: {item}" for item in c.nonfinite[:5]]
            else:
                lines.append(f"  {c.name}: {c.status}" + (f" ({c.note})" if c.note else ""))
        for c in outcome.repeat:
            detail = f"max abs {_number(c.max_abs)}" if c.status == "fail" else c.status
            lines.append(f"  {c.name}: differs between repeated runs ({detail})")
        if outcome.provenance_changes:
            since = "the reference" if reference == "reference" else reference
            lines.append(f"  changed since {since}" + (" (results unaffected):" if outcome.ok else ":"))
            lines += [f"    {change}" for change in outcome.provenance_changes[:MAX_CHANGES]]
            if len(outcome.provenance_changes) > MAX_CHANGES:
                more = len(outcome.provenance_changes) - MAX_CHANGES
                lines.append(f"    ... and {more} more (--json lists them all)")
        if outcome.status == "run-failed" and outcome.run is not None:
            run = outcome.run
            if run.build is not None:
                lines += [f"    build: {d.get('summary')}" for d in run.build.get("diagnoses", [])]
                if not run.build.get("diagnoses"):
                    lines += [f"    build: {e}" for e in run.build.get("errors", [])[:3]]
            lines += [f"    {line}" for line in run.stderr.strip().splitlines()[-8:]]
    passed = sum(o.ok for o in outcomes)
    lines.append(f"\n{passed} of {len(outcomes)} case(s) {summary}.")
    return "\n".join(lines)
