"""crash.py — ``fobis run --explain`` / ``fobis test --explain``: why a program failed at run time.

Parses what a failed run printed on standard error and its exit status into a `Crash`: the runtime message of
gfortran (``At line N of file F`` + ``Fortran runtime error:``, ``Program received signal``, ``ERROR STOP``),
Intel (``forrtl: severe (408): ...`` + the traceback table), nvfortran (``0: message (file: line)``), and the
backtrace frames when the build has debug information.

Then, with no model, what FoBiS can say from facts:

- **optimised-build backtraces lie**: frames of an optimised build (or one without ``-g``) are often wrong; the
  crash is then not explained from them, and FoBiS names the fobos mode (or build profile) to reproduce it with
  debug information and runtime checks first;
- out-of-bounds and unassociated-pointer errors located, with the declaration of the array;
- ``error stop`` traced back to the statement that printed the message (Intel prints only the message);
- the runtime compiler bugs documented in the hpc-practice pack (gfortran ``-O2`` EFAULT on pointer sections
  passed to explicit-lower-bound dummies; nvfortran CUDA 719 on a reduction into a ``declare create`` module
  allocatable), matched by message, compiler, optimisation and the project's code.

When the location is trustworthy, the model gets the message, the code at the failing line and at its caller,
and the declarations, and answers cited ``cause``/``fix`` claims (`fobis.ai.grounding`).
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
import signal
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..analysis import read_source
from ..analysis.project import build_index
from ..analysis.regions import parse_directive
from ..llm.provider import messages
from .ask import route_packs
from .diagnostics import demangle, strip_ansi
from .explain import (
    _IDENTIFIER,
    COMPILER_NAMES,
    KINDS,
    BuildFacts,
    _clip,
    _code_span,
    _enclosing,
    _module_of,
    _show,
    _specification,
)
from .grounding import ANSWER_TOKENS, ContextBundle, Grounded, Source, check_claims, claims_schema, load_prompt

if TYPE_CHECKING:
    from ..kb import KnowledgeBase
    from ..llm.provider import Provider

FORTRAN_EXTENSIONS = (".f", ".for", ".fpp", ".f77", ".f90", ".f95", ".f03", ".f08", ".f18", ".f23", ".fypp")
BACKTRACES_LIE = "hpc-practice:gpu-practice#correctness-and-debugging-tools"
GFORTRAN_EFAULT = "hpc-practice:gpu-practice#gfortran-o2-bug-pointer-array-assumed-shape-dummy-with-expli"
NVFORTRAN_719 = "hpc-practice:gpu-practice#nvfortran-bug-openacc-reduction-into-a-declare-create-module"

# Flags of a debug build, per compiler family (used when the fobos file has no debug mode)
DEBUG_FLAGS = {
    "gnu": "-O0 -g -fcheck=all -fbacktrace -ffpe-trap=invalid,zero,overflow",
    "intel": "-O0 -g -traceback -check all -fpe0",
    "nvfortran": "-O0 -g -traceback -Mbounds -Ktrap=fp",
}
_FAMILY = {"intel_nextgen": "intel", "pgi": "nvfortran", "opencoarrays-gnu": "gnu"}

_GNU_AT = re.compile(r"^At line (?P<line>\d+) of file (?P<file>.+?)(?: \(unit = .*\))?\s*$")
_GNU_ERROR = re.compile(r"^Fortran runtime error: (?P<msg>.*)$")
_GNU_SIGNAL = re.compile(r"^Program received signal (?P<sig>SIG\w+): (?P<msg>.*)$")
_GNU_FRAME = re.compile(r"^#\d+\s+0x[0-9a-f]+ in (?P<func>\S+)")
_GNU_FRAME_AT = re.compile(r"^\s+at (?P<file>.+):(?P<line>\d+)\s*$")
_ERROR_STOP = re.compile(r"^ERROR STOP\s*(?P<msg>.*)$")
_INTEL_ERROR = re.compile(r"^forrtl: (?P<sev>severe|error|warning) \((?P<code>\d+)\): (?P<msg>.*)$")
_INTEL_ROW = re.compile(r"^(?P<image>\S+)\s+[0-9A-F]{8,16}\s+(?P<func>\S+)\s+(?P<line>\d+|Unknown)\s+(?P<file>\S+)\s*$")
_NV_ERROR = re.compile(r"^0: (?P<msg>.*?)(?: \((?P<file>[^():]+): (?P<line>\d+)\))?\s*$")
_TIMEOUT = re.compile(r"^TIMEOUT after (?P<secs>[\d.]+)s")

_KINDS = [
    ("bounds", re.compile(r"above upper bound|below lower bound|subscript .* (greater|less) than|subscript out of")),
    ("pointer", re.compile(r"pointer \w+ when it is not associated|not associated with a target|disassociated")),
    ("allocation", re.compile(r"already allocated|not allocated|unallocated|allocat\w* fail|out of memory")),
    ("gpu", re.compile(r"cuda_error|failed to launch|launch failed|call to cu\w+ returned error")),
    ("fpe", re.compile(r"floating[- ](point exception|divide|invalid|overflow|underflow)|sigfpe")),
    ("segv", re.compile(r"segmentation fault|invalid memory reference|access violation|sigsegv")),
    ("io", re.compile(r"cannot open file|file not found|end of file|end-of-file|input/output|bad (integer|real)")),
]
_BOUNDS_DETAIL = [
    re.compile(
        r"Index '(?P<index>-?\d+)' of dimension (?P<dim>\d+) of array '(?P<array>\w+)' "
        r"(?P<side>above upper|below lower) bound of (?P<bound>-?\d+)"
    ),
    re.compile(
        r"Subscript #(?P<dim>\d+) of the array (?P<array>\w+) has value (?P<index>-?\d+) which is "
        r"(?P<side>greater than the upper|less than the lower) bound of (?P<bound>-?\d+)",
        re.IGNORECASE,
    ),
]
_NV_BOUNDS = re.compile(r"Subscript out of range for array (?P<array>\w+)")
_NV_BOUNDS_DETAIL = re.compile(
    r"subscript=(?P<index>-?\d+), lower bound=(?P<lower>-?\d+), upper bound=(?P<upper>-?\d+), dimension=(?P<dim>\d+)"
)
_INTEL_POINTER = re.compile(r"Attempt to use pointer (?P<array>\w+) when it is not associated", re.IGNORECASE)
_EFAULT = re.compile(r"errno\s*=\s*14\b|\bEFAULT\b|Bad address")
_CUDA_719 = re.compile(r"CUDA_ERROR_LAUNCH_FAILED|\b719\b|invalid pointer dereference")
_O_FLAG = re.compile(r"(?<!\S)-(?:O(?P<level>[0-4sz]|fast)?|(?P<fast>fast))(?!\S)")


# ── the crash ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Frame:
    """A backtrace frame: function (demangled), and source file and line when the build has debug info."""

    function: str
    file: str | None = None
    line: int | None = None


@dataclass
class Crash:
    """A failed run.

    Attributes
    ----------
    tool : str
        Runtime that reported it: ``gnu``, ``intel``, ``nvfortran`` or ``unknown``.
    kind : str
        ``bounds``, ``pointer``, ``allocation``, ``fpe``, ``segv``, ``gpu``, ``io``, ``error-stop``, ``killed``,
        ``timeout``, ``signal`` or ``exit`` (non-zero status, nothing recognised).
    message : str
        The runtime message (or a description of the signal).
    exit_code : int
        Exit status (negative: killed by that signal).
    file, line : str or None, int or None
        Where the runtime message says it happened (Intel: the innermost located frame).
    frames : list of Frame
        Backtrace frames with a known function, innermost first.
    detail : dict
        Kind-specific values: ``array``, ``index``, ``bound``, ``side``, ``dim`` for bounds errors.
    text : str
        The error output (ANSI colours removed).
    """

    tool: str
    kind: str
    message: str
    exit_code: int
    file: str | None = None
    line: int | None = None
    frames: list[Frame] = field(default_factory=list)
    detail: dict[str, str] = field(default_factory=dict)
    text: str = ""

    @property
    def signal(self) -> str | None:
        if self.exit_code < 0:
            try:
                return signal.Signals(-self.exit_code).name
            except ValueError:
                return f"signal {-self.exit_code}"
        return None

    @property
    def located_frames(self) -> list[Frame]:
        """Frames in Fortran sources with a line number, innermost first."""
        return [f for f in self.frames if f.file and f.line and f.file.lower().endswith(FORTRAN_EXTENSIONS)]

    def to_dict(self) -> dict:
        """JSON-ready form (``test --json``, the MCP server); the location is the runtime's, trusted or not
        (see `trusted_location`)."""
        return {
            "tool": self.tool,
            "kind": self.kind,
            "message": self.message,
            "exit_code": self.exit_code,
            "signal": self.signal,
            "file": self.file,
            "line": self.line,
            "frames": [{"function": f.function, "file": f.file, "line": f.line} for f in self.frames],
            "detail": dict(self.detail),
        }


def _kind_of(message: str) -> str:
    lowered = message.lower()
    for kind, pattern in _KINDS:
        if pattern.search(lowered):
            return kind
    return ""


def parse_crash(output: str, exit_code: int) -> Crash | None:
    """The crash described by the error *output* of a run that ended with *exit_code* (None when it is 0)."""
    if exit_code == 0:
        return None
    text = strip_ansi(output)
    lines = text.splitlines()
    crash = Crash("unknown", "", "", exit_code, text=text.strip())
    found: list[str] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if match := _GNU_AT.match(stripped):
            crash.tool, crash.file, crash.line = "gnu", match.group("file"), int(match.group("line"))
        elif match := _GNU_ERROR.match(stripped):
            crash.tool = "gnu"
            found.append(match.group("msg"))
        elif match := _GNU_SIGNAL.match(stripped):
            crash.tool = "gnu"
            found.append(f"{match.group('sig')}: {match.group('msg')}")
        elif match := _GNU_FRAME.match(stripped):
            at = _GNU_FRAME_AT.match(lines[i + 1]) if i + 1 < len(lines) else None
            if at:
                i += 1
            if match.group("func") != "???":
                crash.frames.append(
                    Frame(
                        demangle(match.group("func")).name,
                        at.group("file") if at else None,
                        int(at.group("line")) if at else None,
                    )
                )
        elif match := _ERROR_STOP.match(stripped):
            crash.kind = "error-stop"
            found.append(match.group("msg").strip().strip("'\""))
        elif match := _INTEL_ERROR.match(stripped):
            crash.tool = "intel"
            crash.detail["code"] = match.group("code")
            found.append(re.sub(r"^fort: \(\d+\): ", "", match.group("msg")))
        elif match := _INTEL_ROW.match(stripped):
            if match.group("func") != "Unknown" and match.group("image") != "Image":
                known = match.group("line") != "Unknown"
                crash.frames.append(
                    Frame(
                        demangle(match.group("func")).name,
                        match.group("file") if known else None,
                        int(match.group("line")) if known else None,
                    )
                )
        elif match := _NV_ERROR.match(stripped):
            crash.tool = "nvfortran"
            found.append(match.group("msg"))
            if match.group("file"):
                crash.file, crash.line = match.group("file"), int(match.group("line"))
            if i + 1 < len(lines) and (detail := _NV_BOUNDS_DETAIL.search(lines[i + 1])):
                crash.detail.update(detail.groupdict())
                i += 1
        elif _TIMEOUT.match(stripped):
            crash.kind = "timeout"
            found.append(stripped)
        i += 1
    crash.message = "; ".join(m for m in found if m)
    crash.kind = crash.kind or _kind_of(crash.message)
    if not crash.kind and crash.signal:
        crash.kind = {"SIGSEGV": "segv", "SIGBUS": "segv", "SIGFPE": "fpe", "SIGKILL": "killed"}.get(
            crash.signal, "signal"
        )
    crash.kind = crash.kind or "exit"
    if not crash.message:
        if crash.signal:
            crash.message = f"killed by {crash.signal}, with no runtime message"
        else:
            last = [ln.strip() for ln in lines if ln.strip()]
            crash.message = last[-1] if last else f"exit status {exit_code}, with no message"
    _bounds_detail(crash)
    if crash.file is None and crash.tool == "intel" and crash.located_frames:
        crash.file, crash.line = crash.located_frames[0].file, crash.located_frames[0].line
    return crash


def _bounds_detail(crash: Crash) -> None:
    for pattern in _BOUNDS_DETAIL:
        match = pattern.search(crash.message)
        if match:
            crash.detail.update(
                array=match.group("array").lower(),
                index=match.group("index"),
                bound=match.group("bound"),
                side="upper" if "upper" in match.group("side") else "lower",
                dim=match.group("dim"),
            )
            return
    if nv := _NV_BOUNDS.search(crash.message):
        crash.detail["array"] = nv.group("array").lower()
        if "index" in crash.detail:
            above = int(crash.detail["index"]) > int(crash.detail["upper"])
            crash.detail["side"] = "upper" if above else "lower"
            crash.detail["bound"] = crash.detail["upper"] if above else crash.detail["lower"]
    if pointer := _INTEL_POINTER.search(crash.message):
        crash.detail["array"] = pointer.group("array").lower()


# ── the build that produced the program ────────────────────────────────────────


@dataclass(frozen=True)
class ModeInfo:
    """A fobos mode: compiler and effective compile flags (build profile included)."""

    name: str
    compiler: str
    cflags: str
    shadow: str = ""

    @property
    def family(self) -> str:
        return _FAMILY.get(self.compiler, self.compiler)

    def as_shadow(self, shadow: str) -> ModeInfo:
        """This mode rebuilt as *shadow* (``--shadow``): its flags transformed; unchanged when unavailable."""
        from ..verification.shadow import ShadowError, flags_for, transform

        try:
            flags = flags_for(shadow, self.compiler)
        except ShadowError:
            return self
        return ModeInfo(self.name, self.compiler, transform(self.cflags, flags.compile, flags.drop), shadow)


def optimisation(compiler: str, cflags: str) -> tuple[int, bool, bool]:
    """(optimisation level, debug information, runtime checks) of a build with *cflags*.

    The last ``-O`` flag wins; without one, the compiler's default applies: gfortran and LFortran 0, nvfortran 1
    (0 with ``-g``), Intel 2 (0 with ``-g``). ``-Ofast``/``-fast`` count as 3, ``-Os``/``-Oz`` as 2.
    """
    family = _FAMILY.get(compiler, compiler)
    flags = cflags.split()
    debug = any(f == "-g" or re.fullmatch(r"-g[0-3]|-ggdb", f) for f in flags)
    level: int | None = None
    for match in _O_FLAG.finditer(cflags):
        value = match.group("level")
        if match.group("fast") or value == "fast":
            level = 3
        elif value in ("s", "z"):
            level = 2
        elif value is None:
            level = 2 if family == "intel" else 1
        else:
            level = int(value)
    if level is None:
        level = {"intel": 0 if debug else 2, "nvfortran": 0 if debug else 1}.get(family, 0)
    checks = any(f.startswith(("-fcheck", "-fsanitize", "-Mbounds", "-check")) or f in ("-C", "-CB") for f in flags)
    return level, debug, checks


def mode_infos(fobos: Any) -> list[ModeInfo]:
    """The modes of a parsed `Fobos` (templates already applied by Fobos; ``$variables`` substituted here)."""
    from ..Profiles import get_profile_flags

    parser = getattr(fobos, "fobos", None)
    if parser is None:
        return []
    names = parser.get("modes", "modes").split() if parser.has_option("modes", "modes") else []
    if not names and parser.has_section("default"):
        names = ["default"]
    variables = sorted((getattr(fobos, "local_variables", {}) or {}).items(), key=lambda kv: -len(kv[0]))
    infos = []
    for name in names:
        if not parser.has_section(name):
            continue

        def value(key: str, default: str = "", section: str = name) -> str:
            raw = parser.get(section, key) if parser.has_option(section, key) else default
            for var, val in variables:
                raw = re.sub(re.escape(var) + r"(?![A-Za-z0-9_])", lambda _m, v=val: v, raw)
            return " ".join(raw.split())

        compiler = value("compiler", "gnu").lower()
        cflags = value("cflags")
        profile = value("build_profile")
        if profile:
            cflags = (get_profile_flags(compiler, profile)["cflags"] + " " + cflags).strip()
        infos.append(ModeInfo(name, compiler, cflags))
    return infos


@dataclass
class RunContext:
    """What FoBiS knows about the failed run: the build mode, the other modes, the project's sources."""

    mode: ModeInfo
    modes: list[ModeInfo] = field(default_factory=list)
    facts: BuildFacts = field(default_factory=BuildFacts)
    command: str = "run"

    @property
    def level(self) -> int:
        return optimisation(self.mode.compiler, self.mode.cflags)[0]

    @property
    def debug(self) -> bool:
        return optimisation(self.mode.compiler, self.mode.cflags)[1]

    def debug_mode(self) -> ModeInfo | None:
        """The fobos mode to reproduce the crash with: unoptimised with debug info, same compiler preferred."""
        candidates = []
        for info in self.modes:
            level, debug, checks = optimisation(info.compiler, info.cflags)
            if info.name != self.mode.name and level == 0 and debug:
                score = (info.family == self.mode.family, checks, "debug" in info.name.lower())
                candidates.append((score, info))
        return max(candidates, key=lambda c: c[0])[1] if candidates else None


