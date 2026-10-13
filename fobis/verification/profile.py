"""profile.py — where a case spends its time, as facts mapped to the source (phase V11 of PLAN-verification.md).

Two CPU backends, both optional tools found on PATH:

- ``gprof``: the case rebuilt with ``-pg`` (a build variant: the mode's own flags, objects apart), run, and the flat
  profile read (self seconds sampled every 0.01 s, call counts). Procedures the compiler inlined count in their
  caller.
- ``callgrind`` (valgrind): the case rebuilt with ``-g`` added (optimisation kept) and run under valgrind; the raw
  ``callgrind.out`` file is parsed for the instructions executed per function AND per source line. Lines carry
  their own file even when inlined, so mapping each line to its enclosing procedure through FoBiS's source analysis
  recovers procedures that vanished into their callers. Instructions, not time: memory stalls are not counted.

Symbols are demangled (gfortran ``__m_MOD_p``, ifx ``m_mp_p_``, nvfortran ``m_p_``) and mapped to the project's
procedures (file and line); costs outside the project's sources (runtime, libraries) are reported as such.
GPU backends (nsys, ncu) are not implemented yet.
"""

from __future__ import annotations

import os
import re
from collections import Counter
from dataclasses import dataclass, field

from .case import CaseError

TOOLS = ("gprof", "callgrind")
GPROF_FLAGS = {"gnu": "-pg", "nvfortran": "-pg", "intel": "-p"}  # per shadow family
_GPROF_ROW = re.compile(
    r"^\s*(?P<pct>[\d.]+)\s+(?P<cum>[\d.]+)\s+(?P<self>[\d.]+)"
    r"(?:\s+(?P<calls>\d+)\s+(?P<self_call>[\d.]+)\s+(?P<total_call>[\d.]+))?\s+(?P<name>\S.*?)\s*$"
)
_SAMPLE = re.compile(r"Each sample counts as ([\d.]+) seconds")
_NAMED = re.compile(r"^\((?P<id>\d+)\)(?:\s+(?P<name>.*))?$")
_POSITION = re.compile(r"[+-]?\d+|\*")


class ProfileError(CaseError):
    """A profile could not be made or read."""


# ── gprof ──────────────────────────────────────────────────────────────────────


@dataclass
class Routine:
    """One function of a profile: its symbol, self cost (seconds or instructions) and calls."""

    symbol: str
    self_cost: float
    calls: int | None = None
    procedure: str = ""  # the project procedure, qualified (module::name)
    location: str = ""  # file:line of its definition
    percent: float = 0.0
    callers: list[dict] = field(default_factory=list)  # callgrind, outside the sources: who in the project calls it

    def to_dict(self) -> dict:
        data = {
            "symbol": self.symbol,
            "procedure": self.procedure,
            "location": self.location,
            "self": self.self_cost,
            "percent": round(self.percent, 2),
            "calls": self.calls,
        }
        if self.callers:
            data["callers"] = self.callers
        return data


def parse_gprof(text: str) -> tuple[list[Routine], float]:
    """The flat profile of ``gprof -b -p``: routines and the sampling interval (seconds)."""
    sample = _SAMPLE.search(text)
    routines, started = [], False
    for line in text.splitlines():
        if line.strip().startswith("time") and "name" in line:
            started = True
            continue
        if not started or not line.strip():
            continue
        match = _GPROF_ROW.match(line)
        if match:
            calls = int(match["calls"]) if match["calls"] else None
            routines.append(Routine(match["name"], float(match["self"]), calls))
    return routines, float(sample.group(1)) if sample else 0.01


# ── callgrind ──────────────────────────────────────────────────────────────────


@dataclass
class Callgrind:
    """Self instructions per function and per source line of one or more ``callgrind.out`` files."""

    total: int = 0
    functions: Counter = field(default_factory=Counter)  # symbol -> self Ir
    lines: Counter = field(default_factory=Counter)  # (file, line) -> self Ir
    calls: Counter = field(default_factory=Counter)  # (caller, callee) -> inclusive Ir of the calls
    call_counts: Counter = field(default_factory=Counter)  # (caller, callee) -> number of calls


