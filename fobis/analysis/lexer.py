"""lexer.py — Fortran source to logical statements (free and fixed form).

The lexer does not parse Fortran: it produces *logical statements* (continuations joined, comments removed,
``;``-separated statements split, labels detached), each with a case-folded *masked* copy in which the contents
of character literals are blanked, so that keyword searches never match inside strings. Compiler directives
with the OpenMP (``!$omp``) and OpenACC (``!$acc``) sentinels become statements of their own, tagged with the
sentinel. Conditional compilation (``#if`` ...) is resolved first with the build mode's defines (see
`fobis.analysis.preprocessor`).

On syntax it does not understand the lexer never fails: the worst outcome is a statement with odd text.
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
import re
from dataclasses import dataclass, field

from .preprocessor import preprocess

FIXED_FORM_EXTENSIONS = frozenset((".f", ".for", ".fpp", ".fortran", ".f77", ".ftn"))
DIRECTIVE_SENTINELS = ("omp", "acc")

_SUPPRESS_RE = re.compile(r"!\s*fobis\s*:\s*ignore\s*\[([^\]]*)\]\s*(.*)$", re.IGNORECASE)
_FREE_DIRECTIVE_RE = re.compile(r"^\s*!\$(omp|acc)(&?)(?=[\s&]|$)", re.IGNORECASE)
_FIXED_DIRECTIVE_RE = re.compile(r"^[!cC*]\$(omp|acc)", re.IGNORECASE)
_LABEL_RE = re.compile(r"^(\d{1,5})\s+(?=\S)")


@dataclass(frozen=True)
class Statement:
    """One logical Fortran statement.

    Attributes
    ----------
    text : str
        Code as written (case preserved), continuations joined, comments and label removed.
    masked : str
        ``text`` lower-cased, with the contents of character literals replaced by blanks (quotes kept).
    line, end_line : int
        First and last physical line (1-based).
    label : str or None
        Statement label.
    sentinel : str or None
        ``"omp"`` / ``"acc"`` for a directive (``text`` then excludes the sentinel), None for code.
    """

    text: str
    masked: str
    line: int
    end_line: int
    label: str | None = None
    sentinel: str | None = None


@dataclass(frozen=True)
class Suppression:
    """An inline ``! fobis: ignore[ID, ...] reason`` comment."""

    line: int
    rules: tuple[str, ...]
    reason: str
    own_line: bool


@dataclass
class SourceFile:
    """A lexed source file.

    Attributes
    ----------
    path : str
    fixed_form : bool
    statements : list of Statement
        Code and directive statements in source order.
    includes : list of (int, str)
        ``#include`` directives and Fortran ``include`` lines (1-based line, file name).
    suppressions : list of Suppression
    warnings : list of (int, str)
        Preprocessor problems.
    lines : list of str
        The raw physical lines.
    """

    path: str
    fixed_form: bool
    statements: list[Statement] = field(default_factory=list)
    includes: list[tuple[int, str]] = field(default_factory=list)
    suppressions: list[Suppression] = field(default_factory=list)
    warnings: list[tuple[int, str]] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)


def mask_strings(text: str) -> str:
    """Lower-case *text* and blank the contents of character literals (quotes are kept)."""
    out, quote, i = [], None, 0
    while i < len(text):
        c = text[i]
        if quote:
            if c == quote:
                if i + 1 < len(text) and text[i + 1] == quote:
                    out.append("  ")
                    i += 2
                    continue
                quote = None
                out.append(c)
            else:
                out.append(" ")
        elif c in "'\"":
            quote = c
            out.append(c)
        else:
            out.append(c.lower())
        i += 1
    return "".join(out)


def _scan(code: str, quote: str | None) -> tuple[str, str | None]:
    """Strip the trailing comment of *code*, honouring a character literal open since a previous line."""
    out, i = [], 0
    while i < len(code):
        c = code[i]
        if quote:
            out.append(c)
            if c == quote:
                if i + 1 < len(code) and code[i + 1] == quote:
                    out.append(c)
                    i += 2
                    continue
                quote = None
        elif c in "'\"":
            quote = c
            out.append(c)
        elif c == "!":
            break
        else:
            out.append(c)
        i += 1
    return "".join(out), quote


def _split_semicolons(text: str) -> list[str]:
    """Split *text* on ``;`` outside character literals."""
    parts, current, quote = [], [], None
    for c in text:
        if quote:
            if c == quote:
                quote = None
        elif c in "'\"":
            quote = c
        elif c == ";":
            parts.append("".join(current))
            current = []
            continue
        current.append(c)
    parts.append("".join(current))
    return parts


class _Builder:
    """Accumulates continued lines into statements."""

    def __init__(self, source: SourceFile) -> None:
        self.source = source
        self.parts: list[str] = []
        self.label: str | None = None
        self.sentinel: str | None = None
        self.first = 0
        self.last = 0

    @property
    def open(self) -> bool:
        return bool(self.parts)

    def add(self, lineno: int, code: str, label: str | None = None, sentinel: str | None = None) -> None:
        if not self.parts:
            self.first, self.label, self.sentinel = lineno, label, sentinel
        self.parts.append(code)
        self.last = lineno

    def flush(self) -> None:
        if not self.parts:
            return
        text = "".join(self.parts)
        pieces = [text] if self.sentinel else _split_semicolons(text)
        label = self.label
        for piece in pieces:
            piece = piece.strip()
            if not piece:
                continue
            if self.sentinel is None and label is None:
                match = _LABEL_RE.match(piece)
                if match:
                    label, piece = match.group(1), piece[match.end() :]
            self.source.statements.append(
                Statement(
                    text=piece,
                    masked=mask_strings(piece),
                    line=self.first,
                    end_line=self.last,
                    label=label,
                    sentinel=self.sentinel,
                )
            )
            label = None
        self.parts = []


def _suppressions(lines: list[str]) -> list[Suppression]:
    found = []
    for idx, raw in enumerate(lines):
        match = _SUPPRESS_RE.search(raw)
        if match:
            rules = tuple(r.strip().upper() for r in match.group(1).split(",") if r.strip())
            own_line = raw[: match.start()].strip() == ""
            found.append(Suppression(line=idx + 1, rules=rules, reason=match.group(2).strip(), own_line=own_line))
    return found


def _lex_free(lines: list[str], active: list[bool], source: SourceFile, openmp: bool) -> None:
    builder, quote, directive_cont = _Builder(source), None, False
    for idx, raw in enumerate(lines):
        if not active[idx]:
            continue
        lineno = idx + 1
        line = raw.rstrip("\n").rstrip("\r")
        directive = _FREE_DIRECTIVE_RE.match(line)
        if directive:
            sentinel = directive.group(1).lower()
            body = line[directive.end() :]
            if not (directive_cont and builder.sentinel == sentinel):
                builder.flush()
            code, _ = _scan(body, None)
            code = code.rstrip()
            directive_cont = code.endswith("&")
            if directive_cont:
                code = code[:-1]
            code = code.lstrip()
            if code.startswith("&"):
                code = code[1:]
            builder.add(lineno, " " + code if builder.open else code, sentinel=sentinel)
            if not directive_cont:
                builder.flush()
            continue
        stripped = line.lstrip()
        if openmp and stripped[:3] == "!$ ":
            line = line.replace("!$", "  ", 1)
            stripped = line.lstrip()
        if not stripped or (stripped.startswith("!") and quote is None):
            continue  # blank or comment line: does not break a continuation
        if builder.open and builder.sentinel is None and not quote:
            if stripped.startswith("&"):
                line = stripped[1:]
        elif builder.open and quote and stripped.startswith("&"):
            line = stripped[1:]
        code, quote = _scan(line, quote)
        code = code.rstrip()
        continued = code.endswith("&")
        if continued:
            code = code[:-1]
        builder.add(lineno, code)
        if not continued:
            quote = None
            builder.flush()
    builder.flush()


def _lex_fixed(lines: list[str], active: list[bool], source: SourceFile, openmp: bool, width: int | None) -> None:
    builder, quote = _Builder(source), None
    for idx, raw in enumerate(lines):
        if not active[idx]:
            continue
        lineno = idx + 1
        line = raw.rstrip("\n").rstrip("\r").expandtabs(6) if raw.startswith("\t") else raw.rstrip("\n\r")
        if width is not None:
            line = line[:width]
        if not line.strip():
            continue
        directive = _FIXED_DIRECTIVE_RE.match(line)
        if directive:
            sentinel = directive.group(1).lower()
            cont_col = line[5:6]
            is_cont = cont_col not in ("", " ", "0")
            code, _ = _scan(line[6:], None)
            if not is_cont or builder.sentinel != sentinel:
                builder.flush()
            builder.add(lineno, (" " if is_cont else "") + code.strip(), sentinel=sentinel)
            continue
        first = line[0]
        if first in "cC*!" and not (openmp and line[:2] == "!$" and line[2:6].strip(" 0123456789") == ""):
            continue
        if openmp and line[:2] in ("!$", "c$", "C$", "*$"):
            line = "  " + line[2:]
        stripped = line.lstrip()
        if stripped.startswith("!") and quote is None:
            continue
        label_field, cont_field, body = line[:5], line[5:6], line[6:]
        if cont_field not in ("", " ", "0") and builder.open and builder.sentinel is None:
            code, quote = _scan(body, quote)
            builder.add(lineno, code.rstrip() if quote is None else code)
            continue
        builder.flush()
        quote = None
        code, quote = _scan(body, None)
        label = label_field.strip() or None
        builder.add(lineno, code.rstrip(), label=label if label and label.isdigit() else None)
    builder.flush()


_FORTRAN_INCLUDE_RE = re.compile(r"""^include\s*(['"])(.+?)\1\s*$""")


def lex(
    text: str,
    path: str = "<string>",
    fixed_form: bool | None = None,
    defines: dict[str, str] | None = None,
    openmp: bool = False,
    fixed_line_length: int | None = 72,
) -> SourceFile:
    """Lex Fortran *text* into a `SourceFile`.

    Parameters
    ----------
    text : str
        Source code.
    path : str
        File name (used for the form when *fixed_form* is None, and reported in results).
    fixed_form : bool or None
        Source form; None infers it from the extension of *path*.
    defines : dict or None
        Preprocessor macros (see `fobis.analysis.preprocessor.parse_defines`).
    openmp : bool
        Compile ``!$ `` conditional-compilation lines as code (OpenMP enabled in the build).
    fixed_line_length : int or None
        Fixed form: characters beyond this column are ignored (72, the compilers' default); None keeps all.
    """
    if fixed_form is None:
        fixed_form = os.path.splitext(path)[1].lower() in FIXED_FORM_EXTENSIONS
    lines = text.splitlines()
    pre = preprocess(lines, defines)
    source = SourceFile(path=path, fixed_form=fixed_form, lines=lines)
    source.includes.extend(pre.includes)
    source.warnings.extend(pre.warnings)
    source.suppressions.extend(_suppressions(lines))
    if fixed_form:
        _lex_fixed(lines, pre.active, source, openmp, fixed_line_length)
    else:
        _lex_free(lines, pre.active, source, openmp)
    for stmt in source.statements:
        if stmt.sentinel is None:
            match = _FORTRAN_INCLUDE_RE.match(stmt.masked)
            if match:
                start = stmt.masked.index(match.group(1)) + 1
                source.includes.append((stmt.line, stmt.text[start : start + len(match.group(2))]))
    source.includes.sort()
    return source


def read_source(path: str) -> str:
    """Read a source file as text, tolerating any byte (undecodable bytes are replaced)."""
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()