# ── deterministic notes ────────────────────────────────────────────────────────


@dataclass
class Note:
    """Something FoBiS says about the crash from facts: summary, facts, advice, knowledge-pack references."""

    kind: str
    summary: str
    facts: list[str] = field(default_factory=list)
    advice: list[str] = field(default_factory=list)
    refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """JSON-ready form (``test --json``, the MCP server)."""
        return {
            "kind": self.kind,
            "summary": self.summary,
            "facts": self.facts,
            "advice": self.advice,
            "refs": self.refs,
        }


def _line_text(path: str | None, line: int | None) -> str | None:
    if not path or not line:
        return None
    lines = read_source(path).splitlines()
    return lines[line - 1].strip() if 0 < line <= len(lines) else None


def _describe(crash: Crash) -> str:
    detail = crash.detail
    if crash.kind == "bounds" and {"array", "index", "bound"} <= set(detail):
        side = "above its upper" if detail.get("side") == "upper" else "below its lower"
        return f"index {detail['index']} of array {detail['array']} is {side} bound {detail['bound']}"
    labels = {
        "bounds": "out-of-bounds array access",
        "pointer": "use of a pointer that is not associated",
        "allocation": "allocation error",
        "fpe": "floating-point exception",
        "segv": "segmentation fault (invalid memory access)",
        "gpu": "GPU runtime error",
        "io": "input/output error",
        "killed": "killed by SIGKILL (often the out-of-memory killer)",
        "timeout": "timeout",
        "signal": f"killed by {crash.signal}",
    }
    return labels.get(crash.kind, "the program failed")


