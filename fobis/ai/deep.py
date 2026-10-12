"""deep.py — ``fobis lint --deep``: a cited LLM review of the findings, region by region.

The findings of a lint run are grouped by the code they are about: the innermost OpenMP/OpenACC region that
contains them, else the enclosing procedure (a window around the findings when the procedure is long). For each
group FoBiS builds a `ContextBundle`: the code (finding lines marked ``>``), the declarations of the procedure,
the documentation of each rule and the knowledge-pack sections it references, the compiler feedback attributed
to those lines, the interfaces of the procedures the code calls, and pack sections routed by the directive's
clauses. The findings are labelled ``F1..Fn``.

The model answers, under a JSON Schema whose finding and source labels are enums, a **verdict** per finding
(``confirmed``, ``dismissed`` or ``uncertain``, with a reason and citations) and **advisory concerns** the rules
did not raise. FoBiS checks the answer: a confirmed or dismissed verdict without a valid citation becomes
``uncertain``; a concern without one is dropped; a finding the model skipped stays ``uncertain``. Nothing is
hidden: a dismissed finding is still printed (with the reason) and still counts in the exit status.

``fobis lint --ask "QUESTION" FILE:LINE`` builds the same bundle for the group around that line and answers the
question as cited claims.
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
import textwrap
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..analysis import FileUnits, Unit
from ..analysis.regions import Region, call_name, regions
from ..llm.provider import messages
from .grounding import ContextBundle, Grounded, Source, _parse, check_claims, claims_schema, load_prompt

if TYPE_CHECKING:
    from ..analysis.project import ProjectIndex
    from ..kb import KnowledgeBase
    from ..lint.engine import LintResult
    from ..lint.feedback import FeedbackMessage
    from ..lint.rule import Finding
    from ..llm.provider import Provider

VERDICTS = ["confirmed", "dismissed", "uncertain"]
# Families whose findings are syntactic facts (obsolescent forms, modernisation, portability, structure, meta):
# a model verdict adds nothing, so --deep does not spend a call on them
MECHANICAL_FAMILIES = ("OBS", "MDN", "PRT", "STY", "LNT")
_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}
_PACK_OF_SENTINEL = {"omp": "openmp", "acc": "openacc"}


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text.rfind("\n", 0, limit)
    return text[: cut if cut > 0 else limit].rstrip() + "\n[...]"


# ── groups ─────────────────────────────────────────────────────────────────────


@dataclass
class Group:
    """Findings reviewed together, with the code they are about.

    Attributes
    ----------
    path : str
        Display path of the file.
    first, last : int
        Lines of the code shown to the model.
    title : str
        What the code is (``!$omp parallel do (line 12)``, ``subroutine smooth``).
    unit : Unit or None
        The enclosing scoping unit.
    region : Region or None
        The directive region, when the group is one.
    findings : list of (int, Finding)
        Index in the lint result, and the finding.
    """

    path: str
    first: int
    last: int
    title: str
    unit: Unit | None = None
    region: Region | None = None
    findings: list[tuple[int, Finding]] = field(default_factory=list)

    @property
    def labels(self) -> list[str]:
        return [f"F{i}" for i in range(1, len(self.findings) + 1)]


def _region_lines(region: Region) -> tuple[int, int]:
    start = region.directive.statement.line
    return start, max([start, *(s.end_line for s in region.statements)])


def _innermost_unit(units: FileUnits, line: int) -> Unit | None:
    best = None
    for unit in units.walk():
        if unit.kind in ("interface", "fragment") or not unit.end_line:
            continue
        if unit.line <= line <= unit.end_line and (best is None or unit.line >= best.line):
            best = unit
    return best


def _innermost_region(unit: Unit, line: int) -> Region | None:
    best, best_span = None, None
    for region in regions(unit.statements):
        start, end = _region_lines(region)
        if start <= line <= end and (best_span is None or end - start < best_span):
            best, best_span = region, end - start
    return best


def locate(units: FileUnits, path: str, line: int, window: int = 15, max_lines: int = 120) -> Group:
    """The code around *line*: its innermost directive region, else its procedure (a window when it is long)."""
    unit = _innermost_unit(units, line)
    if unit is None:
        return Group(path, max(1, line - window), line + window, f"lines around {line}")
    region = _innermost_region(unit, line)
    if region is not None:
        first, last = _region_lines(region)
        title = f"!${region.directive.sentinel} {region.directive.construct} (line {first})"
        return Group(path, first, last, title, unit, region)
    title = f"{unit.kind} {unit.name}".strip()
    if unit.end_line - unit.line <= max_lines:
        return Group(path, unit.line, unit.end_line, title, unit)
    return Group(path, max(unit.line, line - window), min(unit.end_line, line + window), title, unit)


def group_findings(result: LintResult, skip: Iterable[str] = MECHANICAL_FAMILIES) -> list[Group]:
    """The findings of *result* grouped by region or procedure (findings of the *skip* families left out).

    Directive regions come first, then by severity, path and line: ``--deep-max`` spends the model calls on the
    parallel code first.
    """
    skip = tuple(skip)
    groups: list[Group] = []
    for index, finding in enumerate(result.findings):
        units = result.units.get(finding.path)
        if units is None or finding.rule.startswith(skip):
            continue
        probe = locate(units, finding.path, finding.line)
        for group in groups:
            same = (group.path, group.first, group.last) == (probe.path, probe.first, probe.last)
            # two windows of one long procedure that overlap become one
            overlap = (
                group.region is None
                and probe.region is None
                and group.unit is not None
                and group.unit is probe.unit
                and group.first <= probe.last
                and probe.first <= group.last
            )
            if same or overlap:
                group.first, group.last = min(group.first, probe.first), max(group.last, probe.last)
                group.findings.append((index, finding))
                break
        else:
            probe.findings.append((index, finding))
            groups.append(probe)
    return sorted(
        groups,
        key=lambda g: (
            g.region is None,
            min(_SEVERITY_ORDER.get(f.severity, 3) for _, f in g.findings),
            g.path,
            g.first,
        ),
    )


# ── bundle ─────────────────────────────────────────────────────────────────────


def _code(units: FileUnits, first: int, last: int, marked: set[int]) -> str:
    lines = units.source.lines
    last = min(last, len(lines))
    width = len(str(last))
    return "\n".join(
        f"{n:<{width}} {'>' if n in marked else '|'} {lines[n - 1]}" for n in range(max(1, first), last + 1)
    )


def _specification(unit: Unit, lines: list[str]) -> str:
    """Header, ``use`` statements and declarations of *unit*, as written."""
    numbers = sorted({u.line for u in unit.uses} | {d.line for d in unit.decls.values() if d.line})
    out = [unit.header.text.strip()] if unit.header is not None else []
    out += [lines[n - 1].strip() for n in numbers if 0 < n <= len(lines)]
    return "\n".join(out)


def _rule_text(rule_id: str) -> str:
    from ..lint.rule import RULES

    rul = RULES[rule_id]
    parts = [f"{rul.id} {rul.name} [{rul.severity}]: {rul.summary}", textwrap.dedent(rul.rationale).strip()]
    if rul.bad:
        parts.append("Reported:\n" + textwrap.dedent(rul.bad).strip())
    if rul.good:
        parts.append("Preferred:\n" + textwrap.dedent(rul.good).strip())
    return "\n\n".join(parts)


def _pack_source(kb: KnowledgeBase, chunk_id: str, max_chars: int) -> Source | None:
    try:
        chunk = kb.get(chunk_id)
    except KeyError:
        return None
    where = kb.packs[chunk.pack].meta.get("title", chunk.pack)
    return Source(chunk.id, f"{chunk.heading} - {where}", _clip(chunk.text, max_chars))


def build_bundle(
    group: Group,
    files: dict[str, FileUnits],
    project: ProjectIndex | None = None,
    kb: KnowledgeBase | None = None,
    feedback: Iterable[FeedbackMessage] = (),
    question: str | None = None,
    max_chars: int = 1500,
    min_score: float = 10.0,
) -> ContextBundle:
    """What the model gets to review *group* (or, with *question*, to answer it about that code).

    *files* maps display paths to analysed files (the group's file and the files of called procedures).
    """
    from ..lint.rule import RULES

    units = files[group.path]
    marked = {f.line for _, f in group.findings}
    findings = "\n".join(
        f"{label} {f.rule} {RULES[f.rule].name} [{f.severity}] line {f.line}: {f.message}"
        for label, (_, f) in zip(group.labels, group.findings, strict=True)
    )
    sections = [("Question", question)] if question else []
    sections.append(("Code under review", f"{group.title} in {group.path}, lines {group.first}-{group.last}"))
    sections.append(("Findings of the rules", findings or "none"))
    sources = [
        Source(
            f"code:{group.path}:{group.first}-{group.last}",
            f"{group.path} lines {group.first}-{group.last} ({group.title})",
            _code(units, group.first, group.last, marked),
        )
    ]
    if group.unit is not None and group.unit.name:
        sources.append(
            Source(
                f"fact:{group.path}#{group.unit.name}",
                f"declarations of {group.unit.kind} {group.unit.name} ({group.path}:{group.unit.line})",
                _specification(group.unit, units.source.lines),
            )
        )
    rule_ids = list(dict.fromkeys(f.rule for _, f in group.findings))
    for rule_id in rule_ids:
        sources.append(
            Source(f"rule:{rule_id}", f"rule {rule_id} {RULES[rule_id].name}", _clip(_rule_text(rule_id), max_chars))
        )
    if kb is not None:
        refs = dict.fromkeys(ref for rule_id in rule_ids for ref in RULES[rule_id].refs)
        sources += [s for ref in list(refs)[:3] if (s := _pack_source(kb, ref, max_chars)) is not None]
    local = [m for m in feedback if group.first <= m.line <= group.last]
    if local:
        text = "\n".join(f"line {m.line}: {m.text}" for m in local[:30])
        sources.append(Source(f"feedback:{group.path}", f"compiler feedback for {group.path}", text))
    if group.region is not None:
        statements = group.region.statements
    else:
        statements = [s for s in (group.unit.statements if group.unit else []) if group.first <= s.line <= group.last]
    if project is not None:
        for name in list(dict.fromkeys(n for s in statements if (n := call_name(s))))[:3]:
            proc = project.procedure(name)
            path = next((p for u, p in project.procedures.get(name, []) if u is proc), None)
            if proc is None or path not in files:
                continue
            sources.append(
                Source(
                    f"fact:{path}#{name}",
                    f"interface of {proc.kind} {name} ({path}:{proc.line})",
                    _specification(proc, files[path].source.lines),
                )
            )
    if kb is not None:
        region = group.region
        directive = region.directive.statement.text if region is not None else ""
        query = " ".join([directive, *(RULES[r].name.replace("-", " ") for r in rule_ids), question or ""])
        sentinel = region.directive.sentinel if region is not None else ""
        packs = [p for p in (_PACK_OF_SENTINEL.get(sentinel or ""), "fortran-std", "hpc-practice") if p in kb.packs]
        known = {s.id for s in sources}
        for result in kb.search(query, k=2, packs=packs):
            if result.score >= min_score and result.chunk.id not in known:
                sources.append(_pack_source(kb, result.chunk.id, max_chars))
    return ContextBundle(sections=sections, sources=sources)


# ── review ─────────────────────────────────────────────────────────────────────


def review_schema(finding_labels: list[str], source_labels: list[str]) -> dict:
    """JSON Schema of a review: a verdict per finding and advisory concerns; the labels are enums."""
    citation = {"type": "string", "enum": source_labels} if source_labels else {"type": "string"}
    finding = {"type": "string", "enum": finding_labels} if finding_labels else {"type": "string"}

    def array(properties: dict) -> dict:
        return {
            "type": "array",
            "items": {
                "type": "object",
                "properties": properties,
                "required": list(properties),
                "additionalProperties": False,
            },
        }

    return {
        "type": "object",
        "properties": {
            "verdicts": array(
                {
                    "finding": finding,
                    "verdict": {"type": "string", "enum": VERDICTS},
                    "reason": {"type": "string"},
                    "citations": {"type": "array", "items": citation},
                }
            ),
            "concerns": array(
                {
                    "line": {"type": "integer"},
                    "text": {"type": "string"},
                    "citations": {"type": "array", "items": citation},
                }
            ),
        },
        "required": ["verdicts", "concerns"],
        "additionalProperties": False,
    }


@dataclass(frozen=True)
class Verdict:
    """The model's verdict on one finding; ``uncited`` marks a verdict downgraded to uncertain."""

    verdict: str
    reason: str
    sources: tuple[Source, ...] = ()
    uncited: bool = False


@dataclass(frozen=True)
class Concern:
    """An advisory concern of the model: not a rule finding."""

    path: str
    line: int | None
    text: str
    sources: tuple[Source, ...]


@dataclass
class Review:
    """The checked review of one group."""

    verdicts: dict[int, Verdict] = field(default_factory=dict)
    concerns: list[Concern] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    raw: str = ""


def _cited(item: dict, by_label: dict[str, Source]) -> tuple[Source, ...]:
    labels = [str(c).strip().strip("[]").upper() for c in item.get("citations") or []]
    return tuple(dict.fromkeys(by_label[c] for c in labels if c in by_label))


def check_review(raw: str, group: Group, bundle: ContextBundle) -> Review:
    """The verdicts and concerns of *raw* that the bundle supports; every finding of *group* gets a verdict."""
    by_label = dict(zip(bundle.labels, bundle.sources, strict=True))
    by_finding = {label: index for label, (index, _) in zip(group.labels, group.findings, strict=True)}
    result = Review(raw=raw)
    data = _parse(raw) or {}
    for item in data.get("verdicts") or []:
        if not isinstance(item, dict):
            continue
        index = by_finding.get(str(item.get("finding", "")).strip().strip("[]").upper())
        verdict = str(item.get("verdict", "")).strip().lower()
        if index is None or index in result.verdicts or verdict not in VERDICTS:
            continue
        reason = str(item.get("reason", "")).strip()
        sources = _cited(item, by_label)
        if sources or verdict == "uncertain":
            result.verdicts[index] = Verdict(verdict, reason, sources)
        else:
            result.verdicts[index] = Verdict("uncertain", reason, (), uncited=True)
    for index, _ in group.findings:
        result.verdicts.setdefault(index, Verdict("uncertain", "not reviewed by the model"))
    for item in data.get("concerns") or []:
        if not isinstance(item, dict) or not str(item.get("text", "")).strip():
            continue
        text = str(item["text"]).strip()
        sources = _cited(item, by_label)
        if not sources:
            result.dropped.append(text)
            continue
        line = item.get("line")
        line = line if isinstance(line, int) and group.first <= line <= group.last else None
        result.concerns.append(Concern(group.path, line, text, sources))
    return result


def review(group: Group, bundle: ContextBundle, provider: Provider, seed: int = 0) -> Review:
    """Ask *provider* to review *group* with *bundle*; the checked answer."""
    completion = provider.chat(
        messages(bundle.render(), system=load_prompt("deep")),
        schema=review_schema(group.labels, bundle.labels),
        temperature=0.0,
        seed=seed,
    )
    return check_review(completion.text, group, bundle)


def ask_region(bundle: ContextBundle, provider: Provider, seed: int = 0) -> Grounded:
    """Answer the question of *bundle* (``fobis lint --ask``) as cited claims."""
    completion = provider.chat(
        messages(bundle.render(), system=load_prompt("ask")),
        schema=claims_schema(bundle.labels),
        temperature=0.0,
        seed=seed,
    )
    return check_claims(completion.text, bundle)


# ── report ─────────────────────────────────────────────────────────────────────


@dataclass
class DeepReport:
    """Every review of a ``--deep`` run, merged.

    Attributes
    ----------
    verdicts : dict
        Finding index (in the lint result) to `Verdict`.
    concerns : list of Concern
    dropped : int
        Uncited concerns discarded.
    reviewed, groups : int
        Groups reviewed, and groups in total (``--deep-max`` limits the first).
    """

    verdicts: dict[int, Verdict] = field(default_factory=dict)
    concerns: list[Concern] = field(default_factory=list)
    dropped: int = 0
    reviewed: int = 0
    groups: int = 0

    def add(self, item: Review) -> None:
        self.verdicts.update(item.verdicts)
        self.concerns += item.concerns
        self.dropped += len(item.dropped)
        self.reviewed += 1

    def sources(self) -> list[Source]:
        """Every cited source, in order of first citation."""
        seen: dict[str, Source] = {}
        for index in sorted(self.verdicts):
            for src in self.verdicts[index].sources:
                seen.setdefault(src.id, src)
        for concern in self.concerns:
            for src in concern.sources:
                seen.setdefault(src.id, src)
        return list(seen.values())


def annotations(report: DeepReport) -> tuple[dict[int, list[str]], list[str]]:
    """Lines to print under each finding, and the trailing block (concerns, sources, counts)."""
    cited = report.sources()
    numbers = {src.id: n for n, src in enumerate(cited, start=1)}

    def refs(sources: tuple[Source, ...]) -> str:
        return "".join(f"[{numbers[s.id]}]" for s in sources)

    per_finding = {}
    for index, verdict in report.verdicts.items():
        note = " (no valid citation)" if verdict.uncited else ""
        per_finding[index] = [f"    [llm] {verdict.verdict}{note}: {verdict.reason} {refs(verdict.sources)}".rstrip()]
    tail: list[str] = []
    if report.concerns:
        tail += ["", "Advisory concerns [llm] (not rule findings; they do not change the exit status):"]
        for concern in report.concerns:
            where = f"{concern.path}:{concern.line}" if concern.line else concern.path
            tail.append(f"  {where}: {concern.text} {refs(concern.sources)}")
    if cited:
        tail += ["", "Sources cited by the review:"]
        tail += [f"  [{numbers[src.id]}] {src.title}  ({src.id})" for src in cited]
    counts = {v: sum(1 for x in report.verdicts.values() if x.verdict == v) for v in VERDICTS}
    summary = f"Review [llm]: {report.reviewed} of {report.groups} group(s); " + ", ".join(
        f"{n} {v}" for v, n in counts.items()
    )
    summary += ". Dismissed findings are still reported and still count."
    if report.dropped:
        summary += f" {report.dropped} uncited concern(s) dropped."
    if report.reviewed < report.groups:
        summary += " Raise --deep-max to review more groups."
    tail += ["", summary]
    return per_finding, tail


def to_json(report: DeepReport) -> tuple[dict[int, dict], dict]:
    """Per-finding ``review`` objects and the top-level ``review`` object of the JSON output."""
    per_finding = {
        index: {"verdict": v.verdict, "reason": v.reason, "sources": [s.id for s in v.sources], "uncited": v.uncited}
        for index, v in report.verdicts.items()
    }
    top = {
        "groups": report.groups,
        "reviewed": report.reviewed,
        "concerns": [
            {"path": c.path, "line": c.line, "text": c.text, "sources": [s.id for s in c.sources]}
            for c in report.concerns
        ],
        "dropped_concerns": report.dropped,
        "sources": [{"id": s.id, "title": s.title} for s in report.sources()],
    }
    return per_finding, top


def parse_location(path: str) -> tuple[str, int | None]:
    """``src/a.f90:120`` -> (``src/a.f90``, 120); a plain path -> (path, None)."""
    match = re.match(r"^(?P<path>.+):(?P<line>\d+)$", path)
    return (match.group("path"), int(match.group("line"))) if match else (path, None)
