"""matrix.py — build, test and verify every combination of modes and shadows available on the machine.

A cell is a fobos mode rebuilt as a shadow (``none``: the mode's own flags; ``checks``, ``sanitize``, ``strict``:
see `shadow`), always in its own build directory and always compiled from scratch: the user's build tree is never
touched, and a compiler swapped by ``module load`` under the same command name cannot leave stale objects. Each
cell runs in the environment of its ``[verification] setup`` commands (by mode name, compiler name or compiler
family), so one matrix can span compilers that live in different environment modules.

Steps per cell, each a nested ``fobis ... --json`` command: ``build``, ``test`` (when the project has tests) and,
with ``verify``, ``case run`` of every declared case. A cell whose compiler is not found is ``skipped``; a shadow
the compiler has no flags for is ``unsupported``. Across cells, a quantity that differs from the first cell that
produced it beyond the case's tolerance is a **disagreement**. With ``recheck``, failed tests and cases of a cell
are run again under the ``checks`` shadow, whose runtime checks often turn a crash or a wrong number into a
located message.
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
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field

from .probes import Quantity, json_number
from .provenance import COMPILER_COMMANDS
from .shadow import NONE, ShadowError, family, flags_for
from .verify import VerifyError, compare, load_reference, reference_path, tolerance_for, verify

DEFAULT_SHADOWS = (NONE, "checks")

# run(args, env) -> (exit code, stdout, stderr) of ``fobis <args>`` in the project root
Runner = Callable[[list[str], "dict[str, str] | None"], "tuple[int, str, str]"]


@dataclass
class Cell:
    """One mode x shadow combination and what happened to it."""

    mode: str
    shadow: str
    compiler: str = ""
    status: str = "pending"  # ok, fail, skipped, unsupported
    version: str = ""  # first line of the compiler's --version in the cell's environment
    reason: str = ""
    setup: str = ""
    build: dict | None = None
    tests: dict | None = None
    cases: list[dict] = field(default_factory=list)
    recheck: list[dict] = field(default_factory=list)
    quantities: dict[str, dict[str, Quantity]] = field(default_factory=dict)  # case -> name -> quantity

    @property
    def name(self) -> str:
        return f"{self.mode}/{self.shadow}"

    def to_dict(self) -> dict:
        data = {"mode": self.mode, "shadow": self.shadow, "compiler": self.compiler, "status": self.status}
        for key in ("version", "reason", "setup"):
            if getattr(self, key):
                data[key] = getattr(self, key)
        for key in ("build", "tests"):
            if getattr(self, key) is not None:
                data[key] = getattr(self, key)
        if self.cases:
            data["cases"] = self.cases
        if self.recheck:
            data["recheck"] = self.recheck
        return data


@dataclass
class Disagreement:
    """A quantity of a cell that differs from the first cell that produced it, beyond the case's tolerance."""

    case: str
    quantity: str
    cell: str
    baseline: str
    status: str
    tolerance: str
    max_abs: float | None = None
    max_rel: float | None = None
    worst: dict | None = None
    nonfinite: list[str] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict:
        data = {k: v for k, v in self.__dict__.items() if v not in (None, "", [])}
        for key in ("max_abs", "max_rel"):
            if key in data:
                data[key] = json_number(data[key])
        if self.worst:
            data["worst"] = {k: json_number(v) if isinstance(v, float) else v for k, v in self.worst.items()}
        return data


@dataclass
class MatrixResult:
    cells: list[Cell]
    disagreements: list[Disagreement] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.disagreements and all(c.status in ("ok", "skipped", "unsupported") for c in self.cells)

    def to_dict(self) -> dict:
        counts: dict[str, int] = {}
        for cell in self.cells:
            counts[cell.status] = counts.get(cell.status, 0) + 1
        return {
            "status": "ok" if self.ok else "fail",
            "counts": counts,
            "cells": [c.to_dict() for c in self.cells],
            "disagreements": [d.to_dict() for d in self.disagreements],
        }