def _crash_note(crash: Crash, ctx: RunContext) -> Note:
    where = f" at {crash.file}:{crash.line}" if crash.file and crash.line else ""
    note = Note(crash.kind, f"{_describe(crash)}{where}")
    note.facts.append(f"runtime message: {crash.message}")
    path = ctx.facts.find_file(crash.file)
    statement = _line_text(path, crash.line)
    if statement:
        note.facts.append(f"statement: {statement}")
    array = crash.detail.get("array")
    if path and crash.line and array:
        unit = _enclosing(ctx.facts.files[path], crash.line)
        scope = unit
        while scope is not None and array not in scope.decls:
            scope = scope.parent
        if scope is not None:
            decl = scope.decls[array]
            text = _line_text(path, decl.line)
            if text:
                note.facts.append(f"declaration: {text} ({_show(path)}:{decl.line})")
            if unit is not None and array in unit.args:
                callers = crash.located_frames[1:2]
                caller = f", called from {_show(callers[0].file)}:{callers[0].line}" if callers else ""
                note.facts.append(f"{array} is a dummy argument of {unit.name}: the caller passes it{caller}.")
            if "pointer" in decl.attrs and (crash.detail.get("bound") == "0" or crash.detail.get("upper") == "-1"):
                note.facts.append(
                    f"{array} is a pointer and its bounds are empty: it is most likely not associated "
                    "(or associated with a zero-size target)."
                )
    return note


