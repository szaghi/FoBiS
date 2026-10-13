"""
TestRunner.py — First-class test runner for FoBiS.py.

Implements issue #173: auto-discover Fortran programs under test/,
build them, run them, and report pass/fail with timing.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .utils import print_fake

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class TestResult:
    """Result of running a single test program."""

    name: str
    passed: bool
    exit_code: int
    duration: float
    stdout: str = ""
    stderr: str = ""
    suite: str = ""
    binary: str = ""


@dataclass
class TestSuite:
    """Aggregated results for all discovered tests."""

    results: list[TestResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def duration(self) -> float:
        return sum(r.duration for r in self.results)


# ---------------------------------------------------------------------------
# Suite-tag extraction from source comments
# ---------------------------------------------------------------------------

_SUITE_TAG_RE = re.compile(r"!\s*fobis:\s*suite\s*=\s*(\S+)")


def extract_suite_tag(source_file: str, scan_lines: int = 20) -> str | None:
    """
    Scan the first *scan_lines* of *source_file* for ``! fobis: suite=NAME``.

    Parameters
    ----------
    source_file : str
    scan_lines : int

    Returns
    -------
    str or None
    """
    try:
        with open(source_file) as f:
            for i, line in enumerate(f):
                if i >= scan_lines:
                    break
                m = _SUITE_TAG_RE.search(line)
                if m:
                    return m.group(1)
    except OSError:
        pass
    return None


# ---------------------------------------------------------------------------
# Test discovery
# ---------------------------------------------------------------------------


def discover_tests(
    test_dir: str,
    extensions: list[str] | None = None,
) -> list[dict]:
    """
    Discover Fortran program files under *test_dir*.

    Parameters
    ----------
    test_dir : str
        Directory to scan (e.g. ``'test'`` or ``'tests'``).
    extensions : list[str], optional
        File extensions to consider. Defaults to common Fortran extensions.

    Returns
    -------
    list[dict]
        Each dict has keys: ``name``, ``source``, ``suite``.
    """
    if extensions is None:
        extensions = [".F90", ".f90", ".F", ".f", ".f95", ".F95", ".f03", ".F03"]

    if not os.path.isdir(test_dir):
        return []

    _program_re = re.compile(r"^\s*program\s+(\w+)", re.IGNORECASE)
    tests: list[dict] = []

    for root, _, files in os.walk(test_dir):
        for filename in sorted(files):
            _, ext = os.path.splitext(filename)
            if ext not in extensions:
                continue
            filepath = os.path.join(root, filename)
            prog_name = None
            try:
                with open(filepath) as f:
                    for line in f:
                        m = _program_re.match(line)
                        if m:
                            prog_name = m.group(1)
                            break
            except OSError:
                continue
            if prog_name is None:
                continue
            suite = extract_suite_tag(filepath) or ""
            tests.append(
                {
                    "name": prog_name,
                    "source": filepath,
                    "suite": suite,
                }
            )

    # a test is named after its program; programs sharing a name (every FORTRAN 77 test called `tester`) would share
    # one binary and one report: those are named after their file (its path below test_dir when stems repeat too)
    counts: dict[str, int] = {}
    for test in tests:
        counts[test["name"].lower()] = counts.get(test["name"].lower(), 0) + 1
    stems: dict[str, int] = {}
    for test in tests:
        if counts[test["name"].lower()] > 1:
            stem = os.path.splitext(os.path.basename(test["source"]))[0]
            stems[stem] = stems.get(stem, 0) + 1
    for test in tests:
        if counts[test["name"].lower()] > 1:
            stem = os.path.splitext(os.path.basename(test["source"]))[0]
            if stems[stem] > 1:
                stem = os.path.splitext(os.path.relpath(test["source"], test_dir))[0].replace(os.sep, "_")
            test["name"] = stem
    return tests


# ---------------------------------------------------------------------------
# TestRunner
# ---------------------------------------------------------------------------


class TestRunner:
    """
    Build and run discovered test programs.

    Parameters
    ----------
    build_dir : str
        Directory where compiled test binaries are placed.
    print_n : callable, optional
    print_w : callable, optional
    """

    def __init__(
        self,
        build_dir: str = "build",
        print_n: Callable[..., None] | None = None,
        print_w: Callable[..., None] | None = None,
        scheduler: Any = None,
        jobs_dir: str = os.path.join(".fobis", "runs", "test-jobs"),
    ) -> None:
        self.build_dir = build_dir
        self.scheduler = scheduler  # a verification.scheduler.SlurmScheduler: tests run as batch jobs
        self.jobs_dir = jobs_dir
        self.print_n = print_n if print_n is not None else print_fake
        self.print_w = print_w if print_w is not None else print_fake

    def run_test(
        self,
        test: dict,
        binary_path: str,
        timeout: float = 60.0,
        extra_args: list[str] | None = None,
    ) -> TestResult:
        """
        Run a single test binary and capture the result.

        Parameters
        ----------
        test : dict
        binary_path : str
        timeout : float
        extra_args : list[str], optional

        Returns
        -------
        TestResult
        """
        args = [binary_path] + (extra_args or [])
        if self.scheduler is not None:
            return self._run_job(test, args, timeout)
        start = time.monotonic()
        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            duration = time.monotonic() - start
            return TestResult(
                name=test["name"],
                passed=(proc.returncode == 0),
                exit_code=proc.returncode,
                duration=duration,
                stdout=proc.stdout,
                stderr=proc.stderr,
                suite=test.get("suite", ""),
                binary=binary_path,
            )
        except subprocess.TimeoutExpired:
            duration = time.monotonic() - start
            return TestResult(
                name=test["name"],
                passed=False,
                exit_code=-1,
                duration=duration,
                stdout="",
                stderr=f"TIMEOUT after {timeout}s",
                suite=test.get("suite", ""),
                binary=binary_path,
            )
        except OSError as exc:
            return TestResult(
                name=test["name"],
                passed=False,
                exit_code=-2,
                duration=0.0,
                stdout="",
                stderr=str(exc),
                suite=test.get("suite", ""),
                binary=binary_path,
            )

    def _run_job(self, test: dict, args: list[str], timeout: float) -> TestResult:
        """Run a test program as a scheduler job (its run directory under ``jobs_dir``, shared with the nodes)."""
        from .verification.scheduler import Job, SchedulerError

        job = Job(
            name=test["name"],
            command=[os.path.abspath(args[0]), *args[1:]],
            rundir=os.path.abspath(os.path.join(self.jobs_dir, test["name"])),
            timeout=timeout,
        )
        try:
            done = self.scheduler.submit(job)
        except SchedulerError as exc:
            return TestResult(test["name"], False, -2, 0.0, "", str(exc), test.get("suite", ""), args[0])
        code = done.exit_code if done.exit_code is not None else -1
        return TestResult(
            name=test["name"],
            passed=code == 0,
            exit_code=code,
            duration=done.elapsed,
            stdout=done.stdout,
            stderr=done.stderr,
            suite=test.get("suite", ""),
            binary=args[0],
        )

    def run_suite(
        self,
        tests: list[dict],
        build_fn: Callable[[dict], str | None],
        suite_filter: str | None = None,
        name_filter: str | None = None,
        timeout: float = 60.0,
        extra_args: list[str] | None = None,
        no_build: bool = False,
    ) -> TestSuite:
        """
        Build and run a list of test dicts.

        Parameters
        ----------
        tests : list[dict]
        build_fn : callable
            ``build_fn(test) -> binary_path_or_None``
        suite_filter : str, optional
        name_filter : str, optional
        timeout : float
        extra_args : list[str], optional
        no_build : bool

        Returns
        -------
        TestSuite
        """
        # Apply filters
        filtered = tests
        if suite_filter:
            filtered = [t for t in filtered if t.get("suite") == suite_filter]
        if name_filter:
            import fnmatch

            filtered = [t for t in filtered if fnmatch.fnmatch(t["name"], name_filter)]

        suite = TestSuite()
        for test in filtered:
            if no_build:
                binary = os.path.join(self.build_dir, test["name"])
            else:
                binary = build_fn(test)
            if binary is None or not os.path.isfile(binary):
                result = TestResult(
                    name=test["name"],
                    passed=False,
                    exit_code=-3,
                    duration=0.0,
                    stderr="Build failed or binary not found",
                    suite=test.get("suite", ""),
                )
                suite.results.append(result)
                continue
            result = self.run_test(test, binary, timeout=timeout, extra_args=extra_args)
            suite.results.append(result)
        return suite

    @staticmethod
    def format_results(suite: TestSuite) -> str:
        """
        Return a formatted human-readable summary string.

        Parameters
        ----------
        suite : TestSuite

        Returns
        -------
        str
        """
        lines: list[str] = [""]
        for r in suite.results:
            status = "PASS" if r.passed else "FAIL"
            lines.append(f"  {status}  {r.name:<30} ({r.duration:.2f} s)")
            if not r.passed:
                if r.stderr:
                    for line in r.stderr.strip().splitlines():
                        lines.append(f"        {line}")
        lines.append("")
        lines.append(f"  Results: {suite.passed} passed, {suite.failed} failed, 0 skipped")
        lines.append(f"  Total:   {suite.duration:.2f} s")
        return "\n".join(lines)
