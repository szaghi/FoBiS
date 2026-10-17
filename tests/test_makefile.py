"""Tests for FoBiS.py Makefile generation."""

import shutil
import subprocess

import pytest

from tests.helpers import make_makefile


@pytest.mark.parametrize("n", range(1, 3))
def test_makefile(monkeypatch, n):
    """Test Makefile generation scenario n."""
    assert make_makefile(monkeypatch, f"makefile-test{n}"), f"makefile-test{n} failed"


@pytest.mark.skipif(not all(shutil.which(tool) for tool in ("gfortran", "make", "nm")), reason="tools")
@pytest.mark.parametrize(("mklib", "output"), [("static", "libgreet.a"), ("shared", "libgreet.so")])
def test_a_library_mode_exports_a_library_rule(tmp_path, monkeypatch, mklib, output):
    """A library mode was exported with a program link rule: make failed with undefined reference to 'main'."""
    from fobis.fobis import run_fobis

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "greet.f90").write_text(
        "module greet\ncontains\nsubroutine hello()\nprint '(A)', 'hello'\nend subroutine hello\nend module greet\n"
    )
    shared = " -fPIC" if mklib == "shared" else ""
    (tmp_path / "fobos").write_text(
        f"[default]\ncompiler = gnu\ncflags = -c{shared}\nsrc = ./src/\nbuild_dir = ./build/\n"
        f"target = src/greet.f90\nmklib = {mklib}\noutput = {output}\n"
    )
    monkeypatch.chdir(tmp_path)
    run_fobis(fake_args=["build", "--quiet", "--makefile", "Makefile"])
    subprocess.run(["make"], cwd=tmp_path, capture_output=True, text=True, check=True)
    symbols = subprocess.run(["nm", str(tmp_path / "build" / output)], capture_output=True, text=True, check=True)
    assert "__greet_MOD_hello" in symbols.stdout
