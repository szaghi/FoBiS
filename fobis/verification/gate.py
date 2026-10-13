"""gate.py — one verdict for a change (phase V9 of PLAN-verification.md).

The gate runs FoBiS's own checks as stages — build, review of the changed lines, tests, verification against
references, differential run against the base, benchmarks against the base, assessment budgets, the declared
matrix — each as a nested ``fobis ... --json`` command, and reduces every stage to pass / fail / error / skipped
with the FIRST failing fact (located when the stage locates it). A stage that does not apply (no tests, no cases,
no benchmark declared, nothing changed) is skipped with its reason, never failed; an advisory stage is reported
but does not fail the gate. ``[gate]`` in the fobos sets the stages, the advisory ones, the base and the matrix.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .case import CaseError

STAGES = ("build", "review", "test", "verify", "diff-run", "bench", "assess", "matrix")
NEEDS_BUILD = {"test", "verify", "diff-run", "bench", "assess", "matrix"}  # skipped when the build fails
_KEYS = {"stages", "skip", "advisory", "base", "mode", "matrix_modes", "matrix_shadows"}


class GateError(CaseError):
    """The gate is declared or asked for incorrectly."""


def _names(text: str) -> list[str]:
    return text.replace(",", " ").split()


@dataclass
class GateConfig:
    """``[gate]``: stages (in order), skipped and advisory stages, base revision, mode, matrix subset."""

    stages: list[str] = field(default_factory=lambda: list(STAGES))
    advisory: set[str] = field(default_factory=set)
    base: str = ""
    mode: str = ""
    matrix_modes: list[str] = field(default_factory=list)
    matrix_shadows: list[str] = field(default_factory=lambda: ["none", "checks"])

    def check(self) -> None:
        unknown = sorted((set(self.stages) | self.advisory) - set(STAGES))
        if unknown:
            raise GateError(f"unknown gate stage(s) {', '.join(unknown)} (stages: {', '.join(STAGES)})")


def load_config(fobos: Any) -> GateConfig:
    """The ``[gate]`` section of a parsed fobos (defaults when absent)."""
    config = GateConfig()
    parser = getattr(fobos, "fobos", None)
    if parser is None or not parser.has_section("gate"):
        return config
    items = dict(parser.items("gate"))
    unknown = sorted(set(items) - _KEYS)
    if unknown:
        raise GateError(f"[gate]: unknown key(s) {', '.join(unknown)} (known: {', '.join(sorted(_KEYS))})")
    if items.get("stages", "").strip():
        config.stages = _names(items["stages"])
    skip = set(_names(items.get("skip", "")))
    config.stages = [s for s in config.stages if s not in skip]
    config.advisory = set(_names(items.get("advisory", "")))
    config.base = items.get("base", "").strip()
    config.mode = items.get("mode", "").strip()
    config.matrix_modes = _names(items.get("matrix_modes", ""))
    if items.get("matrix_shadows", "").strip():
        config.matrix_shadows = _names(items["matrix_shadows"])
    config.check()
    return config


@dataclass
class StageResult:
    """One stage of the gate: status ``pass``, ``fail``, ``error`` (the command gave no verdict) or ``skipped``."""

    name: str
    status: str
    advisory: bool = False
    fact: str = ""  # the first failing fact, or why the stage was skipped
    commands: list[list[str]] = field(default_factory=list)
    elapsed: float = 0.0
    details: list[str] = field(default_factory=list)  # further failing facts (a few)

    @property
    def blocking(self) -> bool:
        return self.status in ("fail", "error") and not self.advisory

    def to_dict(self) -> dict:
        return {
            "stage": self.name,
            "status": self.status,
            "advisory": self.advisory,
            "fact": self.fact,
            "details": self.details,
            "commands": self.commands,
            "elapsed": round(self.elapsed, 2),
        }


# ── the first failing fact of each stage's document ────────────────────────────


def _where(path: Any, line: Any) -> str:
    return f"{path}:{line}" if path and line else (str(path) if path else "")


def _quantity_fact(case: dict) -> str:
    """The first failing quantity of a verify/diff-run case document."""
    for quantity in case.get("quantities", []):
        if quantity.get("status") in ("pass", None):
            continue
        text = f"{quantity.get('name')} {quantity.get('status')}"
        if quantity.get("out_of_tolerance"):
            text += f" ({quantity['out_of_tolerance']}/{quantity.get('count')} out of {quantity.get('tolerance')}"
            text += f", max rel {quantity.get('max_rel')})"
        worst = quantity.get("worst") or {}
        if worst:
            text += f", worst at {worst.get('index')}: {worst.get('value')} vs {worst.get('reference')}"
        if quantity.get("nonfinite"):
            text += f", non-finite {quantity['nonfinite'][0]}"
        return text
    run = case.get("run") or case.get("old_run") or {}
    if run.get("status") not in (None, "ok"):
        tail = (run.get("stderr") or "").strip().splitlines()[-1:]
        return f"run {run.get('status')}" + (f": {tail[0]}" if tail else "")
    return case.get("note", "")


def build_facts(doc: dict) -> list[str]:
    if doc.get("status") == "ok":
        return []
    found = [d.get("summary", "") for d in doc.get("diagnoses", [])]
    found += [
        f"{_where(d.get('file'), d.get('line'))}: {d.get('message', '')}".lstrip(": ")
        for d in doc.get("diagnostics", [])
    ]
    found += [e for e in doc.get("errors", []) if e.strip()]
    return [f for f in found if f] or ["the build failed"]


def review_facts(doc: dict) -> list[str]:
    return [
        f"{_where(f.get('path'), f.get('line'))}: {f.get('rule')} {f.get('message', '')}"
        for f in doc.get("findings", [])
        if f.get("severity") in ("error", "warning")
    ]


def test_facts(doc: dict) -> list[str]:
    found = []
    for result in doc.get("results", []):
        if result.get("status") == "passed":
            continue
        text = f"{result.get('name')}: {result.get('status')}"
        crash = result.get("crash") or {}
        notes = result.get("notes") or result.get("diagnoses") or []
        if notes:
            text += f": {notes[0].get('summary', '')}"
        elif crash:
            text += f": {crash.get('message', '')} {_where(crash.get('file'), crash.get('line'))}".rstrip()
        found.append(text)
    return found


def verify_facts(doc: dict) -> list[str]:
    found = []
    for case in doc.get("cases", []):
        if case.get("status") == "pass":
            continue
        if case.get("status") == "no-reference":
            found.append(f"{case.get('case')}: no reference (fobis verify {case.get('case')} --update, once right)")
            continue
        fact = _quantity_fact(case)
        found.append(f"{case.get('case')}: {case.get('status')}" + (f": {fact}" if fact else ""))
    return found


def diff_run_facts(doc: dict) -> list[str]:
    found = []
    for case in doc.get("cases", []):
        if case.get("status") in ("equivalent", "within-uncertainty"):
            continue
        fact = _quantity_fact(case)
        found.append(f"{case.get('case')}: {case.get('status')}" + (f": {fact}" if fact else ""))
    if found and doc.get("changed"):
        changed = doc["changed"][0]
        procedures = ", ".join(changed.get("procedures", [])[:3])
        found.append(f"changed: {changed.get('path')}" + (f" ({procedures})" if procedures else ""))
    return found


def bench_facts(doc: dict) -> list[str]:
    found = []
    for case in doc.get("cases", []):
        if case.get("status") != "ok":
            found.append(f"{case.get('case')}: {case.get('error') or case.get('status')}")
            continue
        comparison = case.get("comparison") or {}
        if comparison.get("verdict") == "slower":
            low, high = comparison.get("interval") or (None, None)
            text = f"{case.get('case')}: slower than {comparison.get('against')}, speedup {comparison['speedup']:.3f}"
            if low is not None:
                text += f" [{low:.3f}, {high:.3f}]"
            regressions = [f for f in case.get("feedback", []) if f.get("regression")]
            if regressions:
                first = regressions[0]
                where = f" at {first['lines'][0]}" if first.get("lines") else ""
                text += f"; {first['procedure']}: {first['category']} {first['old']} -> {first['new']}{where}"
            found.append(text)
    return found


def assess_facts(doc: dict) -> list[str]:
    if doc.get("status") == "error":
        return [f"{doc.get('case')}: {doc.get('error', 'the base run failed')}"]
    return [
        f"{doc.get('case')}: budget {b.get('budget')} not met (actual {b.get('actual')})"
        for b in doc.get("budgets", [])
        if not b.get("ok")
    ]


def matrix_facts(doc: dict) -> list[str]:
    found = []
    for cell in doc.get("cells", []):
        if cell.get("status") != "fail":
            continue
        name = f"{cell.get('mode')}/{cell.get('shadow')}"
        build = cell.get("build") or {}
        if build.get("status") not in (None, "ok"):
            found.append(f"{name}: build: {build.get('problem', 'failed')}")
        for failure in (cell.get("tests") or {}).get("failures", []):
            found.append(f"{name}: test {failure.get('name')}: {failure.get('problem') or failure.get('status')}")
        for case in cell.get("cases", []):
            if case.get("status") not in ("ok", "pass"):
                found.append(f"{name}: case {case.get('case')}: {case.get('problem') or case.get('status')}")
    for item in doc.get("disagreements", []):
        found.append(
            f"{item.get('case')}.{item.get('quantity')}: {item.get('cell')} disagrees with {item.get('baseline')} "
            f"(max rel {item.get('max_rel')})"
        )
    return found


FACTS: dict[str, Callable[[dict], list[str]]] = {
    "build": build_facts,
    "review": review_facts,
    "test": test_facts,
    "verify": verify_facts,
    "diff-run": diff_run_facts,
    "bench": bench_facts,
    "assess": assess_facts,
    "matrix": matrix_facts,
}
MAX_DETAILS = 4


def parse_json(text: str) -> dict | None:
    """The JSON document of a command's stdout (from its first ``{``), None when there is none."""
    start = text.find("{")
    if start < 0:
        return None
    try:
        data = json.loads(text[start:])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


