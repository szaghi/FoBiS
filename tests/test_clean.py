"""Tests for FoBiS.py clean functionality."""

import shutil

import pytest

from tests.helpers import run_clean


@pytest.mark.parametrize("n", range(1, 2))
def test_clean(monkeypatch, n):
    """Test clean scenario n."""
    assert run_clean(monkeypatch, f"clean-test{n}"), f"clean-test{n} failed"


@pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran")
def test_clean_removes_the_build_log(tmp_path, monkeypatch):
    """The log of build --log is written in the build directory, but clean looked for it in the current one."""
    from fobis.fobis import run_fobis

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.f90").write_text("program main\nend program main\n")
    (tmp_path / "fobos").write_text(
        "[default]\ncompiler = gnu\ncflags = -c\nsrc = ./src/\nbuild_dir = ./build/\ntarget = src/main.f90\nlog = True\n"
    )
    monkeypatch.chdir(tmp_path)
    run_fobis(fake_args=["build", "--quiet"])
    assert (tmp_path / "build" / "build_main.log").is_file()
    run_fobis(fake_args=["clean"])
    assert not (tmp_path / "build" / "build_main.log").exists() and not (tmp_path / "build" / "main").exists()
