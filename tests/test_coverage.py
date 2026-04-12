"""Tests for fobis.Coverage — coverage report generation (issue #180)."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import patch

from fobis.Coverage import CoverageReporter

# ── detect_tool() ────────────────────────────────────────────────────────────


def test_detect_tool_gcovr():
    with patch("shutil.which", side_effect=lambda name: "/usr/bin/gcovr" if name == "gcovr" else None):
        reporter = CoverageReporter(build_dir=".")
        assert reporter.detect_tool() == "gcovr"


def test_detect_tool_lcov_fallback():
    def which_side(name):
        return "/usr/bin/" + name if name in ("lcov", "genhtml") else None

    with patch("shutil.which", side_effect=which_side):
        reporter = CoverageReporter(build_dir=".")
        assert reporter.detect_tool() == "lcov"


def test_detect_tool_none():
    with patch("shutil.which", return_value=None):
        reporter = CoverageReporter(build_dir=".")
        assert reporter.detect_tool() is None


# ── generate(): no .gcda files ───────────────────────────────────────────────


def test_no_gcda_files_exits_1():
    with tempfile.TemporaryDirectory() as build_dir:
        warnings = []
        reporter = CoverageReporter(build_dir=build_dir, print_w=warnings.append)
        # obj/ has no .gcda files
        result = reporter.generate(formats=["html"], output_dir=os.path.join(build_dir, "coverage"))
        assert result == 1
        assert any("coverage data" in w.lower() or "gcda" in w.lower() or "No coverage" in w for w in warnings)


# ── run_gcovr() ──────────────────────────────────────────────────────────────


def _make_gcda(build_dir: str) -> None:
    """Create a fake .gcda file so _find_gcda_files() is satisfied."""
    obj_dir = os.path.join(build_dir, "obj")
    os.makedirs(obj_dir, exist_ok=True)
    open(os.path.join(obj_dir, "main.gcda"), "w").close()


def test_gcovr_html_command_correct():
    with tempfile.TemporaryDirectory() as build_dir:
        _make_gcda(build_dir)
        output_dir = os.path.join(build_dir, "coverage")
        reporter = CoverageReporter(build_dir=build_dir)
        with (
            patch("fobis.Coverage.syswork", return_value=(0, "")) as mock_sw,
            patch("shutil.which", return_value="/usr/bin/gcovr"),
        ):
            reporter.run_gcovr(formats=["html"], output_dir=output_dir)
        cmd = mock_sw.call_args[0][0]
        assert "gcovr" in cmd
        assert "--html-details" in cmd
        assert "index.html" in cmd


def test_gcovr_xml_command_correct():
    with tempfile.TemporaryDirectory() as build_dir:
        _make_gcda(build_dir)
        output_dir = os.path.join(build_dir, "coverage")
        reporter = CoverageReporter(build_dir=build_dir)
        with patch("fobis.Coverage.syswork", return_value=(0, "")) as mock_sw:
            reporter.run_gcovr(formats=["xml"], output_dir=output_dir)
        cmd = mock_sw.call_args[0][0]
        assert "--xml" in cmd
        assert "coverage.xml" in cmd


def test_gcovr_fail_under_passed():
    with tempfile.TemporaryDirectory() as build_dir:
        _make_gcda(build_dir)
        output_dir = os.path.join(build_dir, "coverage")
        reporter = CoverageReporter(build_dir=build_dir)
        with patch("fobis.Coverage.syswork", return_value=(0, "")) as mock_sw:
            reporter.run_gcovr(formats=["html"], output_dir=output_dir, fail_under=80.0)
        cmd = mock_sw.call_args[0][0]
        assert "--fail-under-line" in cmd
        assert "80" in cmd


def test_gcovr_exclude_patterns_passed():
    with tempfile.TemporaryDirectory() as build_dir:
        _make_gcda(build_dir)
        output_dir = os.path.join(build_dir, "coverage")
        reporter = CoverageReporter(build_dir=build_dir)
        with patch("fobis.Coverage.syswork", return_value=(0, "")) as mock_sw:
            reporter.run_gcovr(formats=["html"], output_dir=output_dir, exclude=["test/*"])
        cmd = mock_sw.call_args[0][0]
        assert "--exclude" in cmd
        assert "test/*" in cmd


def test_format_all_runs_both_html_and_xml():
    with tempfile.TemporaryDirectory() as build_dir:
        _make_gcda(build_dir)
        output_dir = os.path.join(build_dir, "coverage")
        reporter = CoverageReporter(build_dir=build_dir)
        with (
            patch("fobis.Coverage.syswork", return_value=(0, "")) as mock_sw,
            patch("shutil.which", return_value="/usr/bin/gcovr"),
        ):
            reporter.generate(formats=["all"], output_dir=output_dir, tool="gcovr")
        cmd = mock_sw.call_args[0][0]
        assert "--html-details" in cmd
        assert "--xml" in cmd


def test_fail_under_exit_code_propagated():
    with tempfile.TemporaryDirectory() as build_dir:
        _make_gcda(build_dir)
        output_dir = os.path.join(build_dir, "coverage")
        reporter = CoverageReporter(build_dir=build_dir)
        with patch("fobis.Coverage.syswork", return_value=(2, "below threshold")):
            result = reporter.run_gcovr(formats=["html"], output_dir=output_dir, fail_under=90.0)
        assert result == 2


# ── run_lcov() ───────────────────────────────────────────────────────────────


def test_lcov_invocations_in_order():
    with tempfile.TemporaryDirectory() as build_dir:
        _make_gcda(build_dir)
        output_dir = os.path.join(build_dir, "coverage")
        reporter = CoverageReporter(build_dir=build_dir)
        calls_made = []
        with patch("fobis.Coverage.syswork", side_effect=lambda cmd: (calls_made.append(cmd), (0, ""))[1]):
            reporter.run_lcov(output_dir=output_dir)
        assert len(calls_made) >= 2
        assert any("lcov" in c and "--capture" in c for c in calls_made)
        assert any("genhtml" in c for c in calls_made)
        # lcov --capture must be called before genhtml
        capture_idx = next(i for i, c in enumerate(calls_made) if "lcov" in c and "--capture" in c)
        genhtml_idx = next(i for i, c in enumerate(calls_made) if "genhtml" in c)
        assert capture_idx < genhtml_idx


# ── output_dir creation ──────────────────────────────────────────────────────


def test_output_dir_created_if_missing():
    with tempfile.TemporaryDirectory() as build_dir:
        _make_gcda(build_dir)
        output_dir = os.path.join(build_dir, "nonexistent_coverage")
        assert not os.path.isdir(output_dir)
        reporter = CoverageReporter(build_dir=build_dir)
        with patch("fobis.Coverage.syswork", return_value=(0, "")):
            reporter.run_gcovr(formats=["html"], output_dir=output_dir)
        assert os.path.isdir(output_dir)