def _error_stop_note(crash: Crash, ctx: RunContext) -> Note | None:
    """The ``error stop`` statement(s) whose text contains the printed message."""
    wanted = crash.message.strip().strip("'\"").lower()
    if not wanted:
        return None
    hits = []
    for path, units in ctx.facts.files.items():
        for unit in units.walk():
            for stmt in unit.statements:
                low = stmt.text.lower()
                if "error stop" in low and wanted in low:
                    hits.append((path, stmt))
    if not hits:
        return None
    path, stmt = hits[0]
    note = Note("error-stop", f"the program stopped itself: error stop at {_show(path)}:{stmt.line}")
    note.facts.append(f"statement: {stmt.text.strip()}")
    if len(hits) > 1:
        note.facts.append(
            "the same message is also raised at " + ", ".join(f"{_show(p)}:{s.line}" for p, s in hits[1:4])
        )
    note.advice.append("this is the program's own check failing: look at why its condition holds for this input")
    return note


def _optimised_note(crash: Crash, ctx: RunContext, message_located: bool) -> Note | None:
    level, debug, checks = optimisation(ctx.mode.compiler, ctx.mode.cflags)
    if level == 0 and debug and (checks or crash.kind not in ("segv", "fpe", "signal")):
        return None
    reasons = []
    if level > 0:
        reasons.append(f"optimised (-O{level})")
    if not debug:
        reasons.append("without debug information (-g)")
    if not checks:
        reasons.append("without runtime checks")
    name = f"mode {ctx.mode.name}" if ctx.mode.name else "this build"
    if ctx.mode.shadow:
        name += f" (shadow {ctx.mode.shadow})"
    note = Note("optimised-build", f"{name} is " + ", ".join(reasons), refs=[BACKTRACES_LIE])
    if message_located:
        note.facts.append(
            "the location comes from the runtime message itself; the backtrace frames, often wrong in such a "
            "build, are not used."
        )
    elif level > 0 or not debug:
        note.facts.append(
            "the backtrace of an optimised build is often wrong: the reported routine or line may not be where "
            "the fault is, so FoBiS does not explain the crash from it."
        )
    if crash.kind in ("segv", "fpe", "signal") and not checks:
        note.facts.append(
            "with runtime checks a segmentation fault often becomes a located message (an index out of bounds, "
            "an unassociated pointer)."
        )
    debug_mode = ctx.debug_mode()
    if debug_mode is not None:
        note.advice.append(
            f"reproduce it in a debug build first: fobis {ctx.command} --mode {debug_mode.name} --explain"
        )
    if ctx.mode.shadow != "checks" and ctx.mode.as_shadow("checks").shadow:
        mode_arg = f" --mode {ctx.mode.name}" if ctx.mode.name else ""
        note.advice.append(
            f"{'or ' if debug_mode is not None else ''}rebuild this mode with runtime checks and run it again: "
            f"fobis {ctx.command}{mode_arg} --shadow checks --explain"
        )
    elif debug_mode is None:
        flags = DEBUG_FLAGS.get(ctx.mode.family, DEBUG_FLAGS["gnu"])
        note.advice.append(
            f"the fobos file has no debug mode: add one (`build_profile = debug`, or `cflags = {flags}`) and "
            "reproduce the crash with it"
        )
    return note


