"""engine.py — run lint rules over files: suppressions, baseline, file discovery."""

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

import json
import os
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from ..analysis import SourceFile, Suppression, build_units, lex, read_source
from .rule import RULES, Finding, Hit, LintContext, Rule, rule

BASELINE_VERSION = 1
DEFAULT_EXCLUDED_DIRS = frozenset((".fobis_deps", ".git", ".svn", ".hg", "node_modules"))


@rule(
    "LNT001",
    "suppression-without-reason",
    summary="An inline suppression `! fobis: ignore[ID]` gives no reason.",
    rationale="""
        A suppression silences a finding forever; without a reason, nobody can later tell whether it is
        still justified. Write the reason after the bracket: `! fobis: ignore[COR020] state kept on purpose`.
        """,
    bad="real :: total = 0.0  ! fobis: ignore[COR020]",
    good="real :: total = 0.0  ! fobis: ignore[COR020] running total across calls is intended",
)
def _check_reason(ctx: LintContext) -> Iterator[Hit]:
    return iter(())  # computed by the engine, which owns suppressions


@rule(
    "LNT002",
    "unused-suppression",
    summary="An inline suppression silences nothing.",
    rationale="""
        The code it was written for has changed or moved: the stale comment now hides nothing, but would
        silently hide a future finding on that line. Remove it.
        """,
    bad="integer :: n  ! fobis: ignore[COR020] n is not initialised any more",
    good="integer :: n",
)
def _check_unused(ctx: LintContext) -> Iterator[Hit]:
    return iter(())  # computed by the engine


@rule(
    "LNT003",
    "unknown-rule-in-suppression",
    summary="An inline suppression names a rule that does not exist.",
    rationale="A misspelled rule id suppresses nothing, while the comment suggests otherwise.",
    bad="! fobis: ignore[COR999] typo",
    good="! fobis: ignore[COR020] reason",
)
def _check_unknown(ctx: LintContext) -> Iterator[Hit]:
    return iter(())  # computed by the engine


@rule(
    "LNT004",
    "preprocessor-assumption",
    summary="A preprocessor condition could not be evaluated and was assumed true.",
    rationale="""
        The linter evaluates `#if` conditions with the build mode's defines to analyse the code the compiler
        sees. When an expression is beyond its evaluator (function-like macros, unknown operators) the
        branch is assumed taken: findings in or around it may not match the compiled code.
        """,
    severity="info",
)
def _check_preprocessor(ctx: LintContext) -> Iterator[Hit]:
    for line, message in ctx.source.warnings:
        yield Hit(line=line, message=message, snippet=message)


_ENGINE_RULES = ("LNT001", "LNT002", "LNT003")


@dataclass
class LintResult:
    """Outcome of linting a set of files.

    Attributes
    ----------
    findings : list of Finding
        Findings left after suppressions and baseline.
    files : int
        Number of files linted.
    unreadable : list of (str, str)
        Files that could not be read (path, reason).
    baselined : int
        Findings hidden by the baseline.
    """

    findings: list[Finding] = field(default_factory=list)
    files: int = 0
    unreadable: list[tuple[str, str]] = field(default_factory=list)
    baselined: int = 0


def _statement_span(source: SourceFile, sup: Suppression) -> tuple[int, int]:
    """Lines covered by a suppression: the statement it ends (inline) or the next one (own line)."""
    for stmt in source.statements:
        if sup.own_line and stmt.line > sup.line:
            return stmt.line, stmt.end_line
        if not sup.own_line and stmt.line <= sup.line <= stmt.end_line:
            return stmt.line, stmt.end_line
    return sup.line, sup.line


def _meta(rid: str, path: str, line: int, message: str) -> Finding:
    return Finding(rule=rid, path=path, line=line, end_line=line, message=message, severity=RULES[rid].severity)


def _apply_suppressions(
    source: SourceFile, path: str, findings: list[Finding], enabled: set[str]
) -> tuple[list[Finding], list[Finding]]:
    """Drop suppressed findings; return (kept, meta-findings about the suppressions)."""
    meta: list[Finding] = []
    suppressed: set[int] = set()
    for sup in source.suppressions:
        first, last = _statement_span(source, sup)
        for rid in sup.rules:
            if rid not in RULES:
                if "LNT003" in enabled:
                    meta.append(_meta("LNT003", path, sup.line, f"unknown rule '{rid}' in suppression"))
                continue
            used = False
            for idx, finding in enumerate(findings):
                if finding.rule == rid and first <= finding.line <= last:
                    suppressed.add(idx)
                    used = True
            if not used and rid in enabled and "LNT002" in enabled:
                meta.append(_meta("LNT002", path, sup.line, f"suppression of {rid} matches no finding"))
        if not sup.reason and "LNT001" in enabled:
            meta.append(_meta("LNT001", path, sup.line, f"suppression of {', '.join(sup.rules)} gives no reason"))
    kept = [f for idx, f in enumerate(findings) if idx not in suppressed]
    return kept, meta


