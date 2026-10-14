"""assess.py — numerical error and uncertainty assessment of a case (``fobis assess``).

An **ensemble** of variants of a case, the spread of each quantity across it, and what that spread says about the
quantity's accuracy. Families of variants, declared in the fobos (``[assess:CASE]``) or chosen on the command line:

- ``precision``: the program rebuilt with its reals promoted (default per compiler, or declared flag sets such as a
  project kind switch ``-DRKIND=16``): the digits of the base run that agree with the most precise run.
- ``rounding``: compiler-level perturbations of the arithmetic (optimisation level, FMA contraction, value-unsafe
  math, vectorisation): the significant digits the members share.
- ``compiler``: the same case built by other fobos modes (other compilers or versions, each with its
  ``[verification] setup``): the digits shared, and which compiler is the outlier.
- ``parallel``: thread and rank counts, each run ``repeats`` times: digits shared across counts, and repeated runs
  that differ (non-determinism: reductions, races).
- ``inputs``: declared input parameters perturbed, one at a time (``rel EPS``: elasticities) or sampled (``uniform``,
  ``normal``: Monte Carlo, seeded): output mean, standard deviation, correlation with each input.
- ``refinement``: a control parameter on a ladder of values (resolution, step, tolerance): observed order,
  Richardson extrapolation, error estimate, GCI, convergence type, asymptotic range.

Budgets (``budget = q: digits >= 12; err: order >= 1.8``) turn the assessment into a check. Every member is a run
of the case through `LocalRunner`: built once per distinct build (flags, mode), its inputs edited in its own run
directory, never in the project.
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

import os
import random
import re
import shlex
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from itertools import pairwise
from typing import Any

from . import stats
from .case import Case, CaseError
from .probes import Quantity, json_number
from .runner import BuildVariant, RunResult
from .shadow import family as compiler_family
from .verify import index_text

FAMILIES = ("precision", "rounding", "compiler", "parallel", "inputs", "refinement")
DEFAULT_FAMILIES = ("rounding",)
# the section of the numerics knowledge pack describing each family's method, assumptions and references
METHODS = {family: f"numerics:assessment#{family}-family" for family in FAMILIES}
DEFAULT_SAMPLES = 16
DEFAULT_REPEATS = 2

# measured on gfortran 16, ifx 2025.3, nvfortran 26.1 (docs/advanced/assess.md)
PRECISION_DEFAULTS = {
    "gnu": {"promoted": "-freal-4-real-8 -freal-8-real-16"},  # explicit real64 promoted too
    "intel": {"promoted": "-real-size 64 -double-size 128"},  # default REAL and DOUBLE PRECISION only
    "nvfortran": {"promoted": "-r8"},  # default REAL only
}
ROUNDING_DEFAULTS = {
    "gnu": {
        "O0": "-O0",
        "O3": "-O3",
        "fma": "-O2 -mfma -ffp-contract=fast",
        "no-fma": "-ffp-contract=off",
        "fast-math": "-O3 -ffast-math",
        "no-vectorize": "-O3 -fno-tree-vectorize",
    },
    "intel": {
        "O0": "-O0",
        "O3": "-O3",
        "precise": "-fp-model precise",
        "fast": "-fp-model fast=2",
        "no-fma": "-no-fma",
    },
    "nvfortran": {"O0": "-O0", "O2": "-O2", "fast": "-fast", "ieee": "-Kieee", "no-fma": "-Mnofma"},
}

_KEYS = {
    "families",
    "precision",
    "rounding",
    "modes",
    "threads",
    "ranks",
    "repeats",
    "inputs",
    "refine",
    "samples",
    "seed",
    "budget",
    "description",
}
_TARGETS = {"namelist": 2, "keyvalue": 2, "regex": 2, "arg": 1, "env": 1}
_BUDGET = re.compile(r"^(?P<q>[\w*.-]+)\s*:\s*(?P<metric>digits|order|error)\s*(?P<op>>=|<=|>|<)\s*(?P<value>\S+)$")


class AssessError(CaseError):
    """A bad ``[assess:CASE]`` declaration or an impossible assessment."""


# ── the declaration ────────────────────────────────────────────────────────────


@dataclass
class Parameter:
    """An input of the case: where it is (``namelist FILE VAR``, ``keyvalue FILE KEY``, ``regex FILE PATTERN``,
    ``arg N``, ``env VAR``) and how it varies (``rel EPS``, ``uniform A B``, ``normal MU SIGMA``, or for refinement
    ``values V1 V2 ... [inverse|direct]``)."""

    name: str
    kind: str
    where: list[str]
    spec: str = ""
    numbers: list[float] = field(default_factory=list)
    raw_values: list[str] = field(default_factory=list)  # refinement: as written (integers stay integers)
    inverse: bool = False  # refinement: h = 1/value (a resolution) instead of h = value (a step)


@dataclass
class Budget:
    quantity: str
    metric: str
    op: str
    value: float

    def text(self) -> str:
        return f"{self.quantity}: {self.metric} {self.op} {self.value:g}"

    def holds(self, actual: float) -> bool:
        return {
            ">=": actual >= self.value,
            "<=": actual <= self.value,
            ">": actual > self.value,
            "<": actual < self.value,
        }[self.op]


@dataclass
class AssessSpec:
    case: str
    families: list[str] = field(default_factory=lambda: list(DEFAULT_FAMILIES))
    precision: dict[str, str] = field(default_factory=dict)
    rounding: dict[str, str] = field(default_factory=dict)
    modes: list[str] = field(default_factory=list)
    threads: list[int] = field(default_factory=list)
    ranks: list[int] = field(default_factory=list)
    repeats: int = DEFAULT_REPEATS
    inputs: list[Parameter] = field(default_factory=list)
    refine: Parameter | None = None
    samples: int = DEFAULT_SAMPLES
    seed: int = 0
    budgets: list[Budget] = field(default_factory=list)


def _variants(text: str, key: str) -> dict[str, str]:
    """``NAME: flags`` lines (a line of flags alone is named after them)."""
    found = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        name, sep, flags = line.partition(":")
        if not sep or " " in name.strip() or name.strip().startswith("-"):
            name, flags = re.sub(r"[^A-Za-z0-9_.=-]+", "_", line), line
        if not flags.strip():
            raise AssessError(f"{key}: variant {name.strip()!r} has no flags")
        found[name.strip()] = flags.strip()
    return found


def parse_parameter(line: str, refinement: bool = False) -> Parameter:
    """``NAME: TARGET ... VARIATION`` (see `Parameter`)."""
    name, sep, rest = line.partition(":")
    words = shlex.split(rest)
    if not sep or not name.strip() or not words or words[0] not in _TARGETS:
        raise AssessError(f"{line.strip()!r} is not 'NAME: namelist|keyvalue|regex|arg|env ... VARIATION'")
    kind = words[0]
    count = _TARGETS[kind]
    where, spec = words[1 : 1 + count], words[1 + count :]
    if len(where) != count or not spec:
        raise AssessError(f"{name.strip()}: {kind} takes {count} argument(s) and then the variation")
    param = Parameter(name.strip(), kind, where, spec[0])
    if kind == "arg" and not where[0].isdigit():
        raise AssessError(f"{param.name}: arg takes the argument's position (1, 2, ...)")
    if kind == "regex":
        try:
            groups = re.compile(where[1]).groups
        except re.error as exc:
            raise AssessError(f"{param.name}: bad regex: {exc}") from exc
        if groups < 1:
            raise AssessError(f"{param.name}: the regex needs a group around the value")
    numbers = spec[1:]
    if refinement:
        if spec[0] != "values":
            raise AssessError(f"refine {param.name}: 'values V1 V2 V3 ...' (at least 3, coarse to fine)")
        if numbers and numbers[-1] in ("inverse", "direct"):
            param.inverse = numbers.pop() == "inverse"
        param.raw_values = numbers
    try:
        param.numbers = [float(n) for n in numbers]
    except ValueError as exc:
        raise AssessError(f"{param.name}: {' '.join(numbers)} are not numbers") from exc
    if refinement:
        if len(param.numbers) < 3:
            raise AssessError(f"refine {param.name}: at least 3 values")
        h = [1 / v if param.inverse and v else v for v in param.numbers]
        if any(v <= 0 for v in param.numbers) or any(a <= b for a, b in pairwise(h)):
            raise AssessError(
                f"refine {param.name}: values from coarse to fine (h = {'1/value' if param.inverse else 'value'} "
                "must decrease; add 'inverse' for a resolution such as a number of points)"
            )
        return param
    expected = {"rel": 1, "uniform": 2, "normal": 2}
    if spec[0] not in expected or len(param.numbers) != expected[spec[0]]:
        raise AssessError(f"{param.name}: the variation is 'rel EPS', 'uniform A B' or 'normal MU SIGMA'")
    return param


def parse_spec(name: str, items: dict[str, str] | None) -> AssessSpec:
    """The ``[assess:NAME]`` section (None: the defaults)."""
    spec = AssessSpec(name)
    items = items or {}
    unknown = sorted(set(items) - _KEYS)
    if unknown:
        raise AssessError(f"[assess:{name}]: unknown key(s) {', '.join(unknown)} (known: {', '.join(sorted(_KEYS))})")
    if items.get("families"):
        spec.families = items["families"].replace(",", " ").split()
    bad = [f for f in spec.families if f not in FAMILIES]
    if bad:
        raise AssessError(f"[assess:{name}]: unknown family {', '.join(bad)} (known: {', '.join(FAMILIES)})")
    spec.precision = _variants(items.get("precision", ""), "precision")
    spec.rounding = _variants(items.get("rounding", ""), "rounding")
    spec.modes = items.get("modes", "").split()
    try:
        spec.threads = [int(v) for v in items.get("threads", "").split()]
        spec.ranks = [int(v) for v in items.get("ranks", "").split()]
        spec.repeats = int(items.get("repeats", DEFAULT_REPEATS))
        spec.samples = int(items.get("samples", DEFAULT_SAMPLES))
        spec.seed = int(items.get("seed", 0))
    except ValueError as exc:
        raise AssessError(f"[assess:{name}]: {exc}") from exc
    try:
        spec.inputs = [parse_parameter(line) for line in items.get("inputs", "").splitlines() if line.strip()]
        if items.get("refine", "").strip():
            spec.refine = parse_parameter(items["refine"].strip(), refinement=True)
    except AssessError as exc:
        raise AssessError(f"[assess:{name}]: {exc}") from exc
    for part in re.split(r"[;\n]", items.get("budget", "")):
        if not part.strip():
            continue
        match = _BUDGET.match(part.strip())
        if not match:
            raise AssessError(f"budget {part.strip()!r} is not 'quantity: digits|order|error >=|<=|>|< value'")
        try:
            value = float(match["value"])
        except ValueError as exc:
            raise AssessError(f"budget {part.strip()!r}: {match['value']} is not a number") from exc
        spec.budgets.append(Budget(match["q"], match["metric"], match["op"], value))
    return spec


def load_spec(fobos: Any, name: str) -> AssessSpec:
    """The ``[assess:NAME]`` of a parsed fobos (``$variables`` substituted), or the defaults."""
    parser = getattr(fobos, "fobos", None)
    section = f"assess:{name}"
    if parser is None or not parser.has_section(section):
        return parse_spec(name, None)
    variables = getattr(fobos, "local_variables", {}) or {}
    items = {}
    for key, value in parser.items(section):
        for var, val in sorted(variables.items(), key=lambda kv: -len(kv[0])):
            value = re.sub(re.escape(var) + r"(?![A-Za-z0-9_])", lambda _m, v=val: v, value)
        items[key] = value
    return parse_spec(name, items)


# ── editing a member's inputs ──────────────────────────────────────────────────


def _format(value: float) -> str:
    """A value as written into an input: 15 significant digits (``3.003``, not ``3.0029999999999997``)."""
    return format(float(value), ".15g")


def _pattern(param: Parameter) -> re.Pattern:
    if param.kind == "namelist":
        return re.compile(rf"(?im)\b{re.escape(param.where[1])}\s*=\s*([^,/\n!]+?)\s*(?=[,/\n!]|$)")
    if param.kind == "keyvalue":
        return re.compile(rf"(?m)^\s*{re.escape(param.where[1])}\s*[=:]\s*(\S+)")
    return re.compile(param.where[1], re.MULTILINE)


def current_value(param: Parameter, case: Case, root: str) -> float:
    """The value the case uses now (the base of a ``rel`` variation)."""
    if param.kind == "arg":
        index = int(param.where[0]) - 1
        if index >= len(case.args):
            raise AssessError(f"input {param.name}: the case has {len(case.args)} argument(s)")
        text = case.args[index]
    elif param.kind == "env":
        if param.where[0] not in case.env:
            raise AssessError(f"input {param.name}: the case sets no env {param.where[0]}")
        text = case.env[param.where[0]]
    else:
        covered = any(
            os.path.normpath(param.where[0]) == os.path.normpath(i)
            or os.path.normpath(param.where[0]).startswith(os.path.normpath(i) + os.sep)
            for i in case.inputs
        )
        if not covered:
            raise AssessError(f"input {param.name}: {param.where[0]} is not among the case's inputs")
        try:
            with open(os.path.join(root, param.where[0]), encoding="utf-8") as handle:
                match = _pattern(param).search(handle.read())
        except OSError as exc:
            raise AssessError(f"input {param.name}: {exc}") from exc
        if match is None:
            raise AssessError(f"input {param.name}: no value found in {param.where[0]}")
        text = match.group(1)
    try:
        return float(text.strip().replace("d", "e").replace("D", "e"))
    except ValueError as exc:
        raise AssessError(f"input {param.name}: {text!r} is not a number") from exc


def with_values(case: Case, values: list[tuple[Parameter, str]]) -> tuple[Case, Callable[[str], None]]:
    """The case with arguments/environment set, and the function editing the files of its run directory."""
    args, env = list(case.args), dict(case.env)
    files: list[tuple[Parameter, str]] = []
    for param, text in values:
        if param.kind == "arg":
            index = int(param.where[0]) - 1
            if index >= len(args):
                raise AssessError(f"{param.name}: the case has {len(args)} argument(s)")
            args[index] = text
        elif param.kind == "env":
            env[param.where[0]] = text
        else:
            files.append((param, text))

    def prepare(rundir: str) -> None:
        for param, text in files:
            path = os.path.join(rundir, param.where[0])
            with open(path, encoding="utf-8") as handle:
                content = handle.read()
            match = _pattern(param).search(content)
            if match is None:
                raise ValueError(f"input {param.name}: no value found in {param.where[0]}")
            content = content[: match.start(1)] + text + content[match.end(1) :]
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(content)

    return replace(case, args=args, env=env), prepare


# ── members ────────────────────────────────────────────────────────────────────


@dataclass
class Member:
    """One run of the ensemble."""

    label: str
    family: str
    build: BuildVariant | None = None
    mode: str | None = None
    case: Case | None = None
    prepare: Callable[[str], None] | None = None
    params: dict[str, float] = field(default_factory=dict)
    group: str = ""  # parallel: the configuration (its repeats share it); inputs one at a time: the parameter
    result: RunResult | None = None

    @property
    def build_key(self) -> tuple:
        return (self.mode, self.build)


def members_for(
    spec: AssessSpec, case: Case, family: str, compiler: str, root: str, samples: int, cpus: int
) -> tuple[list[Member], list[str]]:
    """The members a family adds to the base run, and notes on how they were chosen."""
    notes: list[str] = []
    fam = compiler_family(compiler) or ""
    found: list[Member] = []
    if family in ("precision", "rounding"):
        declared = spec.precision if family == "precision" else spec.rounding
        defaults = (PRECISION_DEFAULTS if family == "precision" else ROUNDING_DEFAULTS).get(fam, {})
        variants = declared or defaults
        if not variants:
            raise AssessError(f"{family}: no default variants for compiler {compiler!r}: declare '{family} = ...'")
        if family == "precision" and not declared:
            notes.append(f"default promotion for {compiler}: {defaults['promoted']}")
        if family == "rounding":
            notes.append("compiler-level perturbations (Verificarlo's Monte Carlo arithmetic is not used)")
        found = [Member(f"{family}-{n}", family, BuildVariant(f"{family}-{n}", flags)) for n, flags in variants.items()]
    elif family == "compiler":
        if not spec.modes:
            raise AssessError("compiler: declare the other modes to build the case with ('modes = gnu nvf ...')")
        found = [Member(f"compiler-{m}", family, mode=m) for m in spec.modes]
    elif family == "parallel":
        threads = spec.threads or [t for t in (1, 2, 4) if t <= cpus]
        ranks = spec.ranks or [case.ranks]
        if not spec.threads:
            notes.append(f"threads {' '.join(map(str, threads))} (declare 'threads = ...' to choose)")
        for t in threads:
            for r in ranks:
                group = f"threads={t}" + (f",ranks={r}" if r else "")
                for k in range(1, max(1, spec.repeats) + 1):
                    found.append(
                        Member(f"parallel-t{t}-r{r}-{k}", family, case=replace(case, threads=t, ranks=r), group=group)
                    )
    elif family == "inputs":
        if not spec.inputs:
            raise AssessError("inputs: declare the parameters to vary ('inputs = NAME: namelist FILE VAR rel 1e-3')")
        base = {p.name: current_value(p, case, root) for p in spec.inputs}
        if any(p.spec != "rel" for p in spec.inputs):
            rng = random.Random(spec.seed)
            for k in range(1, samples + 1):
                values = {}
                for p in spec.inputs:
                    if p.spec == "rel":
                        low, high = sorted((base[p.name] * (1 - p.numbers[0]), base[p.name] * (1 + p.numbers[0])))
                        values[p.name] = rng.uniform(low, high)
                    elif p.spec == "uniform":
                        values[p.name] = rng.uniform(*p.numbers)
                    else:
                        values[p.name] = rng.gauss(*p.numbers)
                values = {n: float(_format(v)) for n, v in values.items()}  # what the program reads
                edited, prepare = with_values(case, [(p, _format(values[p.name])) for p in spec.inputs])
                found.append(Member(f"inputs-sample-{k}", family, case=edited, prepare=prepare, params=values))
            notes.append(f"Monte Carlo: {samples} samples, seed {spec.seed}")
        else:
            for p in spec.inputs:
                for sign, tag in ((-1, "low"), (1, "high")):
                    value = float(_format(base[p.name] * (1 + sign * p.numbers[0])))
                    edited, prepare = with_values(case, [(p, _format(value))])
                    params = dict(base) | {p.name: value}
                    found.append(
                        Member(
                            f"inputs-{p.name}-{tag}", family, case=edited, prepare=prepare, params=params, group=p.name
                        )
                    )
            notes.append(
                "one at a time: "
                + ", ".join(f"{p.name} = {base[p.name]:g} +/- {p.numbers[0]:g} (relative)" for p in spec.inputs)
            )
    elif family == "refinement":
        p = spec.refine
        if p is None:
            raise AssessError("refinement: declare the control parameter ('refine = n: arg 1 values 10 20 40 inverse')")
        current_value(p, case, root)  # the target must hold a number now: a wrong position fails here, not later
        integer = all(re.fullmatch(r"[+-]?\d+", v) for v in p.raw_values)
        for raw, value in zip(p.raw_values, p.numbers, strict=True):
            edited, prepare = with_values(case, [(p, raw if integer else _format(value))])
            h = 1 / value if p.inverse else value
            params = {"h": h, p.name: value}
            found.append(Member(f"refine-{p.name}={raw}", family, case=edited, prepare=prepare, params=params))
        notes.append(f"{p.name} = {' '.join(p.raw_values)}, h = {'1/' if p.inverse else ''}{p.name}")
    return found, notes


# ── analysis ───────────────────────────────────────────────────────────────────


def _quantities(result: RunResult) -> dict[str, Quantity]:
    return {q.name: q for q in result.quantities}


def _number(value: float | None) -> Any:
    return None if value is None else json_number(value)


OUTLIER_ULPS = 8  # an ensemble's outlier is named only beyond this many double-precision ulps from the median


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= 1e-12 * max(abs(a), abs(b))


def ensemble(members: list[tuple[str, Quantity]]) -> dict:
    """Digits shared by the members of an ensemble, its spread and its outlier, for one quantity."""
    first = members[0][1]
    size = len(first.values)
    if any(len(q.values) != size for _, q in members):
        return {"note": "the members have different sizes"}
    per_point, lower = [], []
    for i in range(size):
        digits, low = stats.significant_digits([q.values[i] for _, q in members])
        per_point.append(digits)
        lower.append(low)
    points = stats.over_points(per_point)
    data: dict[str, Any] = {
        "members": len(members),
        "digits": _number(points.minimum),
        "digits_low": _number(min(lower)),
    }
    if size > 1:
        data["digits_median"] = _number(points.median)
        data["worst"] = index_text(points.worst, first.shape, first.order)
    column = [q.values[points.worst] for _, q in members]
    mu, sigma = stats.mean_std(column)
    data.update({"mean": _number(mu), "std": _number(sigma), "min": _number(min(column)), "max": _number(max(column))})
    if sigma > 0:
        median = sorted(column)[len(column) // 2]
        label, value = max(((label, q.values[points.worst]) for label, q in members), key=lambda m: abs(m[1] - median))
        if abs(value - median) > OUTLIER_ULPS * sys.float_info.epsilon * abs(median):  # not a last-bit difference
            data["outlier"] = {"member": label, "value": _number(value), "median": _number(median)}
    return data


@dataclass
class FamilyResult:
    family: str
    members: list[str] = field(default_factory=list)
    failed: list[dict] = field(default_factory=list)
    quantities: dict[str, dict] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def method(self) -> str:
        return METHODS.get(self.family, "")

    def to_dict(self) -> dict:
        data = {"family": self.family, "method": self.method, "members": self.members, "quantities": self.quantities}
        if self.failed:
            data["failed"] = self.failed
        if self.notes:
            data["notes"] = self.notes
        return data


def analyse(family: str, base: Member, members: list[Member], spec: AssessSpec) -> FamilyResult:
    """What the members of *family* say about each quantity of the base run."""
    result = FamilyResult(family, [m.label for m in members])
    ok = [m for m in members if m.result is not None and m.result.ok]
    for m in members:
        if m in ok:
            continue
        detail = ""
        if m.result is not None and m.result.build:
            build = m.result.build
            diagnostics = [d.get("message", "") for d in build.get("diagnostics", [])[:1]]
            detail = "; ".join(build.get("errors", [])[:1] or diagnostics) or "build failed"
            detail = next((line.strip() for line in detail.splitlines() if "rror" in line), detail.splitlines()[0])
        elif m.result is not None:
            detail = (m.result.stderr.strip().splitlines() or [""])[-1]
        result.failed.append(
            {"member": m.label, "status": m.result.status if m.result else "not run", "detail": detail}
        )
    for name, quantity in _quantities(base.result).items():
        found = [(m.label, _quantities(m.result).get(name)) for m in ok]
        found = [(label, q) for label, q in found if q is not None]
        if family == "precision":
            result.quantities[name] = _precision(quantity, found)
        elif family in ("rounding", "compiler"):
            result.quantities[name] = ensemble([("base", quantity), *found]) if found else {}
        elif family == "parallel":
            result.quantities[name] = _parallel(name, ok)
        elif family == "inputs":
            result.quantities[name] = _inputs(name, quantity, ok, spec)
        else:
            result.quantities[name] = _refinement(name, ok)
    return result


def _precision(base: Quantity, found: list[tuple[str, Quantity]]) -> dict:
    if not found:
        return {}
    label, best = found[-1]  # the last declared variant is the most precise
    if len(best.values) != len(base.values):
        return {"note": "the promoted run has a different size"}
    per_point = [stats.digits_against(v, r) for v, r in zip(base.values, best.values, strict=True)]
    points = stats.over_points(per_point)
    data = {
        "against": label,
        "digits": _number(points.minimum),
        "base": _number(base.values[points.worst]),
        "reference": _number(best.values[points.worst]),
    }
    if len(per_point) > 1:
        data["digits_median"] = _number(points.median)
        data["worst"] = index_text(points.worst, base.shape, base.order)
    return data


def _relative_difference(values: list[float], reference: list[float]) -> float:
    return max((abs(a - b) / abs(b) if b else abs(a - b)) for a, b in zip(values, reference, strict=False))


def _parallel(name: str, ok: list[Member]) -> dict:
    groups: dict[str, list[Quantity]] = {}
    for m in ok:
        q = _quantities(m.result).get(name)
        if q is not None:
            groups.setdefault(m.group, []).append(q)
    data: dict[str, Any] = {}
    nondeterministic = []
    for group, runs in groups.items():
        differing = [_relative_difference(r.values, runs[0].values) for r in runs[1:] if r.values != runs[0].values]
        if differing:
            nondeterministic.append({"configuration": group, "runs": len(runs), "max_rel": _number(max(differing))})
    if nondeterministic:
        data["nondeterministic"] = nondeterministic
    firsts = [(group, runs[0]) for group, runs in groups.items()]
    if len(firsts) > 1:
        data.update(ensemble(firsts))
        data["bitwise_identical"] = all(q.values == firsts[0][1].values for _, q in firsts)
    return data


def _inputs(name: str, base: Quantity, ok: list[Member], spec: AssessSpec) -> dict:
    if len(base.values) != 1:
        return {"note": "inputs are assessed on scalar quantities"}
    rows = [(m.params, _quantities(m.result).get(name), m.group) for m in ok]
    rows = [(p, q.values[0], g) for p, q, g in rows if q is not None and len(q.values) == 1]
    if not rows:
        return {}
    outputs = [v for _, v, _ in rows]
    data: dict[str, Any] = {}
    if any(p.spec != "rel" for p in spec.inputs):
        mu, sigma = stats.mean_std(outputs)
        digits, low = stats.significant_digits(outputs)
        data.update({"mean": _number(mu), "std": _number(sigma), "digits": _number(digits), "digits_low": _number(low)})
        measure = {}
        for p in spec.inputs:
            value = stats.correlation([params[p.name] for params, _, _ in rows], outputs)
            measure[p.name] = None if value is None else round(value, 4)
        data["correlation"] = measure
    else:
        q0 = base.values[0]
        measure = {}
        for p in spec.inputs:
            mine = sorted((params[p.name], v) for params, v, group in rows if group == p.name)
            if len(mine) == 2:
                (p_low, q_low), (p_high, q_high) = mine
                value = stats.elasticity((p_low + p_high) / 2, q0, p_low, q_low, p_high, q_high)
                measure[p.name] = None if value is None else round(value, 6)
        data["elasticity"] = measure
    data["ranking"] = sorted((n for n, v in measure.items() if v is not None), key=lambda n: -abs(measure[n]))
    return data


def _refinement(name: str, ok: list[Member]) -> dict:
    levels = [(m.params["h"], _quantities(m.result).get(name)) for m in ok if "h" in m.params]
    levels = sorted(((h, q) for h, q in levels if q is not None), key=lambda hq: -hq[0])
    if any(len(q.values) != 1 for _, q in levels):
        return {"note": "refinement is assessed on scalar quantities (arrays change size with the resolution)"}
    if len(levels) < 3:
        return {"note": f"{len(levels)} level(s) ran: at least 3 are needed"}
    h = [lvl for lvl, _ in levels]
    f = [q.values[0] for _, q in levels]
    if all(_close(v, x) for v, x in zip(f, h, strict=True)) or all(_close(v, 1 / x) for v, x in zip(f, h, strict=True)):
        return {"note": "the refined parameter itself (its values are the ladder's): not assessed"}
    found = stats.orders(h, f)
    last = found[-1]
    data = {
        "levels": [{"h": _number(a), "value": _number(b)} for a, b in zip(h, f, strict=True)],
        "orders": [_number(o.order) for o in found],
        "order": _number(last.order),
        "convergence": last.convergence,
        "extrapolated": _number(last.extrapolated),
        "error": _number(last.error),
        "gci": _number(last.gci),
    }
    asymptotic = stats.asymptotic(found)
    if asymptotic is not None:
        data["asymptotic"] = asymptotic
    return data


# ── the assessment ─────────────────────────────────────────────────────────────


@dataclass
class BudgetCheck:
    budget: Budget
    actual: float | None
    ok: bool
    note: str = ""

    def to_dict(self) -> dict:
        data = {"budget": self.budget.text(), "actual": _number(self.actual), "ok": self.ok}
        if self.note:
            data["note"] = self.note
        return data


@dataclass
class Assessment:
    case: str
    mode: str
    families: list[FamilyResult] = field(default_factory=list)
    budgets: list[BudgetCheck] = field(default_factory=list)
    builds: int = 0
    runs: int = 0
    error: str = ""
    base: RunResult | None = None

    @property
    def ok(self) -> bool:
        return not self.error and all(b.ok for b in self.budgets)

    def to_dict(self) -> dict:
        data = {
            "case": self.case,
            "mode": self.mode,
            "status": "ok" if self.ok else ("error" if self.error else "fail"),
            "builds": self.builds,
            "runs": self.runs,
            "families": [f.to_dict() for f in self.families],
            "budgets": [b.to_dict() for b in self.budgets],
        }
        if self.error:
            data["error"] = self.error
        if self.base is not None:
            data["base"] = {q.name: q.to_dict() for q in self.base.quantities}
            data["provenance"] = self.base.provenance
        return data


def _as_float(value: Any) -> float:
    return float(value)  # "inf" and "nan" (JSON-safe strings) included


def check_budgets(assessment: Assessment, budgets: list[Budget]) -> list[BudgetCheck]:
    """Each budget against the families that assessed its quantity: digits, the fewest of any family; order and
    error, the finest triple of the refinement."""
    checks = []
    ran = {f.family for f in assessment.families}
    for budget in budgets:
        capable = ran - {"refinement"} if budget.metric == "digits" else ran & {"refinement"}
        if not capable:
            checks.append(BudgetCheck(budget, None, True, "skipped: no family that measures it ran"))
            continue
        values = []
        for family in assessment.families:
            data = family.quantities.get(budget.quantity) or {}
            if budget.metric == "digits" and data.get("digits") is not None:
                values.append(_as_float(data["digits"]))
            elif budget.metric != "digits" and family.family == "refinement" and data.get(budget.metric) is not None:
                values.append(_as_float(data[budget.metric]))
        if not values:
            checks.append(BudgetCheck(budget, None, False, "not assessed by the families that ran"))
            continue
        actual = min(values)
        checks.append(BudgetCheck(budget, actual, budget.holds(actual)))
    return checks


def assess(
    spec: AssessSpec,
    case: Case,
    families: list[str],
    runner_for: Callable[[BuildVariant | None, str | None], Any],
    root: str = ".",
    mode: str | None = None,
    samples: int | None = None,
    jobs: int = 1,
    progress: Callable[[str], None] = lambda _line: None,
    cpus: int | None = None,
) -> Assessment:
    """Run the ensembles of *families* for *case* and analyse them.

    *runner_for(build, mode)* gives the `LocalRunner` of a build variant of a mode (the mode decides the
    environment: its ``[verification] setup``). Members are built once per distinct (mode, build variant); the
    base run is shared by every family.
    """
    mode = mode or case.mode
    base_runner = runner_for(None, mode)
    facts = base_runner.introspect(mode) if case.target else {}
    compiler = facts.get("compiler", {}).get("name", "gnu") or "gnu"
    assessment = Assessment(case.name, facts.get("buildoptions", {}).get("mode") or mode or "")
    base = Member("base", "base", mode=mode, case=case)
    by_family: dict[str, list[Member]] = {}
    notes: dict[str, list[str]] = {}
    for family in families:
        found, family_notes = members_for(
            spec, case, family, compiler, root, samples or spec.samples, cpus or os.cpu_count() or 1
        )
        for m in found:
            m.mode = m.mode or mode
            m.case = m.case or case
        by_family[family], notes[family] = found, family_notes
    everyone = [base] + [m for found in by_family.values() for m in found]
    builds: dict[tuple, tuple[Any, str | None, dict, dict]] = {}
    for m in everyone:
        if m.build_key in builds:
            continue
        runner = runner_for(m.build, m.mode)
        binary, report = None, {}
        if case.target:
            progress(f"build {m.build.name if m.build else 'base'}" + (f" (mode {m.mode})" if m.mode != mode else ""))
            binary, report = runner.build(case, m.mode)
        builds[m.build_key] = (runner, binary, report, runner.provenance(case, m.mode))
    assessment.builds = len(builds) if case.target else 0
    assessment.runs = len(everyone)

    def run(m: Member) -> None:
        runner, binary, report, provenance = builds[m.build_key]
        if case.target and binary is None:
            m.result = RunResult(case.name, m.label, "build-failed", build=report, provenance=provenance)
            return
        m.result = runner.run(
            m.case, variant=f"assess-{m.label}", mode=m.mode, binary=binary, prepare=m.prepare, provenance=provenance
        )

    progress(f"run {len(everyone)} member(s)" + (f", {jobs} at a time" if jobs > 1 else ""))
    run(base)
    assessment.base = base.result
    if not base.result.ok:
        problem = base.result.status
        if base.result.build:
            problem += ": " + "; ".join(base.result.build.get("errors", [])[:1])
        elif base.result.probe_errors:
            problem += ": " + ", ".join(base.result.probe_errors)
        assessment.error = f"the base run of {case.name} is not ok ({problem})"
        return assessment
    rest = everyone[1:]
    if jobs > 1:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            list(pool.map(run, rest))
    else:
        for m in rest:
            run(m)
    for family in families:
        result = analyse(family, base, by_family[family], spec)
        result.notes = notes[family] + result.notes
        assessment.families.append(result)
    assessment.budgets = check_budgets(assessment, spec.budgets)
    return assessment


# ── report ─────────────────────────────────────────────────────────────────────


def _value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, str):
        return value
    return f"{value:.10g}"


def _digits(value: Any) -> str:
    return "all equal" if value == "inf" else f"{float(value):.1f}"


def render_text(assessment: Assessment) -> str:
    lines = [
        f"assess {assessment.case} (mode {assessment.mode}): {assessment.builds} build(s), {assessment.runs} run(s)"
    ]
    if assessment.error:
        return "\n".join([*lines, f"  ERROR: {assessment.error}"])
    for family in assessment.families:
        lines.append(f"{family.family} ({len(family.members)} member(s); method: fobis kb show {family.method})")
        lines += [f"  note: {note}" for note in family.notes]
        for failure in family.failed:
            detail = f" ({failure['detail']})" if failure["detail"] else ""
            lines.append(f"  member {failure['member']}: {failure['status']}{detail}")
        for name, data in family.quantities.items():
            described = _describe(family.family, data)
            lines += [f"  {name}: {described[0]}", *(f"    {text.strip()}" for text in described[1:])]
    if assessment.budgets:
        lines.append("budgets")
        for check in assessment.budgets:
            if check.actual is None:
                actual = "-"
            elif check.budget.metric == "digits":
                actual = _digits(json_number(check.actual))
            else:
                actual = f"{check.actual:.4g}"
            verdict = "skipped" if check.note.startswith("skipped") else ("ok" if check.ok else "FAILED")
            note = f" ({check.note})" if check.note and verdict != "skipped" else ""
            lines.append(f"  {check.budget.text()}: {actual} {verdict}{note}")
    return "\n".join(lines)


def _describe(family: str, data: dict) -> list[str]:
    if not data:
        return ["no member produced it"]
    if "note" in data and len(data) == 1:
        return [data["note"]]
    if family == "precision":
        where = f" (fewest at {data['worst']}, median {_digits(data['digits_median'])})" if "worst" in data else ""
        agree = "every digit agrees" if data["digits"] == "inf" else f"{_digits(data['digits'])} digit(s) agree"
        return [f"{agree} with {data['against']}{where}: {_value(data['base'])} vs {_value(data['reference'])}"]
    if family == "inputs":
        if "elasticity" in data:
            parts = ", ".join(f"{n} {e:.3g}" if e is not None else f"{n} -" for n, e in data["elasticity"].items())
            return [f"elasticity (relative change of the output per relative change of the input): {parts}"]
        parts = ", ".join(f"{n} {c:+.2f}" if c is not None else f"{n} -" for n, c in data["correlation"].items())
        return [
            f"mean {_value(data['mean'])}, std {_value(data['std'])} ({_digits(data['digits'])} digit(s)); "
            f"correlation with {parts}"
        ]
    if family == "refinement":
        orders = ", ".join("-" if o is None else f"{o:.3f}" for o in data["orders"])
        order = "-" if data["order"] is None else f"{data['order']:.3f}"
        text = f"observed order {order} (triples: {orders}), {data['convergence']}"
        if "asymptotic" in data:
            text += ", asymptotic" if data["asymptotic"] else ", NOT in the asymptotic range"
        lines = [text]
        if data.get("extrapolated") is not None:
            gci = f", GCI {data['gci']:.3g}" if data.get("gci") is not None else ""
            lines.append(f"  extrapolated {_value(data['extrapolated'])}, error estimate {data['error']:.3g}{gci}")
        return lines
    lines = []
    if "digits" in data:
        if data["digits"] == "inf":
            text = "every member gives the same value"
        else:
            text = f"{_digits(data['digits'])} significant digit(s) (>= {_digits(data['digits_low'])} at 95%)"
        if "worst" in data:
            text += f", fewest at {data['worst']} (median {_digits(data['digits_median'])})"
        text += f"; range {_value(data['min'])} .. {_value(data['max'])}"
        if data.get("outlier"):
            text += f"; outlier {data['outlier']['member']}"
        if family == "parallel" and data.get("bitwise_identical"):
            text += "; bitwise identical"
        lines.append(text)
    for item in data.get("nondeterministic", []):
        lines.append(
            f"NON-DETERMINISTIC at {item['configuration']}: {item['runs']} repeated runs differ "
            f"(max rel {item['max_rel']:.3g})"
        )
    if family == "parallel" and not data.get("nondeterministic"):
        lines.append("repeated runs identical")
    return lines
