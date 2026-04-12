"""Tests for fobis.TestRunner — first-class test runner (issue #173)."""

from __future__ import annotations

import os
import subprocess
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from fobis.TestRunner import TestResult, TestSuite, discover_tests, extract_suite_tag


# ── extract_suite_tag() ──────────────────────────────────────────────────────


def test_extract_suite_tag_found():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".F90", delete=False) as f:
        f.write("! fobis: suite=integration\nprogram test_io\nimplicit none\nend program\n")
        path = f.name
    try:
        tag = extract_suite_tag(path)
        assert tag == "integration"
    finally:
        os.unlink(path)


def test_extract_suite_tag_not_found():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".F90", delete=False) as f:
        f.write("program test_simple\nimplicit none\nend program\n")
        path = f.name
    try:
        assert extract_suite_tag(path) is None
    finally:
        os.unlink(path)


def test_extract_suite_tag_beyond_scan_limit():
    """Tag beyond first 20 lines must not be found."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".F90", delete=False) as f:
        # 25 blank lines, then the tag
        f.write("\n" * 25 + "! fobis: suite=late\n")
        path = f.name
    try:
        assert extract_suite_tag(path) is None
    finally:
        os.unlink(path)


def test_extract_suite_tag_missing_file_returns_none():
    assert extract_suite_tag("/nonexistent/path/file.F90") is None


# ── discover_tests() ────────────────────────────────────────────────────────


def test_discover_finds_programs():
    with tempfile.TemporaryDirectory() as test_dir:
        # Program file
        prog = os.path.join(test_dir, "test_grid.F90")
        with open(prog, "w") as f:
            f.write("program test_grid\nimplicit none\nend program test_grid\n")
        # Module file — should NOT be discovered
        mod = os.path.join(test_dir, "support.F90")
        with open(mod, "w") as f:
            f.write("module support\nimplicit none\nend module support\n")

        results = discover_tests(test_dir)
        names = [t["name"] for t in results]
        assert "test_grid" in names
        assert "support" not in names


def test_discover_reads_suite_tag():
    with tempfile.TemporaryDirectory() as test_dir:
        prog = os.path.join(test_dir, "test_io.F90")
        with open(prog, "w") as f:
            f.write("! fobis: suite=integration\nprogram test_io\nimplicit none\nend program\n")
        results = discover_tests(test_dir)
        assert len(results) == 1
        assert results[0]["suite"] == "integration"


def test_discover_no_test_dir():
    """Non-existent test/ dir → empty list, no exception."""
    results = discover_tests("/nonexistent/test")
    assert results == []


def test_discover_empty_dir():
    with tempfile.TemporaryDirectory() as test_dir:
        assert discover_tests(test_dir) == []


def test_discover_multiple_tests():
    with tempfile.TemporaryDirectory() as test_dir:
        for name in ("test_a", "test_b", "test_c"):
            path = os.path.join(test_dir, f"{name}.F90")
            with open(path, "w") as f:
                f.write(f"program {name}\nimplicit none\nend program\n")
        results = discover_tests(test_dir)
        assert len(results) == 3


# ── TestRunner.run_test() ────────────────────────────────────────────────────


def test_run_test_pass():
    from fobis.TestRunner import TestRunner

    runner = TestRunner(build_dir="/tmp")
    test = {"name": "test_pass", "source": "/fake/test_pass.F90", "suite": "unit"}
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "all ok"
    mock_result.stderr = ""

    with patch("subprocess.run", return_value=mock_result):
        result = runner.run_test(test, binary_path="/fake/test_pass")

    assert result.passed is True
    assert result.exit_code == 0
    assert result.name == "test_pass"


def test_run_test_fail():
    from fobis.TestRunner import TestRunner

    runner = TestRunner(build_dir="/tmp")
    test = {"name": "test_fail", "source": "/fake/test_fail.F90", "suite": "unit"}
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    mock_result.stderr = "assertion error"

    with patch("subprocess.run", return_value=mock_result):
        result = runner.run_test(test, binary_path="/fake/test_fail")

    assert result.passed is False
    assert result.exit_code == 1


def test_run_test_timeout():
    from fobis.TestRunner import TestRunner

    runner = TestRunner(build_dir="/tmp")
    test = {"name": "test_slow", "source": "/fake/test_slow.F90", "suite": ""}

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="/fake/test_slow", timeout=1.0)):
        result = runner.run_test(test, binary_path="/fake/test_slow", timeout=1.0)

    assert result.passed is False
    assert "timed out" in result.stderr.lower() or "TIMEOUT" in result.stderr


# ── TestSuite aggregation ────────────────────────────────────────────────────


def test_suite_all_pass():
    suite = TestSuite(results=[
        TestResult("a", True, 0, 0.1),
        TestResult("b", True, 0, 0.2),
    ])
    assert suite.passed == 2
    assert suite.failed == 0
    assert suite.total == 2


def test_suite_any_fail():
    suite = TestSuite(results=[
        TestResult("a", True, 0, 0.1),
        TestResult("b", False, 1, 0.2),
    ])
    assert suite.failed == 1


def test_suite_duration():
    suite = TestSuite(results=[
        TestResult("a", True, 0, 1.0),
        TestResult("b", True, 0, 2.0),
    ])
    assert abs(suite.duration - 3.0) < 1e-6


# ── run_suite() filtering ────────────────────────────────────────────────────


def test_suite_filter(tmp_path):
    from fobis.TestRunner import TestRunner

    runner = TestRunner(build_dir=str(tmp_path))
    # Create real (empty) binary files so os.path.isfile passes
    for name in ("test_a", "test_b", "test_c"):
        (tmp_path / name).write_text("")
    tests = [
        {"name": "test_a", "source": "/f/a.F90", "suite": "unit"},
        {"name": "test_b", "source": "/f/b.F90", "suite": "unit"},
        {"name": "test_c", "source": "/f/c.F90", "suite": "integration"},
    ]
    ran = []

    def build_fn(t):
        return str(tmp_path / t["name"])

    def mock_run(test, binary_path, **kwargs):
        ran.append(test["name"])
        return TestResult(test["name"], True, 0, 0.0, suite=test["suite"])

    with patch.object(runner, "run_test", side_effect=mock_run):
        runner.run_suite(tests, build_fn=build_fn, suite_filter="unit")

    assert "test_a" in ran
    assert "test_b" in ran
    assert "test_c" not in ran


def test_name_filter_glob(tmp_path):
    from fobis.TestRunner import TestRunner

    runner = TestRunner(build_dir=str(tmp_path))
    for name in ("test_grid", "test_solver", "test_io"):
        (tmp_path / name).write_text("")
    tests = [
        {"name": "test_grid", "source": "/f/a.F90", "suite": ""},
        {"name": "test_solver", "source": "/f/b.F90", "suite": ""},
        {"name": "test_io", "source": "/f/c.F90", "suite": ""},
    ]
    ran = []

    def build_fn(t):
        return str(tmp_path / t["name"])

    def mock_run(test, binary_path, **kwargs):
        ran.append(test["name"])
        return TestResult(test["name"], True, 0, 0.0)

    with patch.object(runner, "run_test", side_effect=mock_run):
        runner.run_suite(tests, build_fn=build_fn, name_filter="test_s*")

    assert "test_solver" in ran
    assert "test_grid" not in ran
    assert "test_io" not in ran