def _reductions_into_declare_create(facts: BuildFacts) -> list[tuple[str, str]]:
    """(variable, file:line) of OpenACC reductions into allocatable ``declare create`` module variables."""
    index = build_index(facts.files.values())
    targets = {name for name, var in index.device_variables.items() if var.allocatable}
    found = []
    for path, units in facts.files.items():
        for unit in units.walk():
            for stmt in unit.statements:
                if stmt.sentinel == "acc":
                    for var in parse_directive(stmt).variables("reduction"):
                        if var in targets:
                            found.append((var, f"{_show(path)}:{stmt.line}"))
    return found


def _known_bug_notes(crash: Crash, ctx: RunContext) -> list[Note]:
    notes = []
    if ctx.mode.family == "gnu" and ctx.level >= 2 and _EFAULT.search(crash.text):
        note = Note(
            "compiler-bug",
            "matches a known gfortran -O2+ defect: a pointer array section passed to a dummy with explicit "
            "lower bounds gets a wrong data pointer (EFAULT, errno=14, e.g. in HDF5 writes)",
            refs=[GFORTRAN_EFAULT],
        )
        note.facts.append(f"the build is gfortran -O{ctx.level}, and the output reports EFAULT (errno=14).")
        note.advice += [
            "confirm it: the failure disappears at -O0/-O1",
            "work around it: pass pointer-derived actuals to a routine whose dummy has no explicit lower bounds "
            "(`q(:,:,:,:)`), or to an explicit-shape dummy",
        ]
        notes.append(note)
    if ctx.mode.family == "nvfortran" and _CUDA_719.search(crash.text):
        reductions = _reductions_into_declare_create(ctx.facts)
        if reductions:
            note = Note(
                "compiler-bug",
                "matches a known nvfortran defect: an OpenACC reduction into a module allocatable with "
                "`!$acc declare create` fails at kernel launch (CUDA 719)",
                refs=[NVFORTRAN_719],
            )
            note.facts += [f"reduction into {var} at {where}" for var, where in reductions[:5]]
            note.advice.append(
                "work around it: reduce into a procedure-local allocatable with procedure-scope `declare create` "
                "(allocate, enter data, reduce, update host, exit data), then copy to the module variable"
            )
            notes.append(note)
    return notes