# ── running ────────────────────────────────────────────────────────────────────


@dataclass
class Plan:
    """What the gate will run: per stage its commands, or the reason it is skipped."""

    commands: dict[str, list[list[str]]] = field(default_factory=dict)
    skipped: dict[str, str] = field(default_factory=dict)


def run_gate(
    config: GateConfig,
    plan: Plan,
    run: Callable[[list[str]], tuple[int, str, str]],
    progress: Callable[[str], None] = lambda _m: None,
    fail_fast: bool = False,
    clock: Callable[[], float] = time.monotonic,
) -> list[StageResult]:
    """Run the planned stages in order; *run* executes ``fobis <args>`` and returns (exit code, stdout, stderr)."""
    results: list[StageResult] = []
    build_failed = stop = False
    for name in config.stages:
        result = StageResult(name, "skipped", advisory=name in config.advisory)
        results.append(result)
        if stop:
            result.fact = "not run: an earlier stage failed (--fail-fast)"
            continue
        if name in plan.skipped:
            result.fact = plan.skipped[name]
            continue
        if build_failed and name in NEEDS_BUILD:
            result.fact = "not run: the build failed"
            continue
        result.commands = plan.commands.get(name, [])
        start = clock()
        facts, errors = [], []
        for args in result.commands:
            progress(f"{name}: fobis {' '.join(args)}")
            code, out, err = run(args)
            doc = parse_json(out)
            if doc is None:
                tail = (err or out).strip().splitlines()[-1:] or [f"exit status {code}"]
                errors.append(f"fobis {args[0]} gave no result: {tail[0]}")
                continue
            facts += FACTS[name](doc)
        result.elapsed = clock() - start
        if errors:
            result.status, result.fact, result.details = "error", errors[0], (errors[1:] + facts)[:MAX_DETAILS]
        elif facts:
            result.status, result.fact, result.details = "fail", facts[0], facts[1 : 1 + MAX_DETAILS]
        else:
            result.status = "pass"
        if name == "build" and result.status != "pass":
            build_failed = True
        if fail_fast and result.blocking:
            stop = True
    return results


def verdict(results: list[StageResult]) -> str:
    return "fail" if any(r.blocking for r in results) else "pass"


def render_text(results: list[StageResult], total: float, base: str) -> str:
    marks = {"pass": "pass", "fail": "FAIL", "error": "ERROR", "skipped": "skip"}
    lines = [f"gate: {verdict(results).upper()}" + (f" (base {base})" if base else "") + f", {total:.1f} s"]
    for r in results:
        mark = marks[r.status] + (" (advisory)" if r.advisory and r.status in ("fail", "error") else "")
        timing = f" [{r.elapsed:.1f} s]" if r.status != "skipped" else ""
        lines.append(f"  {r.name:<9} {mark}{timing}" + (f": {r.fact}" if r.fact else ""))
        lines += [f"            {d}" for d in r.details]
    return "\n".join(lines)
