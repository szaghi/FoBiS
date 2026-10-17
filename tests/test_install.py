"""Tests for FoBiS.py install functionality."""

import shutil

import pytest

from tests.helpers import run_install


@pytest.mark.parametrize("n", range(1, 5))
def test_install(monkeypatch, n):
    """Test install scenario n."""
    assert run_install(monkeypatch, f"install-test{n}"), f"install-test{n} failed"


@pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran")
def test_install_sub_directories(tmp_path, monkeypatch):
    """A mode's include (the build's search directories) used to become install's sub-directory for the module files,
    and the mode's lib won over --lib: --bin/--lib/--include given now win, and the mode's include is never used."""
    from fobis.fobis import run_fobis

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "greet.f90").write_text("module greet\nend module greet\n")
    (tmp_path / "fobos").write_text(
        "[default]\ncompiler = gnu\ncflags = -c\nsrc = ./src/\ninclude = ./src/\nbuild_dir = ./build/\n"
        "target = src/greet.f90\nmklib = static\noutput = libgreet.a\ntrack_build = True\nlib = mylib/\n"
    )
    monkeypatch.chdir(tmp_path)
    run_fobis(fake_args=["build", "--quiet"])
    run_fobis(fake_args=["install", "--prefix", "a"])
    assert (tmp_path / "a" / "include" / "greet.mod").is_file() and not (tmp_path / "a" / "src").exists()
    assert (tmp_path / "a" / "mylib" / "libgreet.a").is_file()  # the mode's lib: an install key
    run_fobis(fake_args=["install", "--prefix", "b", "--lib", "lib64", "--include", "mods"])
    assert (tmp_path / "b" / "lib64" / "libgreet.a").is_file() and (tmp_path / "b" / "mods" / "greet.mod").is_file()


@pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran")
def test_install_copies_every_module_of_the_library(tmp_path, monkeypatch):
    """Only <mod_dir>/<target file stem>.mod was installed: the other modules (and a module named unlike its file)
    were missing, so a program using them could not compile against the installed library."""
    from fobis.fobis import run_fobis

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "kernels.f90").write_text(
        "module Impl_Core\ninteger, parameter :: n = 3\nend module Impl_Core\n"
    )
    (tmp_path / "src" / "api.f90").write_text("module api\nuse impl_core, only : n\nend module api\n")
    (tmp_path / "fobos").write_text(
        "[default]\ncompiler = gnu\ncflags = -c\nsrc = ./src/\nbuild_dir = ./build/\ntarget = src/api.f90\n"
        "mklib = static\noutput = libapi.a\ntrack_build = True\n"
    )
    monkeypatch.chdir(tmp_path)
    run_fobis(fake_args=["build", "--quiet"])
    run_fobis(fake_args=["install", "--prefix", "p"])
    assert sorted(path.name for path in (tmp_path / "p" / "include").iterdir()) == ["api.mod", "impl_core.mod"]