def _parse_json(text: str) -> dict | None:
    start = text.find("{")
    if start < 0:
        return None
    try:
        data = json.loads(text[start:])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def setup_environment(command: str, base: dict[str, str] | None = None, timeout: float = 300) -> dict[str, str]:
    """The environment after running *command* in bash (``module load ...``, ``source setvars.sh``).

    Raises ``RuntimeError`` with the end of the command's output when it fails.
    """
    script = "{\n" + command + "\n} 1>&2 && env -0"
    done = subprocess.run(
        ["bash", "-c", script], env=base if base is not None else dict(os.environ), capture_output=True, timeout=timeout
    )
    if done.returncode != 0:
        tail = done.stderr.decode(errors="replace").strip().splitlines()[-5:]
        raise RuntimeError(f"setup {command!r} failed (exit {done.returncode}): " + " | ".join(tail))
    env = {}
    for item in done.stdout.decode(errors="replace").split("\0"):
        key, sep, value = item.partition("=")
        if sep and key:
            env[key] = value
    return env


def compiler_version(command: str, env: dict[str, str] | None) -> str:
    """The first line of ``command --version`` in *env* ('' when it cannot run)."""
    try:
        done = subprocess.run(
            [command, "--version"], env=env, capture_output=True, text=True, errors="replace", timeout=60
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return next((line.strip() for line in (done.stdout + done.stderr).splitlines() if line.strip()), "")


def _first_problem(report: dict) -> str:
    """The first diagnosis, compiler error or error of a ``build --json`` document."""
    for diagnosis in report.get("diagnoses", []):
        if diagnosis.get("summary"):
            return diagnosis["summary"]
    for diagnostic in report.get("diagnostics", []):
        if diagnostic.get("severity") in ("error", "ice", "fatal"):
            where = f"{diagnostic.get('file', '')}:{diagnostic.get('line', '')}: " if diagnostic.get("file") else ""
            return where + str(diagnostic.get("message", ""))
    errors = report.get("errors") or []
    return str(errors[0]) if errors else "build failed"


_SANITIZER_ERROR = re.compile(r"ERROR: AddressSanitizer: (?P<kind>[\w-]+)")
_SANITIZER_SUMMARY = re.compile(r"SUMMARY: \w+Sanitizer: (?P<text>.*?)\.?$")
_UBSAN = re.compile(r"^(?P<where>\S+:\d+):\d+: runtime error: (?P<msg>.*)$")
_FRAME = re.compile(r"#\d+ 0x[0-9a-f]+ in \S+ (?P<file>[^\s:]+):(?P<line>\d+)")
_NOT_PROJECT = ("libsanitizer", "sysdeps", "libgfortran", "/usr/", "csu/")


def sanitizer_problem(stderr: str) -> str:
    """The report of AddressSanitizer, LeakSanitizer or UBSan in *stderr*, in one line ('' when none): what, and
    the first frame in the project's code."""
    frame = next(
        (
            f"{m['file']}:{m['line']}"
            for m in _FRAME.finditer(stderr)
            if not any(part in m["file"] for part in _NOT_PROJECT)
        ),
        "",
    )
    at = f" at {frame}" if frame else ""
    if error := _SANITIZER_ERROR.search(stderr):
        return f"AddressSanitizer: {error['kind']}{at}"
    for line in stderr.splitlines():
        if ubsan := _UBSAN.match(line.strip()):
            return f"undefined behaviour at {ubsan['where']}: {ubsan['msg']}"
    if "LeakSanitizer" in stderr or "leaked in" in stderr:
        summary = _SANITIZER_SUMMARY.search(stderr.strip().splitlines()[-1]) if stderr.strip() else None
        what = summary["text"] if summary else "memory leaked"
        return f"memory leak (LeakSanitizer): {what}" + (f", allocated{at}" if frame else "")
    return ""


def _is_leak(problem: str) -> bool:
    return problem.startswith("memory leak")


def _test_problem(result: dict) -> str:
    if result.get("status") == "build-failed":
        return "build failed: " + _first_problem(result)
    if sanitized := sanitizer_problem(result.get("stderr") or ""):
        return sanitized
    for note in result.get("notes", []):
        if note.get("summary"):
            return note["summary"]
    crash = result.get("crash") or {}
    if crash.get("message"):
        return crash["message"]
    tail = (result.get("stderr") or "").strip().splitlines()
    return f"{result.get('status')} (exit {result.get('exit_code')})" + (f": {tail[-1]}" if tail else "")


def _case_problem(result: dict) -> str:
    if result.get("status") == "build-failed":
        return "build failed: " + _first_problem(result.get("build") or {})
    if result.get("probe_errors"):
        return "quantities not read: " + ", ".join(result["probe_errors"])
    if sanitized := sanitizer_problem(result.get("stderr") or ""):
        return sanitized
    tail = (result.get("stderr") or "").strip().splitlines()
    return f"{result.get('status')} (exit {result.get('exit_code')})" + (f": {tail[-1]}" if tail else "")


class Matrix:
    """Run the cells of a project.

    Parameters
    ----------
    modes : list of str
        The fobos modes (rows).
    shadows : list of str
        The shadows (columns); ``none`` is the mode's own flags.
    run : Runner
        Runs ``fobis <args>`` in the project root with an environment (None: FoBiS's own).
    setup : dict
        ``[verification] setup`` commands by mode, compiler or family.
    cases : dict
        The declared cases (name -> `Case`), run with *verify*.
    references_dir : str
        Where the references are (with *verify*).
    has_tests : bool
        Whether ``fobis test`` finds test programs.
    compilers : list of str or None
        Keep only the modes whose compiler or compiler family is listed.
    verify, recheck : bool
        Run the cases; run failures again under the ``checks`` shadow.
    progress : callable
        Receives one line per cell.
    environment : callable
        Setup command -> environment (`setup_environment`; replaceable in tests).
    version : callable
        (compiler command, environment) -> its version line (`compiler_version`; replaceable in tests).
    """

    def __init__(
        self,
        modes: list[str],
        shadows: list[str],
        run: Runner,
        setup: dict[str, str] | None = None,
        cases: dict | None = None,
        references_dir: str = "",
        has_tests: bool = False,
        compilers: list[str] | None = None,
        verify: bool = False,
        recheck: bool = False,
        progress: Callable[[str], None] = lambda _line: None,
        environment: Callable[[str], dict[str, str]] = setup_environment,
        version: Callable[[str, dict[str, str] | None], str] = compiler_version,
    ) -> None:
        self.modes = modes
        self.shadows = shadows
        self._run = run
        self.setup = setup or {}
        self.cases = cases or {}
        self.references_dir = references_dir
        self.has_tests = has_tests
        self.compilers = compilers
        self.verify = verify
        self.recheck = recheck
        self.progress = progress
        self._environment = environment
        self._version = version
        self._envs: dict[str, dict[str, str] | str] = {}
        self._rechecked: dict[tuple[str, str, str], dict] = {}  # (mode, test|case, name): once per mode

    # ── environment and compiler of a mode ─────────────────────────────────────

    def _setup_for(self, mode: str, compiler: str) -> str:
        for key in (mode, compiler, family(compiler) or ""):
            if key and key in self.setup:
                return self.setup[key]
        return ""

    def environment(self, command: str) -> dict[str, str] | None:
        """The environment of a setup *command* (memoised; None without one); ``RuntimeError`` when it fails."""
        if not command:
            return None
        if command not in self._envs:
            try:
                self._envs[command] = self._environment(command)
            except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
                self._envs[command] = str(exc)
        env = self._envs[command]
        if isinstance(env, str):
            raise RuntimeError(env)
        return env

    def compiler_of(self, mode: str, env: dict[str, str] | None) -> tuple[str, str]:
        """(fobos compiler name, compiler command) of *mode*."""
        _, out, _ = self._run(["introspect", "--compiler", "--mode", mode], env)
        compiler = (_parse_json(out) or {}).get("compiler", {})
        name = compiler.get("name", "") or "gnu"
        return name, compiler.get("binary") or COMPILER_COMMANDS.get(name, "")

    # ── the cells ──────────────────────────────────────────────────────────────

    def run(self) -> MatrixResult:
        cells: list[Cell] = []
        for mode in self.modes:
            base = Cell(mode, "")
            env = self._prepare(base)
            if self.compilers:
                wanted = {c.lower() for c in self.compilers}
                if base.compiler.lower() not in wanted and (family(base.compiler) or "") not in wanted:
                    continue
            for shadow in self.shadows:
                cell = Cell(mode, shadow, base.compiler, base.status, base.version, base.reason, base.setup)
                cells.append(cell)
                if cell.status == "pending":
                    self.progress(f"{cell.name} ({cell.compiler})")
                    self._run_cell(cell, env)
        result = MatrixResult(cells)
        result.disagreements = self._disagreements(cells)
        return result

    def _prepare(self, base: Cell) -> dict[str, str] | None:
        """The mode's environment and compiler; *base* skipped when its setup fails or its compiler is missing."""
        name, command = self.compiler_of(base.mode, None)
        base.compiler = name
        base.setup = self._setup_for(base.mode, name)
        try:
            env = self.environment(base.setup)
        except RuntimeError as exc:
            base.status, base.reason = "skipped", str(exc)
            return None
        path = (env if env is not None else os.environ).get("PATH", "")
        if command and shutil.which(command.split()[0], path=path) is None:
            base.status = "skipped"
            base.reason = f"compiler {command} not found" + (
                f" after setup {base.setup!r}" if base.setup else " (a [verification] setup line can load it)"
            )
        elif command:
            base.version = self._version(command.split()[0], env)
        return env

    @staticmethod
    def _cell_args(cell: Cell, shadow: str | None = None) -> list[str]:
        return ["--mode", cell.mode, "--shadow", shadow or cell.shadow]

    def _run_cell(self, cell: Cell, env: dict[str, str] | None) -> None:
        try:
            flags_for(cell.shadow, cell.compiler)
        except ShadowError as exc:
            cell.status, cell.reason = "unsupported", str(exc)
            return
        code, out, err = self._run(["build", *self._cell_args(cell), "--force-compile", "--json"], env)
        report = _parse_json(out) or {"status": "error", "errors": (out + err).strip().splitlines()[-5:]}
        cell.build = {"status": "ok" if code == 0 and report.get("status") != "error" else "error"}
        if cell.build["status"] == "error":
            cell.build["problem"] = _first_problem(report)
            cell.status = "fail"
            return
        failed = False
        if self.has_tests:
            failed |= self._tests(cell, env)
        if self.verify and self.cases:
            failed |= self._cases(cell, env)
        cell.status = "fail" if failed else "ok"

    def _tests(self, cell: Cell, env: dict[str, str] | None) -> bool:
        _, out, err = self._run(["test", *self._cell_args(cell), "--json"], env)
        data = _parse_json(out)
        if data is None:
            tail = (out + err).strip().splitlines()
            cell.tests = {"passed": 0, "failed": 0, "problem": tail[-1] if tail else "no output", "failures": []}
            return True
        results = data.get("results", [])
        failures = [
            {"name": r.get("name"), "status": r.get("status"), "problem": _test_problem(r)}
            for r in results
            if r.get("status") != "passed"
        ]
        cell.tests = {"passed": len(results) - len(failures), "failed": len(failures), "failures": failures}
        if self.recheck and cell.shadow != "checks":
            for failure in failures:  # a leak is not something runtime checks can locate
                if failure["status"] in ("failed", "timeout") and not _is_leak(failure["problem"]):
                    cell.recheck.append(self._recheck_test(cell, failure["name"], env))
        return bool(failures)

    def _recheck_test(self, cell: Cell, name: str, env: dict[str, str] | None) -> dict:
        key = (cell.mode, "test", name)
        if key not in self._rechecked:
            self._rechecked[key] = self._run_recheck_test(cell, name, env)
        return self._rechecked[key]

    def _run_recheck_test(self, cell: Cell, name: str, env: dict[str, str] | None) -> dict:
        _, out, _ = self._run(["test", *self._cell_args(cell, "checks"), "--filter", name, "--json"], env)
        results = (_parse_json(out) or {}).get("results", [])
        result = next((r for r in results if r.get("name") == name), None)
        if result is None:
            return {"test": name, "status": "error", "problem": "the checks shadow did not run it"}
        item = {"test": name, "status": result.get("status")}
        if result.get("status") != "passed":
            item["problem"] = _test_problem(result)
            if result.get("crash"):
                item["crash"] = result["crash"]
        return item

    def _cases(self, cell: Cell, env: dict[str, str] | None) -> bool:
        from .runner import RunResult

        _, out, err = self._run(["case", "run", *self._cell_args(cell), "--json"], env)
        data = _parse_json(out)
        if data is None:
            tail = (out + err).strip().splitlines()
            cell.cases = [{"case": "*", "status": "error", "problem": tail[-1] if tail else "no output"}]
            return True
        failed = False
        for item in data.get("results", []):
            name = item.get("case", "")
            entry = {"case": name, "status": item.get("status")}
            cell.cases.append(entry)
            if item.get("status") != "ok":
                entry["problem"] = _case_problem(item)
                failed = True
                recheckable = item.get("status") in ("failed", "timeout") and not _is_leak(entry["problem"])
                if self.recheck and cell.shadow != "checks" and recheckable:
                    cell.recheck.append(self._recheck_case(cell, name, env))
                continue
            quantities = {q: Quantity.from_dict(q, d) for q, d in (item.get("quantities") or {}).items()}
            cell.quantities[name] = quantities
            case = self.cases.get(name)
            if case is None or not self.references_dir:
                continue
            try:
                reference = load_reference(reference_path(self.references_dir, name))
            except VerifyError as exc:
                entry["verify"] = {"status": "error", "note": str(exc)}
                failed = True
                continue
            if reference is None:
                continue
            outcome = verify(
                [RunResult(name, cell.name, "ok", 0, quantities=list(quantities.values()))], reference, case.tolerance
            )
            entry["verify"] = {"status": outcome.status, "failed": [c.name for c in outcome.comparisons if not c.ok]}
            failed |= outcome.status != "pass"
        return failed

    def _recheck_case(self, cell: Cell, name: str, env: dict[str, str] | None) -> dict:
        key = (cell.mode, "case", name)
        if key not in self._rechecked:
            self._rechecked[key] = self._run_recheck_case(cell, name, env)
        return self._rechecked[key]

    def _run_recheck_case(self, cell: Cell, name: str, env: dict[str, str] | None) -> dict:
        _, out, _ = self._run(["case", "run", name, *self._cell_args(cell, "checks"), "--json"], env)
        results = (_parse_json(out) or {}).get("results", [])
        if not results:
            return {"case": name, "status": "error", "problem": "the checks shadow did not run it"}
        item = {"case": name, "status": results[0].get("status")}
        if item["status"] != "ok":
            item["problem"] = _case_problem(results[0])
        return item

    def _disagreements(self, cells: list[Cell]) -> list[Disagreement]:
        found = []
        baselines: dict[tuple[str, str], tuple[Cell, Quantity]] = {}
        for cell in cells:
            for case, quantities in cell.quantities.items():
                tolerances = getattr(self.cases.get(case), "tolerance", {}) or {}
                for name, quantity in quantities.items():
                    if (case, name) not in baselines:
                        baselines[case, name] = (cell, quantity)
                        continue
                    base_cell, base = baselines[case, name]
                    tolerance = tolerance_for(tolerances, name)
                    comparison = compare(quantity, base, tolerance)
                    if comparison.ok:
                        continue
                    sized = comparison.status != "shape"
                    found.append(
                        Disagreement(
                            case,
                            name,
                            cell.name,
                            base_cell.name,
                            comparison.status,
                            tolerance.text(),
                            comparison.max_abs if sized else None,
                            comparison.max_rel if sized else None,
                            comparison.worst,
                            comparison.nonfinite,
                            comparison.note,
                        )
                    )
        return found


def render_text(result: MatrixResult, shadows: list[str]) -> str:
    """The matrix as a table (modes x shadows), then what failed, what did not run and the disagreements."""
    modes = list(dict.fromkeys(c.mode for c in result.cells))
    by_key = {(c.mode, c.shadow): c for c in result.cells}
    labels = {"ok": "ok", "fail": "FAIL", "skipped": "skipped", "unsupported": "n/a"}
    width = max([len(m) for m in modes] + [4]) + 2
    column = max([len(s) for s in shadows] + [8]) + 2
    lines = ["mode".ljust(width) + "".join(s.ljust(column) for s in shadows).rstrip()]
    for mode in modes:
        row = mode.ljust(width)
        for shadow in shadows:
            cell = by_key.get((mode, shadow))
            row += (labels.get(cell.status, cell.status) if cell else "-").ljust(column)
        lines.append(row.rstrip())
    details = []
    for cell in result.cells:
        if cell.status != "fail":
            continue
        details.append(f"{cell.name} ({cell.version or cell.compiler}):")
        if cell.build and cell.build.get("status") == "error":
            details.append(f"  build: {cell.build.get('problem')}")
        if (cell.tests or {}).get("problem"):
            details.append(f"  tests: {cell.tests['problem']}")
        for failure in (cell.tests or {}).get("failures", []):
            details.append(f"  test {failure['name']}: {failure['problem']}")
        for case in cell.cases:
            if case.get("problem"):
                details.append(f"  case {case['case']}: {case['problem']}")
            elif case.get("verify", {}).get("status") not in (None, "pass"):
                what = ", ".join(case["verify"].get("failed", [])) or case["verify"].get("note", "")
                details.append(f"  case {case['case']}: differs from its reference ({what})")
        for item in cell.recheck:
            kind, what = ("test", item["test"]) if "test" in item else ("case", item.get("case"))
            details.append(
                f"  recheck of {kind} {what} with --shadow checks: {item['status']}"
                + (f": {item['problem']}" if item.get("problem") else "")
            )
    if details:
        lines += ["", "Failures:", *details]
    not_run = []
    for cell in result.cells:
        if cell.status in ("skipped", "unsupported"):
            text = f"  {cell.name if cell.status == 'unsupported' else cell.mode}: {cell.reason}"
            if text not in not_run:
                not_run.append(text)
    if not_run:
        lines += ["", "Not run:", *not_run]
    if result.disagreements:
        lines += ["", "Disagreements between cells (beyond the case's tolerance):"]
        for d in result.disagreements:
            worst = d.worst or {}
            where = f", worst at {worst['index']}: {worst['value']!r} vs {worst['reference']!r}" if worst else ""
            size = f" (max abs {d.max_abs:.3g}, max rel {d.max_rel:.3g}{where})" if d.max_abs is not None else ""
            lines.append(f"  {d.case}.{d.quantity}: {d.cell} vs {d.baseline}: {d.status} at {d.tolerance}{size}")
            for text in [*d.nonfinite, d.note]:
                if text:
                    lines.append(f"    {text}")
    return "\n".join(lines)
