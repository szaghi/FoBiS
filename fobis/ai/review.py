"""review.py — ``fobis review``: lint findings on the changed lines only, and an optional cited risk summary.

The change is the staged one (``--staged``, the pre-commit hook), the commits since the merge base with a
reference (``--base origin/master``, a pull request in CI), or by default every uncommitted change. The whole
project is linted (cross-file rules need it) and only the findings whose lines intersect the added or modified
lines are reported (a changed OpenMP/OpenACC directive counts its whole region as changed): a review stays
quiet on legacy code without a baseline.

``--deep`` adds a risk summary written by the model from facts (`risk_bundle`): the changed code, the parallel
regions touched, the changed procedure headers with the files that use their modules, the findings; answered
as cited ``risk`` / ``check`` claims (`fobis.ai.grounding`).
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
from collections import Counter
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

from ..analysis.regions import regions
from ..llm.provider import messages
from .change import WORKTREE, FileChange, Git, Revision, _git, file_change, staged_changes
from .deep import _rule_text
from .grounding import ANSWER_TOKENS, ContextBundle, Grounded, Source, check_claims, claims_schema, load_prompt

if TYPE_CHECKING:
    from ..lint.engine import LintResult
    from ..lint.rule import Finding
    from ..llm.provider import Provider

KINDS = ["risk", "check"]
GROUPS = {"risk": "Risks", "check": "To check"}


class ReviewError(Exception):
    """The change to review cannot be determined (not a git repository, unknown base)."""


def review_revision(base: str | None = None, staged: bool = False, git: Git = _git) -> Revision:
    """The `Revision` to review: the index, ``merge-base(base, HEAD)..HEAD``, or HEAD against the worktree."""
    root = git("rev-parse", "--show-toplevel").strip()
    if not root:
        raise ReviewError("not inside a git repository")
    if staged:
        return Revision(("--cached",), "HEAD", "", root)
    if base:
        merge_base = git("merge-base", base, "HEAD").strip()
        if not merge_base:
            raise ReviewError(f"no merge base between {base!r} and HEAD (is {base!r} a known reference?)")
        return Revision((merge_base, "HEAD"), merge_base, "HEAD", root)
    return Revision(("HEAD",), "HEAD", WORKTREE, root)


@dataclass
class DiffScope:
    """The change under review: every changed file, Fortran sources with their added or modified lines."""

    revision: Revision
    changes: list[FileChange] = field(default_factory=list)
    diffs: dict[str, str] = field(default_factory=dict)  # git path -> unified diff (Fortran sources)

    def lines(self) -> dict[str, set[int]]:
        """Absolute path to the added or modified lines, for the Fortran files that still exist."""
        root = self.revision.root
        return {
            os.path.normpath(os.path.join(root, c.path)): c.added for c in self.changes if c.added and c.status != "D"
        }

    @property
    def changed_lines(self) -> int:
        return sum(len(added) for added in self.lines().values())


def diff_scope(revision: Revision, git: Git = _git) -> DiffScope:
    """The changed files and lines of *revision*."""
    changes = [file_change(status, path, old, git, revision) for status, path, old in staged_changes(git, revision)]
    diffs = {
        c.path: git("diff", "--no-color", *revision.diff, "-U2", "-M", "--", f":(top){c.path}")
        for c in changes
        if c.lines
    }
    return DiffScope(revision, changes, diffs)


def effective_lines(scope: DiffScope, result: LintResult) -> dict[str, set[int]]:
    """The changed lines, plus every line of an OpenMP/OpenACC region whose directive changed.

    Changing a directive changes the meaning of the whole region it governs: removing ``private(flux)`` makes
    the assignment to ``flux`` ten lines below a race, although that line did not change.
    """
    lines = {path: set(added) for path, added in scope.lines().items()}
    by_path = {os.path.abspath(p): units for p, units in result.units.items()}
    for path, added in lines.items():
        units = by_path.get(path)
        if units is None:
            continue
        widened = set()
        for unit in units.walk():
            for region in regions(unit.statements):
                stmt = region.directive.statement
                if any(stmt.line <= n <= stmt.end_line for n in added):
                    end = max([stmt.end_line, *(s.end_line for s in region.statements)])
                    widened.update(range(stmt.line, end + 1))
        added |= widened
    return lines


def in_scope(
    findings: list[Finding], scope: DiffScope, context: int = 0, lines: dict[str, set[int]] | None = None
) -> list[int]:
    """Indices of the *findings* whose lines (widened by *context*) touch a changed line.

    *lines* replaces the changed lines of *scope* (see `effective_lines`).
    """
    lines = scope.lines() if lines is None else lines
    kept = []
    for index, finding in enumerate(findings):
        added = lines.get(os.path.abspath(finding.path))
        if added and any(
            n in added for n in range(finding.line - context, max(finding.end_line, finding.line) + context + 1)
        ):
            kept.append(index)
    return kept


def scoped_result(result: LintResult, keep: list[int]) -> LintResult:
    """A copy of *result* with only the findings at *keep* (the analysed units are shared)."""
    return replace(result, findings=[result.findings[i] for i in keep], baselined=0)


# ── markdown (pull-request comment) ────────────────────────────────────────────


def render_markdown(result: LintResult, scope: DiffScope, title: str = "fobis review") -> str:
    """Findings on the changed lines as markdown, for a pull-request comment."""
    from ..lint.rule import RULES

    files = len(scope.lines())
    lines = [f"### {title}", ""]
    if not result.findings:
        lines.append(f"No finding on the changed lines ({scope.changed_lines} line(s) in {files} Fortran file(s)).")
        return "\n".join(lines)
    counts = Counter(f.severity for f in result.findings)
    summary = ", ".join(f"{n} {sev}" for sev, n in sorted(counts.items()))
    lines += [
        f"{len(result.findings)} finding(s) on the changed lines ({summary}), "
        f"{scope.changed_lines} changed line(s) in {files} Fortran file(s).",
        "",
        "| Severity | Rule | Location | Message |",
        "|---|---|---|---|",
    ]
    for f in result.findings:
        message = f.message.replace("|", "\\|")
        lines.append(f"| {f.severity} | `{f.rule}` {RULES[f.rule].name} | `{f.path}:{f.line}` | {message} |")
    lines += ["", "<details><summary>Rules</summary>", ""]
    lines += [f"- `{r}` {RULES[r].name}: {RULES[r].summary}" for r in sorted({f.rule for f in result.findings})]
    lines += ["", "Explain a rule with `fobis lint --explain <ID>`.", "", "</details>"]
    return "\n".join(lines)


# ── risk summary ───────────────────────────────────────────────────────────────


def _windows(added: set[int], total: int, radius: int = 3, max_lines: int = 120) -> list[tuple[int, int]]:
    """Merged windows of lines around the *added* lines, at most *max_lines* lines in all."""
    spans: list[list[int]] = []
    for n in sorted(added):
        first, last = max(1, n - radius), min(total, n + radius)
        if spans and first <= spans[-1][1] + 1:
            spans[-1][1] = max(spans[-1][1], last)
        else:
            spans.append([first, last])
    out, used = [], 0
    for first, last in spans:
        if used + last - first + 1 > max_lines:
            break
        out.append((first, last))
        used += last - first + 1
    return out


def _numbered(lines: list[str], first: int, last: int, marked: set[int]) -> str:
    width = len(str(last))
    return "\n".join(f"{n:<{width}} {'>' if n in marked else '|'} {lines[n - 1]}" for n in range(first, last + 1))


def risk_bundle(
    result: LintResult, scope: DiffScope, findings: list[Finding], max_files: int = 6, max_diff: int = 3000
) -> ContextBundle:
    """What the model gets to summarise the risks of the change: the diff (what was removed matters as much as
    what was added), the changed code in context, the touched regions, the dependents of changed headers, the
    findings' rules."""
    from ..lint.engine import display_path
    from ..lint.rule import RULES

    changed = []
    for c in scope.changes:
        line = f"{c.status} {c.path}"
        if c.procedures:
            line += f" (procedures changed: {', '.join(c.procedures[:6])})"
        if c.interfaces:
            line += f" (headers changed: {', '.join(c.interfaces)})"
        changed.append(line)
    listed = "\n".join(f"{f.rule} [{f.severity}] {f.path}:{f.line}: {f.message}" for f in findings) or "none"
    sections = [("Changed files", "\n".join(changed) or "none"), ("Findings on the changed lines", listed)]
    sources: list[Source] = []
    for path, diff in list(scope.diffs.items())[:max_files]:
        body = diff.split("@@", 1)
        text = "@@" + body[1] if len(body) > 1 else diff
        if len(text) > max_diff:
            text = text[: text.rfind("\n", 0, max_diff)] + "\n[...]"
        sources.append(Source(f"diff:{path}", f"diff of {path} (- removed, + added)", text))
    by_path = {os.path.abspath(p): units for p, units in result.units.items()}
    for path, added in list(scope.lines().items())[:max_files]:
        units = by_path.get(path)
        if units is None:
            continue
        shown = display_path(path)
        lines = units.source.lines
        for first, last in _windows(added, len(lines)):
            sources.append(
                Source(
                    f"code:{shown}:{first}-{last}",
                    f"{shown} lines {first}-{last} (changed lines marked >)",
                    _numbered(lines, first, last, added),
                )
            )
        for unit in units.walk():
            for region in regions(unit.statements):
                start = region.directive.statement.line
                end = max([start, *(s.end_line for s in region.statements)])
                if any(start <= n <= end for n in added):
                    directive = region.directive
                    sources.append(
                        Source(
                            f"region:{shown}:{start}-{end}",
                            f"!${directive.sentinel} {directive.construct} region, {shown} lines {start}-{end}",
                            _numbered(lines, start, min(end, start + 60), added),
                        )
                    )
    headers: dict[str, list[str]] = {}
    for change in scope.changes:
        for name in change.interfaces:
            if "::" in name:
                headers.setdefault(name.split("::")[0], []).append(name)
    for module, procedures in headers.items():
        users = sorted(
            path
            for path, units in result.units.items()
            if module in {u.module for unit in units.walk() for u in unit.uses}
        )
        text = (
            f"changed headers: {', '.join(dict.fromkeys(procedures))}\nused by: {', '.join(users) or 'no linted file'}"
        )
        sources.append(Source(f"fact:dependents#{module}", f"files using module {module}", text))
    for rule_id in sorted({f.rule for f in findings}):
        sources.append(Source(f"rule:{rule_id}", f"rule {rule_id} {RULES[rule_id].name}", _rule_text(rule_id)[:1200]))
    return ContextBundle(sections=sections, sources=sources)


def risk_summary(bundle: ContextBundle, provider: Provider, seed: int = 0) -> Grounded:
    """Ask *provider* for the cited risks of the change and what to check."""
    completion = provider.chat(
        messages(bundle.render(), system=load_prompt("review")),
        schema=claims_schema(bundle.labels, kinds=KINDS),
        temperature=0.0,
        seed=seed,
        max_tokens=ANSWER_TOKENS,
    )
    return check_claims(completion.text, bundle)
