"""
Coverage.py — Coverage report generation for FoBiS.py.

Implements issue #180: post-test coverage report generation using gcovr or lcov/genhtml.
Pairs with ``fobis test`` and the ``coverage`` build profile.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable

from .utils import print_fake, syswork

# ---------------------------------------------------------------------------
# CoverageReporter
# ---------------------------------------------------------------------------


class CoverageReporter:
    """
    Generate coverage reports from ``.gcda`` files produced by instrumented builds.

    Parameters
    ----------
    build_dir : str
        Build directory (used to locate obj/ and .gcda files).
    src_dir : str
        Root source directory for filtering coverage to project sources.
    print_n : callable, optional
    print_w : callable, optional
    """

    def __init__(
        self,
        build_dir: str,
        src_dir: str = ".",
        print_n: Callable[..., None] | None = None,
        print_w: Callable[..., None] | None = None,
    ) -> None:
        self.build_dir = os.path.normpath(build_dir)
        self.src_dir = os.path.normpath(src_dir)
        self.print_n = print_n if print_n is not None else print_fake
        self.print_w = print_w if print_w is not None else print_fake

    def detect_tool(self) -> str | None:
        """
        Return the preferred available coverage tool.

        Returns
        -------
        str or None
            ``'gcovr'``, ``'lcov'``, or ``None`` if neither is found.
        """
        if shutil.which("gcovr"):
            return "gcovr"
        if shutil.which("lcov") and shutil.which("genhtml"):
            return "lcov"
        return None

    def _find_gcda_files(self) -> list[str]:
        """Return list of .gcda files under the build obj directory."""
        obj_dir = os.path.join(self.build_dir, "obj")
        gcda: list[str] = []
        if os.path.isdir(obj_dir):
            for root, _, files in os.walk(obj_dir):
                for f in files:
                    if f.endswith(".gcda"):
                        gcda.append(os.path.join(root, f))
        return gcda

    def run_gcovr(
        self,
        formats: list[str],
        output_dir: str,
        exclude: list[str] | None = None,
        fail_under: float | None = None,
    ) -> int:
        """
        Invoke gcovr with the requested output formats.

        Parameters
        ----------
        formats : list[str]
            Subset of ``['html', 'xml', 'text', 'json']``.
        output_dir : str
        exclude : list[str], optional
        fail_under : float, optional

        Returns
        -------
        int
            gcovr exit code.
        """
        os.makedirs(output_dir, exist_ok=True)
        obj_dir = os.path.join(self.build_dir, "obj")
        cmd_parts = [
            "gcovr",
            "--root", self.src_dir,
            "--object-directory", obj_dir,
        ]
        if "html" in formats:
            cmd_parts += ["--html-details", os.path.join(output_dir, "index.html")]
        if "xml" in formats:
            cmd_parts += ["--xml", os.path.join(output_dir, "coverage.xml")]
        if "text" in formats:
            cmd_parts += ["--txt", os.path.join(output_dir, "coverage.txt")]
        if "json" in formats:
            cmd_parts += ["--json", os.path.join(output_dir, "coverage.json")]
        for pat in (exclude or []):
            cmd_parts += ["--exclude", pat]
        if fail_under is not None:
            cmd_parts += ["--fail-under-line", str(int(fail_under))]
        cmd = " ".join(f'"{p}"' if " " in p else p for p in cmd_parts)
        result = syswork(cmd)
        if result[1]:
            self.print_n(result[1])
        return result[0]

    def run_lcov(self, output_dir: str) -> int:
        """
        Invoke lcov + genhtml.

        Parameters
        ----------
        output_dir : str

        Returns
        -------
        int
            Exit code (0 = success).
        """
        os.makedirs(output_dir, exist_ok=True)
        obj_dir = os.path.join(self.build_dir, "obj")
        info_file = os.path.join(output_dir, "lcov.info")
        html_dir = os.path.join(output_dir, "html")

        r1 = syswork(f"lcov --capture --directory {obj_dir} --output-file {info_file}")
        if r1[0] != 0:
            self.print_w(f"lcov capture failed:\n{r1[1]}")
            return r1[0]

        r2 = syswork(f"lcov --extract {info_file} '{self.src_dir}/*' --output-file {info_file}")
        if r2[0] != 0:
            self.print_w(f"lcov extract failed:\n{r2[1]}")
            return r2[0]

        r3 = syswork(f"genhtml {info_file} --output-directory {html_dir}")
        if r3[1]:
            self.print_n(r3[1])
        return r3[0]

    def generate(
        self,
        formats: list[str],
        output_dir: str,
        exclude: list[str] | None = None,
        fail_under: float | None = None,
        tool: str | None = None,
    ) -> int:
        """
        Main entry point: generate coverage reports.

        Parameters
        ----------
        formats : list[str]
            ``['html']``, ``['xml']``, ``['all']``, etc.
        output_dir : str
        exclude : list[str], optional
        fail_under : float, optional
        tool : str or None
            Force a specific tool; auto-detect if None.

        Returns
        -------
        int
            Exit code (0 = success).
        """
        # Check for .gcda files
        gcda_files = self._find_gcda_files()
        if not gcda_files:
            self.print_w(
                "No coverage data found. Did you:\n"
                "  1. Build with 'build_profile = coverage' (or '--build-profile coverage')?\n"
                "  2. Run 'fobis test' to execute the instrumented tests?"
            )
            return 1

        self.print_n(f"Collecting coverage data from {len(gcda_files)} .gcda file(s)...")

        # Resolve formats
        if "all" in formats:
            formats = ["html", "xml", "text"]

        # Detect/select tool
        if tool is None:
            tool = self.detect_tool()
        if tool is None:
            self.print_w(
                "No coverage tool found. Install gcovr (pip install gcovr) or lcov."
            )
            return 1

        self.print_n(f"Using backend: {tool}")

        if tool == "gcovr":
            return self.run_gcovr(formats, output_dir, exclude=exclude, fail_under=fail_under)
        if tool == "lcov":
            return self.run_lcov(output_dir)

        self.print_w(f"Unknown tool: {tool}")
        return 1
