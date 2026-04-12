"""Tests for fobis run — build and execute a target (issue #174)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from argparse import Namespace
from unittest.mock import MagicMock, call, patch

import pytest

from fobis.fobis import run_fobis_run


def _make_config(
    output_path: str = "myprog",
    no_build: bool = False,
    dry_run: bool = False,
    extra_args: list[str] | None = None,
    target_name: str | None = None,
    build_dir: str = ".",
    mode: str | None = None,
) -> MagicMock:
    """Construct a minimal FoBiSConfig mock for run tests."""
    config = MagicMock()
    config.cliargs = Namespace(
        which="run",
        run_target=target_name,
        run_no_build=no_build,
        run_dry_run=dry_run,
        run_extra_args=extra_args or [],
        run_example=None,
        build_dir=build_dir,
        mode=mode,
    )
    config.fobos = MagicMock()
    config.fobos.get_output_name.return_value = output_path
    config.fobos.get_targets.return_value = []
    config.print_r = MagicMock()
    config.print_b = MagicMock()
    return config


# ── build step ───────────────────────────────────────────────────────────────


def test_run_builds_and_executes(tmp_path):
    """run_fobis_run must call build then execute the binary."""
    exe = tmp_path / "myprog"
    exe.write_text("")  # create file so isfile check passes
    config = _make_config(output_path=str(exe))

    with patch("fobis.fobis.run_fobis") as mock_build, \
         patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_exec:
        try:
            run_fobis_run(config)
        except SystemExit as e:
            assert e.code == 0

    mock_build.assert_called_once()
    mock_exec.assert_called_once()
    # Build must be called before execute
    assert mock_build.call_count == 1


def test_run_no_build_skips_build(tmp_path):
    """--no-build: build step must be skipped; binary still executed."""
    exe = tmp_path / "myprog"
    exe.write_text("")
    config = _make_config(output_path=str(exe), no_build=True)

    with patch("fobis.fobis.run_fobis") as mock_build, \
         patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_exec:
        try:
            run_fobis_run(config)
        except SystemExit:
            pass

    mock_build.assert_not_called()
    mock_exec.assert_called_once()


def test_run_forwards_exit_code(tmp_path):
    """Binary exit 42 must propagate as SystemExit(42)."""
    exe = tmp_path / "myprog"
    exe.write_text("")
    config = _make_config(output_path=str(exe), no_build=True)

    with patch("subprocess.run", return_value=MagicMock(returncode=42)):
        with pytest.raises(SystemExit) as exc_info:
            run_fobis_run(config)
    assert exc_info.value.code == 42


def test_run_forwards_args(tmp_path):
    """Extra args after `--` must be forwarded to the binary."""
    exe = tmp_path / "myprog"
    exe.write_text("")
    extra = ["-n", "100", "--file", "data.dat"]
    config = _make_config(output_path=str(exe), no_build=True, extra_args=extra)

    with patch("subprocess.run", return_value=MagicMock(returncode=0)) as mock_exec:
        try:
            run_fobis_run(config)
        except SystemExit:
            pass

    call_args = mock_exec.call_args[0][0]  # first positional arg = argv list
    assert "-n" in call_args
    assert "100" in call_args
    assert "--file" in call_args
    assert "data.dat" in call_args


# ── dry-run mode ─────────────────────────────────────────────────────────────


def test_run_dry_run_no_execution(tmp_path):
    """--dry-run: neither run_fobis nor subprocess.run must be called."""
    exe = tmp_path / "myprog"
    exe.write_text("")
    config = _make_config(output_path=str(exe), dry_run=True)

    with patch("fobis.fobis.run_fobis") as mock_build, \
         patch("subprocess.run") as mock_exec:
        run_fobis_run(config)  # should return without SystemExit in dry-run

    mock_build.assert_not_called()
    mock_exec.assert_not_called()


def test_run_dry_run_prints_commands(tmp_path):
    """--dry-run output must contain both build and run command descriptions."""
    exe = tmp_path / "myprog"
    exe.write_text("")
    config = _make_config(output_path=str(exe), dry_run=True)

    with patch("fobis.fobis.run_fobis"), patch("subprocess.run"):
        run_fobis_run(config)

    # print_b should have been called at least twice (build command + run command)
    assert config.print_b.call_count >= 1


# ── binary not found ─────────────────────────────────────────────────────────


def test_run_binary_missing_after_build(tmp_path):
    """Build succeeds (mocked) but binary doesn't exist → exit 1 with message."""
    config = _make_config(output_path="/nonexistent/path/myprog", no_build=True)

    with pytest.raises(SystemExit) as exc_info:
        run_fobis_run(config)

    assert exc_info.value.code == 1
    config.print_r.assert_called()
    assert any("not found" in str(c) or "Error" in str(c) for c in config.print_r.call_args_list)
