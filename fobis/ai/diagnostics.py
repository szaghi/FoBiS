"""diagnostics.py — compiler and linker messages as records.

Parses the output of a failed compile or link step into `Diagnostic` records, whatever the compiler: gfortran
(``file:line:col:`` + source excerpt + ``Error:`` line, or the one-line plain form), Intel ifx/ifort
(``file(line): error #NNNN: message [SYMBOL]`` + excerpt), nvfortran (``NVFORTRAN-S-NNNN-message (file: line)``),
LFortran (``semantic error: message`` + `` --> file:line:col``, ANSI colours stripped) and the GNU/LLVM linkers
(``undefined reference to `sym'``, ``multiple definition of `sym'``, lld ``undefined symbol: sym``).

Lines that match no format (summaries, ``collect2``, notes) are ignored. The formats are those of genuine logs
kept in ``tests/build-explain/``.
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
from dataclasses import dataclass

ERROR_SEVERITIES = ("error", "fatal")

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
# gfortran: "file:line:col:" alone (excerpt follows) or followed by the message (-fdiagnostics-plain-output)
_GNU_HEAD = re.compile(
    r"^(?P<file>[^\s:][^:]*):(?P<line>\d+):(?P<col>\d+)(?:-\d+)?:"
    r"(?:\s*(?P<sev>Error|Fatal Error|Warning|Internal compiler error):\s*(?P<msg>.*))?\s*$"
)
_GNU_MSG = re.compile(r"^(?P<sev>Error|Fatal Error|Warning|Internal compiler error):\s*(?P<msg>.*)$")
_INTEL = re.compile(
    r"^(?P<file>.+?)\((?P<line>\d+)\): (?P<sev>error|warning|remark|catastrophic error) #(?P<code>\d+): "
    r"(?P<msg>.*?)(?:\s+\[(?P<sym>[^\]]+)\])?\s*$"
)
_NVIDIA = re.compile(
    r"^NVFORTRAN-(?P<sev>[SFWI])-(?P<code>\d+)-(?P<msg>.*?)(?:\s+\((?P<file>[^():]+): (?P<line>\d+)\))?\s*$"
)
_LFORTRAN = re.compile(
    r"^(?P<sev>semantic error|syntax error|tokenizer error|error|warning|style suggestion): (?P<msg>.*)$"
)
_LFORTRAN_AT = re.compile(r"^\s*-->\s*(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+)")
_LD_PREFIX = re.compile(r"^(?:\S*?(?:ld|ld\.\w+|collect2)(?:\.exe)?: )")
_LD_IN_FUNCTION = re.compile(r"^(?P<obj>.+?): in function [`'](?P<func>[^'`]+)'")
_LD_UNDEFINED = re.compile(
    r"^(?:(?P<file>[^:\s][^:]*?):(?:(?P<line>\d+):)?\([^)]*\): )?undefined reference to [`'](?P<sym>[^'`]+)'"
)
_LD_MULTIPLE = re.compile(
    r"^(?:(?P<file>[^:\s][^:]*?):(?:(?P<line>\d+):)?\([^)]*\): )?multiple definition of [`'](?P<sym>[^'`]+)';"
    r"\s*(?P<first>.*?)(?::\([^)]*\))?: first defined here"
)
_LLD_UNDEFINED = re.compile(r"^error: undefined symbol: (?P<sym>\S+)")
_ICE = re.compile(r"internal compiler error", re.IGNORECASE)

_NV_SEVERITY = {"S": "error", "F": "fatal", "W": "warning", "I": "info"}


@dataclass
class Diagnostic:
    """One compiler or linker message.

    Attributes
    ----------
    tool : str
        ``gnu``, ``intel``, ``nvfortran``, ``lfortran``, ``linker`` or ``compiler`` (a crash message of
        unknown origin).
    severity : str
        ``error``, ``fatal``, ``warning``, ``info`` or ``ice`` (internal compiler error).
    message : str
        The message, without location.
    file, line, column : str, int, int or None
        Where, when the message says it (nvfortran gives no column; the linker gives the referencing source
        file, and a line only with debug information).
    code : str or None
        Message number (ifx ``7002``, nvfortran ``0004``).
    symbol : str or None
        ifx ``[SYMBOL]``; the linker's symbol.
    context : str or None
        Linker: the function referencing the symbol (``MAIN__``), or the object defining it first.
    text : str
        The message block as printed (excerpt included), ANSI colours removed.
    """

    tool: str
    severity: str
    message: str
    file: str | None = None
    line: int | None = None
    column: int | None = None
    code: str | None = None
    symbol: str | None = None
    context: str | None = None
    text: str = ""

    @property
    def is_error(self) -> bool:
        return self.severity in (*ERROR_SEVERITIES, "ice")

    @property
    def where(self) -> str:
        """``file:line`` (or what is known of it)."""
        if self.file and self.line:
            return f"{self.file}:{self.line}"
        return self.file or "?"


def _int(value: str | None) -> int | None:
    return int(value) if value else None


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


def _gnu_block(lines: list[str], i: int, head: re.Match) -> tuple[Diagnostic | None, int]:
    """The gfortran message opened by *head* (at ``lines[i - 1]``) and the index after it."""
    block = [lines[i - 1]]
    sev, msg = head.group("sev"), head.group("msg")
    while sev is None and i < len(lines):
        if _GNU_HEAD.match(lines[i]):  # another location before any message: not a gfortran block
            break
        block.append(lines[i])
        gnu = _GNU_MSG.match(lines[i])
        i += 1
        if gnu:
            sev, msg = gnu.group("sev"), gnu.group("msg")
    if sev is None:
        return None, i
    severity = {"Fatal Error": "fatal", "Internal compiler error": "ice"}.get(sev, sev.lower())
    diagnostic = Diagnostic(
        "gnu",
        severity,
        msg.strip(),
        head.group("file"),
        int(head.group("line")),
        int(head.group("col")),
        text="\n".join(block),
    )
    return diagnostic, i


def parse_diagnostics(output: str) -> list[Diagnostic]:
    """The diagnostics of a compile or link *output*, in order of appearance."""
    lines = strip_ansi(output).splitlines()
    found: list[Diagnostic] = []
    function: str | None = None
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        head = _GNU_HEAD.match(line)
        if head:
            diagnostic, i = _gnu_block(lines, i, head)
            if diagnostic is not None:
                found.append(diagnostic)
            continue
        intel = _INTEL.match(line)
        if intel:
            block = [line]
            while i < len(lines) and len(block) < 3 and lines[i].strip() and not _INTEL.match(lines[i]):
                block.append(lines[i])
                i += 1
            message = intel.group("msg").strip()
            sev = intel.group("sev")
            found.append(
                Diagnostic(
                    "intel",
                    "ice" if _ICE.search(message) else "fatal" if sev == "catastrophic error" else sev,
                    message,
                    intel.group("file"),
                    int(intel.group("line")),
                    code=intel.group("code"),
                    symbol=intel.group("sym"),
                    text="\n".join(block),
                )
            )
            continue
        nvidia = _NVIDIA.match(line)
        if nvidia:
            message = nvidia.group("msg").strip()
            found.append(
                Diagnostic(
                    "nvfortran",
                    "ice" if _ICE.search(message) else _NV_SEVERITY[nvidia.group("sev")],
                    message,
                    nvidia.group("file"),
                    _int(nvidia.group("line")),
                    code=nvidia.group("code"),
                    text=line,
                )
            )
            continue
        lfortran = _LFORTRAN.match(line)
        if lfortran:
            block = [line]
            where = None
            while i < len(lines) and not _LFORTRAN.match(lines[i]) and not lines[i].startswith("Note"):
                where = where or _LFORTRAN_AT.match(lines[i])
                if lines[i].strip():
                    block.append(lines[i])
                i += 1
            sev = lfortran.group("sev")
            message = lfortran.group("msg").strip()
            found.append(
                Diagnostic(
                    "lfortran",
                    "ice"
                    if _ICE.search(message)
                    else "error"
                    if sev.endswith("error")
                    else "warning"
                    if sev == "warning"
                    else "info",
                    message,
                    where.group("file") if where else None,
                    int(where.group("line")) if where else None,
                    int(where.group("col")) if where else None,
                    code=sev,
                    text="\n".join(block),
                )
            )
            continue
        if _ICE.search(line):  # e.g. "f951: internal compiler error: Segmentation fault"
            found.append(Diagnostic("compiler", "ice", line.strip(), text=line))
            continue
        body = _LD_PREFIX.sub("", line)
        in_function = _LD_IN_FUNCTION.match(body)
        if in_function:
            function = in_function.group("func")
            continue
        undefined = _LD_UNDEFINED.match(body) or _LLD_UNDEFINED.match(body)
        if undefined:
            groups = undefined.groupdict()
            found.append(
                Diagnostic(
                    "linker",
                    "error",
                    f"undefined reference to {groups['sym']}",
                    groups.get("file"),
                    _int(groups.get("line")),
                    symbol=groups["sym"],
                    context=function,
                    text=line,
                )
            )
            continue
        multiple = _LD_MULTIPLE.match(body)
        if multiple:
            found.append(
                Diagnostic(
                    "linker",
                    "error",
                    f"multiple definition of {multiple.group('sym')}",
                    multiple.group("file"),
                    _int(multiple.group("line")),
                    symbol=multiple.group("sym"),
                    context=multiple.group("first"),
                    text=line,
                )
            )
    return found


# ── symbol demangling ─────────────────────────────────────────────────────────

_GNU_MODULE_SYMBOL = re.compile(r"^__(?P<module>\w+?)_MOD_(?P<name>\w+)$")
_INTEL_MODULE_SYMBOL = re.compile(r"^(?P<module>\w+?)_mp_(?P<name>\w+?)_$")


@dataclass(frozen=True)
class Symbol:
    """A demangled linker symbol: ``module`` is None for an external procedure (or a non-Fortran symbol)."""

    name: str
    module: str | None = None
    fortran: bool = True

    def __str__(self) -> str:
        return f"{self.module}::{self.name}" if self.module else self.name


def demangle(symbol: str, modules: frozenset[str] | set[str] = frozenset()) -> Symbol:
    """The Fortran entity behind a linker *symbol*.

    gfortran ``__geometry_MOD_area`` and ifx ``geometry_mp_area_`` are unambiguous. nvfortran writes
    ``geometry_area_``: that splits only against the known *modules* (lower case). A trailing underscore
    alone is an external procedure; no underscore at all is a C (or runtime) symbol.
    """
    for pattern in (_GNU_MODULE_SYMBOL, _INTEL_MODULE_SYMBOL):
        match = pattern.match(symbol)
        if match:
            return Symbol(match.group("name").lower(), match.group("module").lower())
    if symbol.endswith("_") and not symbol.startswith("_"):
        base = symbol[:-1].lower()
        for module in sorted(modules, key=len, reverse=True):
            if base.startswith(module + "_") and len(base) > len(module) + 1:
                return Symbol(base[len(module) + 1 :], module)
        return Symbol(base)
    return Symbol(symbol, fortran=False)