def parse_callgrind(text: str, into: Callgrind | None = None) -> Callgrind:
    """Self costs of a raw callgrind file (``positions: line``, ``events: Ir``): name compression ``(id) name``,
    relative positions ``+N``/``-N``/``*``, inlined files (``fi=``/``fe=``), and the inclusive cost line following
    ``calls=`` skipped."""
    found = into or Callgrind()
    files: dict[str, str] = {}
    functions: dict[str, str] = {}
    current_file = function_file = function = callee = ""
    position = 0
    skip_next = False
    count = 0

    def resolve(table: dict[str, str], value: str) -> str:
        match = _NAMED.match(value.strip())
        if not match:
            return value.strip()
        if match["name"]:
            table[match["id"]] = match["name"]
        return table.get(match["id"], value.strip())

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if sep and key in ("fl", "fi", "fe", "fn", "cfi", "cfl", "cfn", "ob", "cob"):
            if key == "fl":
                function_file = current_file = resolve(files, value)
            elif key in ("fi", "fe"):
                current_file = resolve(files, value)
            elif key == "fn":
                function = resolve(functions, value)
                current_file = function_file
            elif key in ("cfi", "cfl"):
                resolve(files, value)  # defines a compressed name; the callee is not costed here
            elif key == "cfn":
                callee = resolve(functions, value)
            continue
        if sep and key == "calls":
            skip_next = True  # the next cost line is the call's inclusive cost: an edge, not self cost
            count = int(value.split()[0]) if value.split() and value.split()[0].isdigit() else 0
            continue
        if line.startswith("totals:"):
            found.total += int(line.split()[1])
            continue
        head = line.split()
        if not _POSITION.fullmatch(head[0]):
            continue
        token = head[0]
        if token != "*":
            position = position + int(token) if token[0] in "+-" else int(token)
        cost = int(head[1]) if len(head) > 1 and head[1].isdigit() else 0
        if skip_next:
            skip_next = False
            found.calls[(function, callee)] += cost
            found.call_counts[(function, callee)] += count
            continue
        found.functions[function] += cost
        found.lines[(current_file, position)] += cost
    return found


# ── mapping to the source ──────────────────────────────────────────────────────


def _same_file(a: str, b: str) -> bool:
    a, b = os.path.normpath(a), os.path.normpath(b)
    return a == b or a.endswith(os.sep + b) or b.endswith(os.sep + a)


def qualified(unit) -> str:
    parts = []
    while unit is not None:
        if unit.name and unit.kind != "interface":
            parts.append(unit.name)
        unit = unit.parent
    return "::".join(reversed(parts))


class SourceMap:
    """The project's procedures by name and by file span (from the source analysis)."""

    def __init__(self, units: dict, root: str = ".") -> None:
        self.root = root
        self.units = units
        self.by_name: dict[str, list[tuple[str, object]]] = {}
        self.modules: set[str] = set()
        for path, file_units in units.items():
            for unit in file_units.walk():
                if unit.kind == "module":
                    self.modules.add(unit.name)
                if unit.name and unit.kind not in ("interface", "fragment"):
                    self.by_name.setdefault(unit.name, []).append((path, unit))

    def _display(self, path: str) -> str:
        return os.path.relpath(os.path.abspath(path), os.path.abspath(self.root)).replace(os.sep, "/")

    def symbol(self, symbol: str) -> tuple[str, str]:
        """(qualified procedure, file:line) of a linker symbol, ('', '') outside the project or ambiguous."""
        from ..ai.diagnostics import demangle

        if symbol == "MAIN__":  # gfortran's main program
            candidates = [(p, u) for p, fu in self.units.items() for u in fu.units if u.kind == "program"]
        else:
            found = demangle(symbol, frozenset(self.modules))
            candidates = self.by_name.get(found.name, [])
            if found.module:
                candidates = [(p, u) for p, u in candidates if qualified(u).startswith(found.module + "::")]
            elif not found.fortran:
                candidates = []
        if len(candidates) != 1:
            return "", ""
        path, unit = candidates[0]
        return qualified(unit), f"{self._display(path)}:{unit.line}"

    def line(self, file: str, number: int) -> tuple[str, str, str]:
        """(project file, innermost procedure, the line's text) of a source position; ('', '', '') outside."""
        for path, file_units in self.units.items():
            if not _same_file(path, file):
                continue
            inner = [u for u in file_units.walk() if u.kind != "interface" and u.line <= number <= (u.end_line or 0)]
            procedure = ""
            if inner:
                unit = min(inner, key=lambda u: u.end_line - u.line)
                procedure = qualified(unit)
                if unit.kind in ("module", "submodule"):  # e.g. `end module`: code the compiler generated
                    procedure += " (module scope)"
            lines = file_units.source.lines
            text = lines[number - 1].strip() if 0 < number <= len(lines) else ""
            return self._display(path), procedure, text
        return "", "", ""


