"""report.py — render lint results: text, JSON, SARIF 2.1.0, GitHub annotations."""

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
import textwrap
from collections import Counter

from .. import __version__
from .engine import LintResult
from .rule import RULES, Rule

FORMATS = ("text", "json", "sarif", "github")
_SARIF_LEVEL = {"error": "error", "warning": "warning", "info": "note"}
_DOCS_URL = "https://szaghi.github.io/FoBiS/lint-rules/"  # one page per rule: docs/lint-rules/<ID>.md


def render_text(result: LintResult, notes: dict[int, list[str]] | None = None, tail: list[str] | None = None) -> str:
    """One line per finding plus a summary.

    *notes* are lines printed under the finding of that index, *tail* lines printed before the summary (the
    ``--deep`` review).
    """
    lines = []
    for index, f in enumerate(result.findings):
        lines.append(f"{f.path}:{f.line}: {f.rule} [{f.severity}] {f.message}")
        lines += (notes or {}).get(index, [])
    lines += [f"{path}: cannot read: {reason}" for path, reason in result.unreadable]
    counts = Counter(f.rule for f in result.findings)
    summary = f"{len(result.findings)} finding(s) in {result.files} file(s)"
    if result.baselined:
        summary += f", {result.baselined} hidden by the baseline"
    if result.skipped:
        summary += f", {len(result.skipped)} C header(s) skipped"
    if counts:
        summary += ": " + ", ".join(f"{rid} x{n}" for rid, n in sorted(counts.items()))
    if result.feedback_messages:
        summary += f"\nCompiler feedback: {result.feedback_messages} message(s) read"
        if result.feedback_unattributed:
            summary += f", {result.feedback_unattributed} not attributable to a linted file"
    if counts:
        summary += "\nExplain a rule with: fobis lint --explain <ID>"
    lines += tail or []
    return "\n".join([*lines, "", summary] if lines else [summary])


def render_json(result: LintResult, reviews: dict[int, dict] | None = None, review: dict | None = None) -> str:
    """Machine-readable findings; with ``--deep``, each finding's *reviews* entry and the top-level *review*."""
    reviews = reviews or {}
    data = {
        "files": result.files,
        "baselined": result.baselined,
        "unreadable": [{"path": p, "reason": r} for p, r in result.unreadable],
        "findings": [
            {
                "rule": f.rule,
                "name": RULES[f.rule].name,
                "severity": f.severity,
                "path": f.path,
                "line": f.line,
                "end_line": f.end_line,
                "message": f.message,
                "fingerprint": f.fingerprint,
                **({"review": reviews[i]} if i in reviews else {}),
            }
            for i, f in enumerate(result.findings)
        ],
    }
    if review is not None:
        data["review"] = review
    return json.dumps(data, indent=2)


def _sarif_rule(rul: Rule) -> dict:
    return {
        "id": rul.id,
        "name": rul.name,
        "shortDescription": {"text": rul.summary},
        "fullDescription": {"text": " ".join(textwrap.dedent(rul.rationale).split())},
        "help": {"text": rul.explain()},
        "helpUri": f"{_DOCS_URL}{rul.id}",
        "defaultConfiguration": {"level": _SARIF_LEVEL[rul.severity]},
    }


def render_sarif(result: LintResult) -> str:
    """SARIF 2.1.0 log (GitHub code scanning, IDEs)."""
    used = sorted({f.rule for f in result.findings})
    index = {rid: i for i, rid in enumerate(used)}
    results = [
        {
            "ruleId": f.rule,
            "ruleIndex": index[f.rule],
            "level": _SARIF_LEVEL[f.severity],
            "message": {"text": f.message},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": f.path.replace("\\", "/")},
                        "region": {"startLine": f.line, "endLine": max(f.end_line, f.line)},
                    }
                }
            ],
            "partialFingerprints": {"fobisLint/v1": f.fingerprint},
        }
        for f in result.findings
    ]
    log = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "fobis lint",
                        "version": __version__,
                        "informationUri": "https://github.com/szaghi/FoBiS",
                        "rules": [_sarif_rule(RULES[rid]) for rid in used],
                    }
                },
                "results": results,
            }
        ],
    }
    return json.dumps(log, indent=2)


def render_github(result: LintResult) -> str:
    """GitHub Actions workflow commands: one annotation per finding."""
    level = {"error": "error", "warning": "warning", "info": "notice"}

    def escape(text: str) -> str:
        return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")

    return "\n".join(
        f"::{level[f.severity]} file={f.path},line={f.line},endLine={max(f.end_line, f.line)},"
        f"title={f.rule} {RULES[f.rule].name}::{escape(f.message)}"
        for f in result.findings
    )


def render(result: LintResult, fmt: str) -> str:
    """Render *result* in format *fmt* (one of `FORMATS`)."""
    return {"text": render_text, "json": render_json, "sarif": render_sarif, "github": render_github}[fmt](result)


def render_rule_list() -> str:
    """Table of every rule: id, name, severity, default, Fortitude equivalent."""
    lines = []
    for rul in sorted(RULES.values(), key=lambda r: r.id):
        flags = "default" if rul.default else "opt-in"
        equivalent = f"  (fortitude {rul.equivalent})" if rul.equivalent else ""
        lines.append(f"{rul.id}  {rul.name:<40} {rul.severity:<8} {flags:<8}{equivalent}")
    return "\n".join(lines)