def trusted_location(crash: Crash, ctx: RunContext) -> tuple[str, int] | None:
    """Where the crash happened, when that can be believed.

    gfortran and nvfortran runtime messages carry the line of the failing statement themselves (a constant the
    compiler emits): trusted at any optimisation. Frames (and Intel's location, taken from them) are trusted
    only in an unoptimised build with debug information.
    """
    unoptimised = ctx.level == 0 and ctx.debug
    if crash.file and crash.line and (crash.tool != "intel" or unoptimised):
        return crash.file, crash.line
    located = crash.located_frames
    if located and unoptimised:
        return located[0].file, located[0].line
    return None


def classify_crash(crash: Crash, ctx: RunContext) -> tuple[list[Note], bool]:
    """The notes FoBiS makes from facts, and whether the model should be asked."""
    if crash.kind == "error-stop" or (crash.tool == "unknown" and crash.kind == "exit"):
        note = _error_stop_note(crash, ctx)
        if note is not None:
            return [note], False
    message_located = bool(crash.file and crash.line and crash.tool != "intel")
    location = trusted_location(crash, ctx)
    if location and not (crash.file and crash.line):
        crash.file, crash.line = location
    notes = [_crash_note(crash, ctx)]
    optimised = _optimised_note(crash, ctx, message_located)
    if optimised is not None:
        notes.append(optimised)
    elif location is None:
        notes[0].advice.append(
            "the run reported no location: run it under a debugger (`gdb --args <program>`, then `run` and "
            "`bt`) to see the failing statement"
        )
    known = _known_bug_notes(crash, ctx)
    notes += known
    ask_model = location is not None and not known and crash.kind not in ("error-stop", "timeout", "killed")
    return notes, ask_model