# ── the profile ────────────────────────────────────────────────────────────────


@dataclass
class Profile:
    """What a profiler measured, mapped to the source."""

    tool: str
    unit: str  # "s" (gprof) or "Ir" (callgrind: instructions)
    total: float
    routines: list[Routine] = field(default_factory=list)
    lines: list[dict] = field(default_factory=list)  # callgrind: hottest source lines of the project
    procedures: list[dict] = field(default_factory=list)  # callgrind: project procedures by their source lines
    project_share: float | None = None  # percent of the total in the analysed sources (the mode's, vendored included)
    processes: list[float] = field(default_factory=list)  # gprof: each process's (MPI rank's) own total
    notes: list[str] = field(default_factory=list)

    @property
    def imbalance(self) -> float | None:
        """max / mean of the processes' totals (1 = balanced), None for one process or no time."""
        if len(self.processes) < 2 or not sum(self.processes):
            return None
        return max(self.processes) / (sum(self.processes) / len(self.processes))

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "unit": self.unit,
            "total": self.total,
            "project_share": None if self.project_share is None else round(self.project_share, 2),
            "routines": [r.to_dict() for r in self.routines],
            "procedures": self.procedures,
            "lines": self.lines,
            "processes": self.processes,
            "imbalance": self.imbalance,
            "notes": self.notes,
        }


def from_gprof(text: str, source: SourceMap, top: int) -> Profile:
    routines, sample = parse_gprof(text)
    if not routines:
        raise ProfileError("gprof found no samples (was the program built with -pg and did it run to the end?)")
    total = sum(r.self_cost for r in routines)
    for routine in routines:
        routine.procedure, routine.location = source.symbol(routine.symbol)
        routine.percent = 100 * routine.self_cost / total if total else 0.0
    profile = Profile("gprof", "s", round(total, 6), [r for r in routines if r.self_cost > 0 or r.procedure][:top])
    samples = round(total / sample) if sample else 0
    if samples:
        profile.project_share = sum(r.percent for r in routines if r.procedure)
        profile.notes.append(f"sampled every {sample:g} s ({samples} samples): a routine below a few samples is noise")
    else:
        profile.notes.insert(
            0,
            f"no time measured: the run is shorter than one {sample:g} s sample; only the call counts are facts "
            "(profile a longer case, or use --tool callgrind, which counts instructions)",
        )
    profile.notes.append(
        "procedures inlined by the compiler count in their caller (callgrind's per-line view attributes them to "
        "their own lines)"
    )
    return profile


def _project_callers(data: Callgrind, symbol: str, source: SourceMap, total: int, limit: int = 3) -> list[dict]:
    """The project procedures that call *symbol* directly, by the inclusive cost of their calls."""
    found = []
    for (caller, callee), cost in data.calls.items():
        if callee != symbol or not cost:
            continue
        procedure, location = source.symbol(caller)
        if procedure:
            calls = data.call_counts[(caller, callee)]
            found.append({"procedure": procedure, "location": location, "calls": calls, "inclusive": cost})
    found.sort(key=lambda item: -item["inclusive"])
    for item in found:
        item["percent"] = round(100 * item["inclusive"] / total, 2)
    return found[:limit]


