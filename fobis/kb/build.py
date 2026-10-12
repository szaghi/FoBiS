"""build.py — turn markdown (a Claude skill, a notes file) into a knowledge pack.

The conversion keeps the content and drops what is addressed to an AI assistant: YAML front matter, sections
such as "How to Use This Skill", and lines that tell the reader to consult or load a skill or file. Each
remaining section (heading plus body) becomes a chunk; long sections are split at paragraph boundaries.
Symbols (exact technical names: directives, clauses, routines, constraint ids) are taken from code spans and
constraint references so that retrieval can match them exactly.
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
import os
import re
import shutil
from collections.abc import Iterable
from dataclasses import dataclass

from .pack import INDEX_VERSION, PackError, write_meta

MAX_CHUNK_CHARS = 1800
MIN_CHUNK_CHARS = 40
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FRONT_MATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
_DROP_SECTION_RE = re.compile(r"how to use this skill|^reference skills?\b|consult the .* skill", re.IGNORECASE)
_DROP_LINE_RE = re.compile(
    r"\bthis skill\b|\bthe `?[\w.-]+`? skill\b|\bskill\)|load (that|this) file|consult (this|that|the) skill"
    r"|do not answer .* from memory",
    re.IGNORECASE,
)
_CODE_SPAN_RE = re.compile(r"`([^`\n]+)`")
_SYMBOL_TOKEN_RE = re.compile(r"!\$(?:omp|acc)\b(?:\s+[a-z_]+){0,2}|[a-z_][a-z0-9_]{2,}")
_CONSTRAINT_RE = re.compile(r"\b([CR]\d{3,4})\b")


@dataclass(frozen=True)
class Source:
    """One markdown document to convert: its name in the pack and its file."""

    doc: str
    path: str


def skill_sources(path: str) -> list[Source]:
    """The markdown documents of a skill directory (``SKILL.md`` becomes ``overview``), or of one file.

    Raises
    ------
    PackError
        No markdown document found.
    """
    if os.path.isfile(path):
        return [Source(doc=_doc_name(path), path=path)]
    sources = []
    for root, dirs, files in os.walk(path):
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in sorted(files):
            if name.endswith(".md"):
                full = os.path.join(root, name)
                sources.append(Source(doc=_doc_name(full), path=full))
    if not sources:
        raise PackError(f"{path}: no markdown documents")
    return sources


def _doc_name(path: str) -> str:
    stem = os.path.splitext(os.path.basename(path))[0]
    return "overview" if stem == "SKILL" else re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")


def clean(text: str) -> str:
    """Drop front matter, assistant-directed sections and lines."""
    text = _FRONT_MATTER_RE.sub("", text)
    out, skip_level = [], 0
    for line in text.splitlines():
        heading = _HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            if skip_level and level > skip_level:
                continue
            skip_level = level if _DROP_SECTION_RE.search(heading.group(2)) else 0
            if skip_level:
                continue
        elif skip_level or _DROP_LINE_RE.search(line):
            continue
        out.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "section"


def symbols_of(text: str) -> list[str]:
    """Technical names in *text*: code-span tokens and constraint/rule ids, lower case, sorted."""
    found = set()
    for span in _CODE_SPAN_RE.findall(text):
        for token in _SYMBOL_TOKEN_RE.findall(span.lower()):
            found.add(" ".join(token.split()))
    found.update(m.lower() for m in _CONSTRAINT_RE.findall(text))
    return sorted(found)


def _split(body: str) -> list[str]:
    """*body* in parts of at most `MAX_CHUNK_CHARS`, split at blank lines (code blocks kept whole)."""
    if len(body) <= MAX_CHUNK_CHARS:
        return [body]
    paragraphs, current, fence = [], [], False
    for line in body.splitlines():
        if line.strip().startswith("```"):
            fence = not fence
        current.append(line)
        if not line.strip() and not fence:
            paragraphs.append("\n".join(current))
            current = []
    paragraphs.append("\n".join(current))
    parts, part = [], ""
    for paragraph in paragraphs:
        if part and len(part) + len(paragraph) > MAX_CHUNK_CHARS:
            parts.append(part)
            part = ""
        part += paragraph + "\n"
    if part.strip():
        parts.append(part)
    return parts


def chunk_document(pack: str, doc: str, text: str) -> list[dict]:
    """The chunks of one cleaned document, as index entries."""
    chunks: list[dict] = []
    ids: set[str] = set()
    path: list[tuple[int, str]] = []
    state = {"title": "", "body": []}

    def flush() -> None:
        body = "\n".join(state["body"]).strip()
        if len(body) < MIN_CHUNK_CHARS:
            return
        heading = " > ".join(t for _, t in path) or doc
        for idx, part in enumerate(_split(body)):
            slug = _slug(state["title"] or doc) + (f"-{idx + 1}" if idx else "")
            chunk_id, n = f"{pack}:{doc}#{slug}", 2
            while chunk_id in ids:
                chunk_id, n = f"{pack}:{doc}#{slug}-{n}", n + 1
            ids.add(chunk_id)
            text_part = part.strip()
            chunks.append(
                {"id": chunk_id, "doc": doc, "heading": heading, "text": text_part, "symbols": symbols_of(text_part)}
            )

    fence = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            fence = not fence
        heading = None if fence else _HEADING_RE.match(line)
        if heading:
            flush()
            level, title = len(heading.group(1)), heading.group(2).strip()
            path[:] = [(lvl, t) for lvl, t in path if lvl < level] + [(level, title)]
            state["title"], state["body"] = title, []
        else:
            state["body"].append(line)
    flush()
    return chunks


def build_pack(
    sources: Iterable[Source],
    out_dir: str,
    meta: dict[str, str],
    notice: str | None = None,
    allow_unlicensed: bool = False,
    rewrites: Iterable[tuple[str, str]] = (),
) -> int:
    """Write the pack *meta* built from *sources* into *out_dir*; return the number of chunks.

    Parameters
    ----------
    sources : iterable of Source
    out_dir : str
        Pack directory (created; ``pack.ini``, ``NOTICE``, ``index.json`` are overwritten).
    meta : dict
        ``pack.ini`` values; ``name`` is required, ``license`` unless *allow_unlicensed*.
    notice : str or None
        Path of a NOTICE file to copy into the pack.
    allow_unlicensed : bool
        Build without license (private packs, which must never be redistributed).
    rewrites : iterable of (str, str)
        Regular-expression substitutions applied to every cleaned document (e.g. to redirect references
        to files that are not part of the pack).

    Raises
    ------
    PackError
        Invalid name, missing license, unreadable source.
    """
    name = meta.get("name", "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
        raise PackError(f"invalid pack name {name!r}: use lower-case letters, digits and '-'")
    if not meta.get("license") and not allow_unlicensed:
        raise PackError(f"pack {name}: a license is required (use --private for a pack you will not distribute)")
    chunks = []
    for source in sources:
        try:
            with open(source.path, encoding="utf-8") as handle:
                text = clean(handle.read())
            for pattern, replacement in rewrites:
                text = re.sub(pattern, replacement, text)
        except OSError as exc:
            raise PackError(f"{source.path}: {exc}") from exc
        chunks.extend(chunk_document(name, source.doc, text))
    os.makedirs(out_dir, exist_ok=True)
    meta = dict(meta)
    if notice:
        shutil.copyfile(notice, os.path.join(out_dir, "NOTICE"))
        meta["notice"] = "NOTICE"
    write_meta(out_dir, meta)
    with open(os.path.join(out_dir, "index.json"), "w", encoding="utf-8") as handle:
        json.dump({"version": INDEX_VERSION, "chunks": chunks}, handle, indent=0, ensure_ascii=False)
        handle.write("\n")
    return len(chunks)
