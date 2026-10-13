"""modernize.py — mechanical modernisation, kept only when the results say it changed nothing (phase V12 of
PLAN-verification.md).

The automatic fixes of the lint rules (``(/ /)`` -> ``[ ]``, ``.eq.`` -> ``==``, specific intrinsics -> generic,
``character*n`` -> ``character(len=n)``, labelled DO -> ``do ... end do``) are applied to a scratch copy of the working
tree, and that copy is checked against an untouched copy: it must build, the tests passing before must pass, and
every declared case must give equivalent quantities (the diff-run comparator, the case's tolerance). When the whole
set fails, each rule's fixes are checked alone. Only verified fixes are written to the working tree, and only with
``--apply``; without tests or cases a build is no evidence of unchanged behaviour, so applying then needs
``--unverified``.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

FIXABLE_RULES = ("MDN011", "MDN021", "OBS005", "OBS008", "OBS011")


@dataclass
class Check:
    """The verdict on one fixed copy: build, tests, cases."""

    rules: list[str]
    status: str = "pass"  # pass, fail
    build: str = ""  # ok or the first problem
    tests: str = ""  # '' (none), ok, or the tests that stopped passing
    cases: str = ""  # '' (none), equivalent, or the first case that differs
    evidence: str = "build"  # build (only a build checked), tests, cases, tests+cases

    def to_dict(self) -> dict:
        return {
            "rules": self.rules,
            "status": self.status,
            "build": self.build,
            "tests": self.tests,
            "cases": self.cases,
            "evidence": self.evidence,
        }


@dataclass
class Plan:
    """The fixes found: per rule, per file, the findings with edits; and each file's digest when analysed."""

    by_rule: dict[str, dict[str, list]] = field(default_factory=dict)  # rule -> path -> findings with fixes
    digests: dict[str, str] = field(default_factory=dict)  # path -> sha256 of the analysed text

    @property
    def rules(self) -> list[str]:
        return sorted(self.by_rule)

    def counts(self) -> dict[str, dict]:
        return {
            rule: {"fixes": sum(len(f.fixes) for fs in paths.values() for f in fs), "files": sorted(paths)}
            for rule, paths in sorted(self.by_rule.items())
        }


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def make_plan(findings: list[Any], read: Callable[[str], str]) -> Plan:
    plan = Plan()
    for finding in findings:
        if finding.fixes:
            plan.by_rule.setdefault(finding.rule, {}).setdefault(finding.path, []).append(finding)
            if finding.path not in plan.digests:
                plan.digests[finding.path] = digest(read(finding.path))
    return plan


def fixed_texts(plan: Plan, rules: list[str], read: Callable[[str], str]) -> dict[str, str]:
    """path -> the text with the fixes of *rules* applied (overlapping edits after the first skipped)."""
    from ..lint import apply_fixes

    per_path: dict[str, list] = {}
    for rule in rules:
        for path, findings in plan.by_rule.get(rule, {}).items():
            per_path.setdefault(path, []).extend(findings)
    return {path: apply_fixes(read(path), findings)[0] for path, findings in per_path.items()}


def write_texts(root: str, texts: dict[str, str]) -> None:
    """Write *texts* (paths relative to the cwd) under *root*."""
    for path, text in texts.items():
        target = os.path.join(root, os.path.relpath(os.path.abspath(path), os.getcwd()))
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(text)


def judge(check: Check, base_tests: dict[str, str] | None, fixed_tests: dict[str, str] | None, diffs: list) -> Check:
    """Fill the tests and cases verdicts of *check* (its build already set) from the runs of both copies."""
    evidence = []
    if base_tests is not None:
        evidence.append("tests")
        broken = sorted(n for n, s in base_tests.items() if s == "passed" and (fixed_tests or {}).get(n) != "passed")
        check.tests = "ok" if not broken else "stopped passing: " + ", ".join(broken)
        if broken:
            check.status = "fail"
    if diffs:
        evidence.append("cases")
        differing = [d for d in diffs if not d.ok]
        check.cases = "equivalent" if not differing else f"{differing[0].verification.case}: {differing[0].status}"
        if differing:
            check.status = "fail"
    check.evidence = "+".join(evidence) or ("build" if check.build == "ok" else "none")
    if check.evidence == "none":
        check.status = "fail"  # nothing showed the fixes harmless
    return check


def render_text(plan: Plan, checks: list[Check], applied: list[str], verified: list[str]) -> str:
    lines = ["fixes found:"]
    for rule, data in plan.counts().items():
        lines.append(f"  {rule}: {data['fixes']} edit(s) in {len(data['files'])} file(s)")
    for check in checks:
        lines.append(f"check [{', '.join(check.rules)}]: {check.status.upper()} (evidence: {check.evidence})")
        lines.append(f"    build: {check.build}")
        if check.tests:
            lines.append(f"    tests: {check.tests}")
        if check.cases:
            lines.append(f"    cases: {check.cases}")
    lines.append(f"verified: {', '.join(verified) or 'none'}")
    lines.append(f"applied: {', '.join(applied)}" if applied else "applied: nothing (use --apply)")
    return "\n".join(lines)