def lint_text(
    text: str,
    path: str,
    rules: Iterable[Rule],
    defines: dict[str, str] | None = None,
    openmp: bool = False,
    fixed_line_length: int | None = 72,
) -> list[Finding]:
    """Lint Fortran *text* reported as *path*; suppressions are applied, the baseline is not."""
    rules = list(rules)
    source = lex(text, path=path, defines=defines, openmp=openmp, fixed_line_length=fixed_line_length)
    ctx = LintContext(path=path, source=source, units=build_units(source))
    findings = []
    for rul in rules:
        if rul.id in _ENGINE_RULES:
            continue
        for hit in rul.check(ctx):
            findings.append(
                Finding(
                    rule=rul.id,
                    path=path,
                    line=hit.line,
                    end_line=hit.end_line or hit.line,
                    message=hit.message,
                    severity=rul.severity,
                    snippet=hit.snippet,
                )
            )
    findings, meta = _apply_suppressions(source, path, findings, {r.id for r in rules})
    return sorted([*findings, *meta], key=lambda f: (f.line, f.rule))


def discover_files(
    paths: Iterable[str],
    extensions: Iterable[str],
    exclude: Iterable[str] = (),
    exclude_dirs: Iterable[str] = (),
    recursive: bool = True,
) -> list[str]:
    """Source files under *paths* (files are taken as given), in sorted order.

    Directories named in `DEFAULT_EXCLUDED_DIRS` (fetched dependencies, VCS metadata) are always skipped.
    """
    extensions = set(extensions)
    excluded_names = {os.path.basename(e) for e in exclude}
    exclude_dirs = [os.path.normpath(d) for d in exclude_dirs if d]
    found: set[str] = set()

    def wanted(name: str) -> bool:
        return os.path.splitext(name)[1] in extensions and name not in excluded_names

    def dir_excluded(root: str) -> bool:
        norm = os.path.normpath(root)
        return bool(set(norm.split(os.sep)) & DEFAULT_EXCLUDED_DIRS) or any(d in norm for d in exclude_dirs)

    for path in paths:
        if os.path.isfile(path):
            found.add(os.path.normpath(path))
        elif os.path.isdir(path) and not recursive:
            found.update(os.path.normpath(os.path.join(path, n)) for n in os.listdir(path) if wanted(n))
        elif os.path.isdir(path):
            for root, dirs, files in os.walk(path):
                dirs[:] = sorted(d for d in dirs if not dir_excluded(os.path.join(root, d)))
                if not dir_excluded(root):
                    found.update(os.path.normpath(os.path.join(root, n)) for n in files if wanted(n))
    return sorted(found)


def display_path(path: str) -> str:
    """*path* relative to the working directory when below it, else unchanged."""
    rel = os.path.relpath(os.path.abspath(path))
    return path if rel.startswith("..") else rel


def lint_files(
    files: Iterable[str],
    rules: Iterable[Rule],
    defines: dict[str, str] | None = None,
    openmp: bool = False,
    fixed_line_length: int | None = 72,
) -> LintResult:
    """Lint *files*; findings carry display paths (see `display_path`)."""
    rules = list(rules)
    result = LintResult()
    for path in files:
        try:
            text = read_source(path)
        except OSError as exc:
            result.unreadable.append((path, str(exc)))
            continue
        result.files += 1
        result.findings.extend(lint_text(text, display_path(path), rules, defines, openmp, fixed_line_length))
    return result


# ── baseline ──────────────────────────────────────────────────────────────────


class BaselineError(ValueError):
    """The baseline file is unreadable or malformed."""


def load_baseline(path: str) -> Counter[str]:
    """Fingerprint counts recorded in the baseline file *path* (empty when the file does not exist).

    Raises
    ------
    BaselineError
        The file exists but is not a valid baseline.
    """
    if not os.path.exists(path):
        return Counter()
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        return Counter(entry["fingerprint"] for entry in data["findings"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise BaselineError(f"invalid lint baseline {path}: {exc}") from exc


def apply_baseline(result: LintResult, baseline: Counter[str]) -> None:
    """Remove from *result* the findings recorded in *baseline* (each record hides one occurrence)."""
    remaining = Counter(baseline)
    kept = []
    for finding in result.findings:
        if remaining[finding.fingerprint] > 0:
            remaining[finding.fingerprint] -= 1
            result.baselined += 1
        else:
            kept.append(finding)
    result.findings = kept


def write_baseline(path: str, findings: Iterable[Finding]) -> int:
    """Record *findings* as the accepted state; return how many were written."""
    entries = [
        {"rule": f.rule, "path": f.path, "fingerprint": f.fingerprint, "message": f.message}
        for f in sorted(findings, key=lambda f: (f.path, f.line, f.rule))
    ]
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"version": BASELINE_VERSION, "tool": "fobis lint", "findings": entries}, handle, indent=1)
        handle.write("\n")
    return len(entries)