def render_notes(notes: list[Note]) -> str:
    """The deterministic notes as text."""
    lines: list[str] = []
    for note in notes:
        lines.append(note.summary)
        lines += [f"  - {fact}" for fact in note.facts]
        lines += [f"  fix: {todo}" for todo in note.advice]
        lines += [f"  see: fobis kb show {ref}" for ref in note.refs]
        lines.append("")
    return "\n".join(lines).rstrip()


# ── grounded explanation ───────────────────────────────────────────────────────


def build_bundle(
    crash: Crash, ctx: RunContext, kb: KnowledgeBase | None = None, k: int = 2, min_score: float = 10.0
) -> ContextBundle:
    """The model's input: runtime message, build, code at the failing line and at its caller, declarations."""
    level, debug, checks = optimisation(ctx.mode.compiler, ctx.mode.cflags)
    build = [f"compiler: {COMPILER_NAMES.get(ctx.mode.compiler, ctx.mode.compiler)} ({ctx.mode.compiler})"]
    if ctx.mode.name:
        build.append(f"fobos mode: {ctx.mode.name}")
    if ctx.mode.cflags:
        build.append(f"compile flags: {ctx.mode.cflags}")
    build.append(
        f"optimisation -O{level}, debug information: {'yes' if debug else 'no'}, runtime checks: {'yes' if checks else 'no'}"
    )
    sections = [("Runtime error", crash.text or crash.message), ("Build", "\n".join(build))]
    sources: list[Source] = []
    facts = ctx.facts
    location = trusted_location(crash, ctx)
    places = [location] if location else []
    if location and level == 0 and debug:
        for frame in crash.located_frames:
            same = facts.find_file(frame.file) == facts.find_file(location[0]) and frame.line == location[1]
            if not same and facts.find_file(frame.file):
                places.append((frame.file, frame.line))
                break
    for n, (file, line) in enumerate(places):
        path = facts.find_file(file)
        if path is None:
            continue
        shown = _show(path)
        lines = read_source(path).splitlines()
        span, first, last = _code_span(lines, line)
        role = "failing line" if n == 0 else "caller"
        sources.append(Source(f"code:{shown}:{first}-{last}", f"{shown} lines {first}-{last} ({role})", span))
        unit = _enclosing(facts.files[path], line)
        if unit is not None and unit.name:
            sources.append(
                Source(
                    f"fact:{shown}#{unit.name}",
                    f"declarations of {unit.kind} {unit.name} ({shown}:{unit.line})",
                    _specification(unit, lines),
                )
            )
        if n == 0 and 0 < line <= len(lines):
            procedures = facts.procedures()
            for name in dict.fromkeys(w.lower() for w in _IDENTIFIER.findall(lines[line - 1])):
                if unit is not None and name == unit.name:
                    continue
                for proc_path, proc in procedures.get(name, [])[:1]:
                    owner = _module_of(proc)
                    title = f"interface of {proc.kind} {proc.name}" + (f" (module {owner})" if owner else "")
                    sources.append(
                        Source(
                            f"fact:{_show(proc_path)}#{proc.name}",
                            f"{title}, {_show(proc_path)}:{proc.line}",
                            _specification(proc, read_source(proc_path).splitlines()),
                        )
                    )
    if kb is not None:
        packs = route_packs(crash.message, kb.packs) or [p for p in ("fortran-std", "hpc-practice") if p in kb.packs]
        for result in kb.search(crash.message, k=k, packs=packs):
            if result.score >= min_score:
                chunk = result.chunk
                where = kb.packs[chunk.pack].meta.get("title", chunk.pack)
                sources.append(Source(chunk.id, f"{chunk.heading} - {where}", _clip(chunk.text, 1500)))
    return ContextBundle(sections=sections, sources=sources)