def from_callgrind(data: Callgrind, source: SourceMap, top: int) -> Profile:
    total = data.total or sum(data.functions.values())
    if not total:
        raise ProfileError("callgrind recorded no instructions")
    routines = []
    for symbol, cost in data.functions.most_common():
        procedure, location = source.symbol(symbol)
        routines.append(Routine(symbol, cost, None, procedure, location, 100 * cost / total))
    for routine in routines[:top]:
        if not routine.procedure:  # a runtime/library routine: the project's procedures that call it
            routine.callers = _project_callers(data, routine.symbol, source, total)
    per_procedure: Counter = Counter()
    located = []
    for (file, number), cost in data.lines.items():
        path, procedure, text = source.line(file, number)
        if path and cost:
            per_procedure[procedure or "(outside any procedure)"] += cost
            located.append((cost, path, number, procedure, text))
    located.sort(key=lambda item: (-item[0], item[1], item[2]))
    profile = Profile("callgrind", "Ir", total, routines[:top])
    profile.lines = [
        {"location": f"{p}:{n}", "procedure": proc, "self": c, "percent": round(100 * c / total, 2), "text": t}
        for c, p, n, proc, t in located[:top]
    ]
    profile.procedures = [
        {"procedure": name, "self": cost, "percent": round(100 * cost / total, 2)}
        for name, cost in per_procedure.most_common(top)
    ]
    profile.project_share = 100 * sum(per_procedure.values()) / total
    with_function = {r.procedure for r in routines if r.procedure}
    inlined = sorted(
        p["procedure"]
        for p in profile.procedures
        if p["procedure"] not in with_function and "(" not in p["procedure"]  # not module scope / outside
    )
    profile.notes.append(
        "instructions executed (Ir), not time: memory stalls, cache misses and vector width are not weighed"
    )
    if inlined:
        profile.notes.append(
            "inlined by the compiler (no function of their own, found through their source lines): "
            + ", ".join(inlined)
        )
    return profile


def render_text(case: str, profile: Profile) -> str:
    total = f"{profile.total:.4g} s" if profile.unit == "s" else f"{int(profile.total):,} instructions"
    lines = [f"profile {case} ({profile.tool}): {total}"]
    if profile.project_share is not None:
        lines[0] += f", {profile.project_share:.1f}% in the mode's sources"
    if profile.imbalance is not None:
        each = ", ".join(f"{t:.4g}" for t in profile.processes)
        lines.append(f"  processes: {each} s (imbalance max/mean {profile.imbalance:.2f})")
    lines.append("  routines (self):")
    for r in profile.routines:
        where = f" = {r.procedure} ({r.location})" if r.procedure else " (outside the sources: runtime, libraries)"
        calls = f", {r.calls} calls" if r.calls is not None else ""
        value = f"{r.self_cost:.4g} s" if profile.unit == "s" else f"{int(r.self_cost):,} Ir"
        lines.append(f"    {r.percent:5.1f}%  {value}  {r.symbol}{where}{calls}")
        for c in r.callers:
            lines.append(
                f"             called by {c['procedure']} ({c['location']}): {c['calls']:,} calls, {c['percent']}%"
            )
    if profile.procedures:
        lines.append("  project procedures (by their source lines, inlined code included):")
        lines += [f"    {p['percent']:5.1f}%  {p['procedure']}" for p in profile.procedures]
    if profile.lines:
        lines.append("  hottest lines:")
        lines += [f"    {item['percent']:5.1f}%  {item['location']}  {item['text']}" for item in profile.lines]
    lines += [f"  note: {n}" for n in profile.notes]
    return "\n".join(lines)


# ── running ────────────────────────────────────────────────────────────────────


def wrap(command: list[str], program: list[str], args: list[str], wrapper: list[str]) -> list[str]:
    """*command* (launcher + program + args) with *wrapper* (valgrind ...) put right before the program."""
    start = len(command) - len(program) - len(args)
    return [*command[:start], *wrapper, *command[start:]]
