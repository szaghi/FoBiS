"""grounding.py — the discipline every LLM feature follows: a deterministic context, cited claims, a check.

A `ContextBundle` holds what the model may use: numbered *sources* (knowledge-pack sections, project facts,
code spans) and plain *sections* (the question, the diagnostic, the build context). It renders the same text
for the same inputs, and the user can print it (``--show-context``) to see exactly what the model saw.

The model answers a JSON object of *claims*, each citing source labels (``S1``, ``S2`` ...). The schema lists
the labels as an enum, so a grammar-constrained server cannot invent one; `check_claims` still verifies every
citation (for servers without grammars) and drops claims that cite nothing or unknown labels. What is dropped
is counted and can be shown, never silently passed as fact.
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

import json
import re
from dataclasses import dataclass, field
from importlib import resources

PROMPTS = "prompts"


def load_prompt(name: str) -> str:
    """The prompt template ``fobis/ai/prompts/<name>.md`` (read through importlib.resources: works from the zipapp)."""
    return resources.files(__package__).joinpath(PROMPTS, f"{name}.md").read_text(encoding="utf-8")


@dataclass(frozen=True)
class Source:
    """Something the model may cite: an id (``openmp:ch07...#key-concepts``), a title and its text."""

    id: str
    title: str
    text: str


@dataclass
class ContextBundle:
    """The model's whole input besides the system prompt.

    Attributes
    ----------
    sections : list of (title, text)
        Plain context, rendered first, in order.
    sources : list of Source
        Citable material, labelled ``S1``, ``S2`` ... in order.
    """

    sections: list[tuple[str, str]] = field(default_factory=list)
    sources: list[Source] = field(default_factory=list)

    @property
    def labels(self) -> list[str]:
        return [f"S{i}" for i in range(1, len(self.sources) + 1)]

    def render(self) -> str:
        """The user message: sections, then the numbered sources."""
        parts = [f"## {title}\n\n{text.strip()}" for title, text in self.sections]
        if self.sources:
            listed = [
                f"[{label}] {src.title} ({src.id})\n{src.text.strip()}"
                for label, src in zip(self.labels, self.sources, strict=True)
            ]
            parts.append("## Sources\n\n" + "\n\n".join(listed))
        return "\n\n".join(parts) + "\n"


def claims_schema(labels: list[str]) -> dict:
    """JSON Schema of a cited answer whose citations can only be *labels*."""
    citation = {"type": "string", "enum": labels} if labels else {"type": "string"}
    return {
        "type": "object",
        "properties": {
            "insufficient": {"type": "boolean"},
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "citations": {"type": "array", "items": citation},
                    },
                    "required": ["text", "citations"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["insufficient", "claims"],
        "additionalProperties": False,
    }


@dataclass(frozen=True)
class Claim:
    """A statement of the model and the sources it cites."""

    text: str
    sources: tuple[Source, ...]


@dataclass
class Grounded:
    """A checked answer.

    Attributes
    ----------
    claims : list of Claim
        Statements with at least one valid citation.
    dropped : list of str
        Statements removed because they cited nothing or only unknown labels.
    insufficient : bool
        The model said the sources do not answer (or nothing survived the check).
    raw : str
        The model's answer as received.
    """

    claims: list[Claim]
    dropped: list[str]
    insufficient: bool
    raw: str

    @property
    def cited(self) -> list[Source]:
        """The sources cited by the kept claims, in order of first citation."""
        seen: dict[str, Source] = {}
        for claim in self.claims:
            for src in claim.sources:
                seen.setdefault(src.id, src)
        return list(seen.values())


def _parse(text: str) -> dict | None:
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def check_claims(raw: str, bundle: ContextBundle) -> Grounded:
    """Keep the claims of *raw* that cite at least one source of *bundle*; drop and count the others.

    An answer that is not the requested JSON yields no claims and is reported as insufficient.
    """
    by_label = dict(zip(bundle.labels, bundle.sources, strict=True))
    data = _parse(raw)
    if data is None:
        return Grounded([], [raw.strip()] if raw.strip() else [], True, raw)
    kept: list[Claim] = []
    dropped: list[str] = []
    for item in data.get("claims") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        labels = [str(c).strip().strip("[]").upper() for c in item.get("citations") or []]
        sources = tuple(dict.fromkeys(by_label[c] for c in labels if c in by_label))
        if sources:
            kept.append(Claim(text, sources))
        else:
            dropped.append(text)
    return Grounded(kept, dropped, bool(data.get("insufficient")) or not kept, raw)


def render_answer(result: Grounded, verbose: bool = False) -> str:
    """Claims with numbered references, the list of sources, and what was dropped."""
    if not result.claims:
        lines = ["The sources found do not answer this question."]
    else:
        numbers = {src.id: i for i, src in enumerate(result.cited, start=1)}
        lines = [f"- {c.text} {''.join(f'[{numbers[s.id]}]' for s in c.sources)}" for c in result.claims]
        lines += ["", "Sources:"] + [f"  [{numbers[s.id]}] {s.title}  ({s.id})" for s in result.cited]
    if result.dropped:
        lines += ["", f"{len(result.dropped)} statement(s) without a valid citation were dropped."]
        if verbose:
            lines += [f"  dropped: {text}" for text in result.dropped]
        else:
            lines[-1] += " Show them with --verbose."
    return "\n".join(lines)


def to_json(result: Grounded) -> dict:
    """Machine-readable form of *result*."""
    return {
        "insufficient": result.insufficient,
        "claims": [{"text": c.text, "sources": [s.id for s in c.sources]} for c in result.claims],
        "dropped": result.dropped,
        "sources": [{"id": s.id, "title": s.title} for s in result.cited],
    }