def explain_crash(bundle: ContextBundle, provider: Provider, seed: int = 0) -> Grounded:
    """Ask *provider* for the cited cause and fix of the crash in *bundle*."""
    completion = provider.chat(
        messages(bundle.render(), system=load_prompt("crash")),
        schema=claims_schema(bundle.labels, kinds=KINDS),
        temperature=0.0,
        seed=seed,
        max_tokens=ANSWER_TOKENS,
    )
    return check_claims(completion.text, bundle)


def scan_context(fobos: Any, mode: str | None, command: str = "run", shadow: str | None = None) -> RunContext:
    """The `RunContext` of the project in the cwd: modes from *fobos*, the selected *mode* (rebuilt as *shadow*
    when given), the sources."""
    from ..cli._constants import __extensions_parsed__
    from ..lint import discover_files

    modes = mode_infos(fobos)
    wanted = mode or getattr(fobos, "mode", None)
    chosen = next((m for m in modes if m.name == wanted), None) or (modes[0] if modes else ModeInfo("", "gnu", ""))
    if shadow:
        chosen = chosen.as_shadow(shadow)
    files = discover_files(["."], extensions=__extensions_parsed__)
    return RunContext(
        mode=chosen,
        modes=modes,
        facts=BuildFacts.scan(files, deps_dir=fobos.get_deps_dir(), compiler=chosen.compiler, mode=chosen.name),
        command=command,
    )
