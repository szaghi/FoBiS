"""Tests for convention-based source directory auto-discovery (issue #177)."""

from __future__ import annotations

import contextlib
import os
import tempfile
from unittest.mock import patch

from fobis.utils import auto_discover_src

# ── auto_discover_src() unit tests ───────────────────────────────────────────


def _make_fortran_file(directory: str, name: str = "main.F90") -> None:
    os.makedirs(directory, exist_ok=True)
    open(os.path.join(directory, name), "w").close()


def test_auto_discover_finds_src():
    with tempfile.TemporaryDirectory() as root:
        _make_fortran_file(os.path.join(root, "src"))
        result = auto_discover_src(root)
        assert any("src" in d for d in result)


def test_auto_discover_finds_source_fallback():
    with tempfile.TemporaryDirectory() as root:
        _make_fortran_file(os.path.join(root, "source"))
        result = auto_discover_src(root)
        assert any("source" in d for d in result)
        assert not any(os.path.basename(d) == "src" for d in result)


def test_auto_discover_finds_app():
    with tempfile.TemporaryDirectory() as root:
        _make_fortran_file(os.path.join(root, "app"))
        result = auto_discover_src(root)
        assert any("app" in d for d in result)


def test_auto_discover_both_src_and_app():
    with tempfile.TemporaryDirectory() as root:
        _make_fortran_file(os.path.join(root, "src"))
        _make_fortran_file(os.path.join(root, "app"))
        result = auto_discover_src(root)
        names = [os.path.basename(d) for d in result]
        assert "src" in names
        assert "app" in names


def test_auto_discover_empty_src_not_returned():
    """src/ exists but contains no Fortran files → not included."""
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, "src"))
        # Write a non-Fortran file
        open(os.path.join(root, "src", "readme.txt"), "w").close()
        result = auto_discover_src(root)
        assert result == []


def test_auto_discover_none_found_returns_empty():
    with tempfile.TemporaryDirectory() as root:
        result = auto_discover_src(root)
        assert result == []


def test_auto_discover_subdirectory_fortran_files():
    """Fortran files in a nested subdir of src/ count."""
    with tempfile.TemporaryDirectory() as root:
        nested = os.path.join(root, "src", "lib")
        _make_fortran_file(nested, "module.f90")
        result = auto_discover_src(root)
        assert any("src" in d for d in result)


# ── FoBiSConfig integration: discovery should not fire when src is explicit ──


def test_explicit_src_in_fobos_disables_discovery():
    """When fobos sets src = ./, auto_discover_src must NOT be called."""
    import fobis.utils as utils_mod

    with patch.object(utils_mod, "auto_discover_src", wraps=utils_mod.auto_discover_src) as mock_asd:
        with tempfile.TemporaryDirectory() as root:
            # Create a src/ with Fortran files (would trigger discovery)
            _make_fortran_file(os.path.join(root, "src"))
            # Create a minimal Fortran program in the root
            prog = os.path.join(root, "main.F90")
            with open(prog, "w") as f:
                f.write("program main\nimplicit none\nend program main\n")
            # Write a fobos that explicitly sets src = ./
            fobos_path = os.path.join(root, "fobos")
            with open(fobos_path, "w") as f:
                f.write(
                    "[default]\ncompiler = Gnu\nsrc      = ./\ntarget   = main.F90\noutput   = myprog\nbuild_dir = ./\n"
                )
            prev = os.getcwd()
            os.chdir(root)
            try:
                from fobis.fobis import run_fobis

                # Just parse config; build may fail (no gfortran needed here),
                # but the key is that auto_discover_src is NOT called.
                with contextlib.suppress(SystemExit, Exception):
                    run_fobis(fake_args=["build", "-f", "fobos", "--dry-run"])
            finally:
                os.chdir(prev)

        # auto_discover_src should NOT have been called (src was explicit)
        assert mock_asd.call_count == 0


def test_verbose_output_when_discovered(capsys):
    """When discovery fires, the [auto-discover] message must be printed."""
    with tempfile.TemporaryDirectory() as root:
        _make_fortran_file(os.path.join(root, "src"))
        prog = os.path.join(root, "src", "main.F90")
        with open(prog, "w") as f:
            f.write("program main\nimplicit none\nend program main\n")
        fobos_path = os.path.join(root, "fobos")
        with open(fobos_path, "w") as f:
            f.write("[default]\ncompiler = Gnu\ntarget   = main.F90\noutput   = myprog\nbuild_dir = ./\n")
        prev = os.getcwd()
        os.chdir(root)
        try:
            from fobis.fobis import run_fobis

            with contextlib.suppress(SystemExit, Exception):
                run_fobis(fake_args=["build", "-f", "fobos"])
        finally:
            os.chdir(prev)

    captured = capsys.readouterr()
    assert "[auto-discover]" in captured.out or "[auto-discover]" in captured.err
