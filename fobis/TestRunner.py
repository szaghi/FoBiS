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
    ) -> None:
        self.build_dir = build_dir
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
