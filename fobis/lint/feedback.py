"""feedback.py — compiler optimisation reports as evidence for lint rules.

The compiler knows what it actually did: which arrays an OpenACC region copies implicitly at every launch,
which device loop it had to run sequentially, which OpenMP target maps it generated. Its reports are read
from a build log (the output of ``fobis build`` or of a plain compiler run) and attributed to source files:

- nvfortran ``-Minfo`` lines carry a line number under a ``procedure:`` header but no file name; the procedure
  is located through the project index (the ``Compiling <files>`` lines of a ``fobis build`` log resolve a
  name defined in several files);
- gfortran ``-fopt-info`` lines carry ``file:line:col:``.

Messages that cannot be attributed unambiguously are counted, never guessed.
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
from collections.abc import Iterable
from dataclasses import dataclass, field

from ..analysis import FileUnits
from ..analysis.project import ProjectIndex

# Report flags per FoBiS compiler name (used to tell the user how to produce a log).
REPORT_FLAGS = {
    "nvfortran": "-Minfo=accel,mp",
    "pgi": "-Minfo=accel,mp",
    "gnu": "-fopt-info-vec-missed",
    "opencoarrays-gnu": "-fopt-info-vec-missed",
}

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")  # colours of a captured terminal log (FoBiS colours its output)
_COMPILING_RE = re.compile(r"^Compiling\s+(.+?)\s+(?:serially|using \d+ concurrent processes)\s*$")
_NV_PROCEDURE_RE = re.compile(r"^([A-Za-z_]\w*):\s*$")
_NV_LINE_RE = re.compile(r"^\s+(\d+),\s+(.*?)\s*$")
_NV_CONTINUATION_RE = re.compile(r"^\s{6,}(\S.*?)\s*$")
_GNU_RE = re.compile(
    r"^(.+?\.(?:f|for|fpp|f77|f90|f95|f03|f08|ftn|F|FOR|FPP|F77|F90|F95|F03|F08)):(\d+):\d+:\s+(\w+):\s+(.*?)\s*$"
)


@dataclass(frozen=True)
class FeedbackMessage:
    """One compiler report message.

    Attributes
    ----------
    compiler : str
        ``nvfortran`` or ``gfortran``.
    line : int
        Source line the message refers to.
    text : str
        Message text.
    path : str or None
        Source file (gfortran), None until attributed (nvfortran).
    procedure : str or None
        Procedure (nvfortran).
    compiling : tuple of str
        Files named by the last ``Compiling ...`` line of a fobis build log before the message.
    kind : str
        gfortran message kind (``missed``, ``optimized``, ``note``); '' for nvfortran.
    """

    compiler: str
    line: int
    text: str
    path: str | None = None
    procedure: str | None = None
    compiling: tuple[str, ...] = ()
    kind: str = ""


def parse_log(text: str) -> list[FeedbackMessage]:
    """Every nvfortran ``-Minfo`` and gfortran ``-fopt-info`` message in a build log."""
    messages: list[FeedbackMessage] = []
    compiling: tuple[str, ...] = ()
    procedure: str | None = None
    nv_line: int | None = None
    for raw in text.splitlines():
        line = _ANSI_RE.sub("", raw).rstrip()
        match = _COMPILING_RE.match(line)
        if match:
            compiling, procedure, nv_line = tuple(match.group(1).split()), None, None
            continue
        match = _GNU_RE.match(line)
        if match:
            path, lineno, kind, msg = match.groups()
            messages.append(FeedbackMessage("gfortran", int(lineno), msg, path=path, compiling=compiling, kind=kind))
            procedure = None
            continue
        match = _NV_PROCEDURE_RE.match(line)
        if match:
            procedure, nv_line = match.group(1).lower(), None
            continue
        if procedure is None:
            continue
        match = _NV_LINE_RE.match(line)
        if match:
            nv_line = int(match.group(1))
            messages.append(
                FeedbackMessage("nvfortran", nv_line, match.group(2), procedure=procedure, compiling=compiling)
            )
            continue
        match = _NV_CONTINUATION_RE.match(line)
        if match and nv_line is not None:
            messages.append(
                FeedbackMessage("nvfortran", nv_line, match.group(1), procedure=procedure, compiling=compiling)
            )
            continue
        procedure, nv_line = None, None  # anything else ends the -Minfo block
    return messages


def _same_file(a: str, b: str) -> bool:
    a, b = os.path.normpath(a), os.path.normpath(b)
    return a == b or a.endswith(os.sep + b) or b.endswith(os.sep + a)


@dataclass
class Attribution:
    """Feedback messages per source file (display path) and what could not be attributed."""

    by_path: dict[str, list[FeedbackMessage]] = field(default_factory=dict)
    unattributed: list[FeedbackMessage] = field(default_factory=list)

    @property
    def attributed(self) -> int:
        return sum(len(v) for v in self.by_path.values())


def attribute(messages: Iterable[FeedbackMessage], files: Iterable[FileUnits], project: ProjectIndex) -> Attribution:
    """Assign each message to one linted file, or count it as unattributed."""
    files = list(files)
    result = Attribution()
    for message in messages:
        path = None
        if message.path is not None:
            path = next((u.source.path for u in files if _same_file(u.source.path, message.path)), None)
        elif message.procedure is not None:
            candidates = []
            for unit, unit_path in project.procedures.get(message.procedure, []):
                if unit.line <= message.line <= (unit.end_line or message.line):
                    candidates.append(unit_path)
            if len(set(candidates)) > 1 and message.compiling:
                candidates = [p for p in candidates if any(_same_file(p, c) for c in message.compiling)]
            if len(set(candidates)) == 1:
                path = candidates[0]
        if path is None:
            result.unattributed.append(message)
        else:
            result.by_path.setdefault(path, []).append(message)
    return result
