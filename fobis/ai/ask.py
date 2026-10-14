"""ask.py — ``fobis ask``: answer a question from the knowledge packs (and the project's own facts), with citations.

Retrieval is the same BM25 + symbol search as ``fobis kb search``. With a project, every procedure of its
sources becomes one more searchable entry: its header, the modules it uses, what it calls (MPI calls apart),
its OpenMP/OpenACC directives and where it is, so "where is the halo exchange done?" finds code locations,
not raw text. The model must cite what it states (`fobis.ai.grounding`).
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
from collections.abc import Iterable
from typing import TYPE_CHECKING

from ..analysis import FileUnits, Unit
from ..analysis.regions import call_name, parse_directive
from ..kb import Chunk, KnowledgeBase, Pack
from ..lint.engine import display_path
from ..llm.provider import messages
from .grounding import ANSWER_TOKENS, ContextBundle, Grounded, Source, check_claims, claims_schema, load_prompt

if TYPE_CHECKING:
    from ..llm.provider import Provider

PROJECT_PACK = "project"
GENERAL_PACKS = ("fortran-std", "hpc-practice", PROJECT_PACK)
# Words naming a programming model, a compiler, a library or a numerical-assessment topic: a question that names
# one is answered from that pack (plus the general ones). Without routing, OpenACC and OpenMP sections compete on
# "parallel", "loop", "private".
_PACK_HINTS = {
    "openmp": re.compile(r"\b(omp|openmp|omp_\w+)\b|!\$omp"),
    "openacc": re.compile(r"\b(acc|openacc|acc_\w+)\b|!\$acc"),
    "mpi": re.compile(r"\b(mpi|mpi_\w+)\b"),
    "compilers": re.compile(r"\b(gfortran|ifx|ifort|nvfortran|pgfortran|compiler flags?|fma)\b"),
    "libraries": re.compile(
        r"\b(hdf5|h5\w+_f|h5dump|h5fc|h5pfc|open ?mpi|intel mpi|mpich|mpirun|mpiexec|mpif90|mpifort|mpiifx)\b"
    ),
    "numerics": re.compile(
        r"\b(significant digits?|round-?off|rounding errors?|richardson|gci|grid convergence|order of accuracy"
        r"|observed order|uncertainty|kahan|reproducib\w*|tolerances?|benchmark\w*|speedup)\b"
    ),
}


def route_packs(question: str, available: Iterable[str]) -> list[str] | None:
    """The packs to search for *question*: the standards it names plus the general packs; None (all packs) when
    it names no programming model."""
    lowered = question.lower()
    named = [name for name, hint in _PACK_HINTS.items() if hint.search(lowered)]
    if not named:
        return None
    available = set(available)
    return [p for p in (*named, *GENERAL_PACKS) if p in available]


DOC_LINES = 4  # doc-comment lines kept per unit


def _doc(unit: Unit, lines: list[str]) -> str:
    """The unit's documentation comment: the ``!<`` lines after its header (FORD), else the ``!>``/``!<`` lines
    just before it (Doxygen); prose only, up to a code fence, at most DOC_LINES lines."""

    def comment(index: int) -> str | None:
        text = lines[index].strip() if 0 <= index < len(lines) else ""
        return text[2:].strip() if text[:2] in ("!<", "!>") else None

    found: list[str] = []
    index = unit.line  # the line after the header (unit.line is 1-based)
    while (text := comment(index)) is not None and not text.startswith("```") and len(found) < DOC_LINES:
        found.append(text)
        index += 1
    if not found:
        index = unit.line - 2
        while (text := comment(index)) is not None and len(found) < DOC_LINES:
            found.insert(0, text)
            index -= 1
    return " ".join(t for t in found if t)


def _unit_text(unit: Unit, path: str, source: list[str] | None = None) -> str:
    calls: list[str] = []
    mpi: list[str] = []
    directives: list[str] = []
    for stmt in unit.statements:
        if stmt.sentinel is not None:
            directive = parse_directive(stmt)
            if directive.construct and not directive.is_end:
                directives.append(f"!${stmt.sentinel} {directive.construct} (line {stmt.line})")
            continue
        name = call_name(stmt)
        if name:
            (mpi if name.startswith("mpi_") else calls).append(name)
    lines = [f"{unit.kind} {unit.name} in {path}, lines {unit.line}-{unit.end_line}"]
    if unit.header is not None:
        lines.append(f"header: {unit.header.text.strip()}")
    doc = _doc(unit, source) if source else ""
    if doc:
        lines.append(f"doc: {doc}")
    if unit.args:
        lines.append(f"arguments: {', '.join(unit.args)}")
    if unit.uses:
        lines.append(f"uses: {', '.join(sorted({u.module for u in unit.uses}))}")
    if calls:
        lines.append(f"calls: {', '.join(dict.fromkeys(calls))}")
    if mpi:
        lines.append(f"MPI calls: {', '.join(dict.fromkeys(mpi))}")
    if directives:
        lines.append("directives: " + "; ".join(directives[:20]))
    return "\n".join(lines)


def project_pack(files: Iterable[FileUnits]) -> Pack:
    """A pseudo knowledge pack with one entry per named unit (module, procedure, program) of *files*."""
    chunks = []
    for file_units in files:
        path = display_path(file_units.source.path)
        for unit in file_units.walk():
            if not unit.name or unit.kind in ("interface", "fragment") or unit.is_interface_body:
                continue
            text = _unit_text(unit, path, file_units.source.lines)
            symbols = tuple(sorted({unit.name, *(w for w in text.replace(",", " ").split() if "_" in w)}))
            chunks.append(
                Chunk(
                    id=f"{PROJECT_PACK}:{path}#{unit.name}",
                    pack=PROJECT_PACK,
                    doc=path,
                    heading=f"{unit.kind} {unit.name} ({path}:{unit.line})",
                    text=text,
                    symbols=symbols,
                )
            )
    return Pack(name=PROJECT_PACK, path="", meta={"title": "this project's sources"}, chunks=chunks, scope="project")


def build_bundle(question: str, kb: KnowledgeBase, k: int = 6, packs: Iterable[str] | None = None) -> ContextBundle:
    """The question and the *k* best matching sections (from *packs* when given, else routed by `route_packs`)."""
    if packs is None:
        packs = route_packs(question, kb.packs)
    sources = []
    for result in kb.search(question, k=k, packs=packs):
        chunk = result.chunk
        where = kb.packs[chunk.pack].meta.get("title", chunk.pack)
        sources.append(Source(id=chunk.id, title=f"{chunk.heading} - {where}", text=chunk.text))
    return ContextBundle(sections=[("Question", question)], sources=sources)


def ask(question_bundle: ContextBundle, provider: Provider, seed: int = 0) -> Grounded:
    """Ask *provider* the question of *question_bundle*, constrained to cite its sources; the checked answer."""
    completion = provider.chat(
        messages(question_bundle.render(), system=load_prompt("ask")),
        schema=claims_schema(question_bundle.labels),
        temperature=0.0,
        seed=seed,
        max_tokens=ANSWER_TOKENS,
    )
    return check_claims(completion.text, question_bundle)
