"""Tests for the precedence of ``--build-dir``: given on the command line it wins over the mode's ``build_dir`` (as
an explicit ``--target`` does), so a build can go to a scratch directory without touching the mode's build tree;
without it the mode's ``build_dir`` applies as before. Real gfortran builds."""

from __future__ import annotations

import shutil

import pytest

from fobis.fobis import run_fobis

pytestmark = pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran")


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.f90").write_text("program app\nprint *, 1\nend program\n")
    (tmp_path / "fobos").write_text(
        "[modes]\nmodes = gnu\n\n[gnu]\ncompiler = gnu\nsrc = ./src/\nbuild_dir = ./build/\ntarget = src/app.f90\n"
        "cflags = -c\n"
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _run(args, capsys):
    try:
        run_fobis(fake_args=args)
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    capsys.readouterr()
    return code


def test_mode_build_dir_without_the_option(project, capsys):
    assert _run(["build"], capsys) == 0
    assert (project / "build" / "app").is_file()


def test_explicit_build_dir_wins_over_the_mode(project, capsys):
    assert _run(["build", "--build-dir", "scratch"], capsys) == 0
    assert (project / "scratch" / "app").is_file() and (project / "scratch" / "obj" / "app.o").is_file()
    assert not (project / "build").exists()  # the mode's build tree is not touched
    assert _run(["build", "--build_dir", "legacy"], capsys) == 0  # the legacy spelling, normalised
    assert (project / "legacy" / "app").is_file()
    assert _run(["clean", "--build-dir", "scratch"], capsys) == 0
    assert not (project / "scratch" / "obj" / "app.o").exists()


def test_target_outside_the_sources_is_an_error(project, capsys):
    """Before: nothing built, nothing said, exit status 0."""
    (project / "test").mkdir()
    (project / "test" / "other.f90").write_text("program other\nend program\n")
    try:
        run_fobis(fake_args=["build", "--target", "test/other.f90"])
        code = 0
    except SystemExit as exc:
        code = exc.code
    out = capsys.readouterr()
    assert code == 1 and 'the target "test/other.f90" is not among the sources' in out.out + out.err


def test_sources_are_parsed_in_natural_path_order(project):
    """Not the directory listing's order, which differs between file systems (the doctests ran 2 before 1 on one
    machine and 1 before 2 on another)."""
    from fobis.fobis import parse_files
    from fobis.FoBiSConfig import FoBiSConfig

    for name in ("m-10.f90", "m-2.f90", "a.f90"):
        (project / "src" / name).write_text(f"module {name[:-4].replace('-', '_')}\nend module\n")
    names = [p.name for p in parse_files(FoBiSConfig(fake_args=["build"]))]
    assert names == ["src/a.f90", "src/app.f90", "src/m-2.f90", "src/m-10.f90"]


def test_a_c_header_next_to_the_sources_is_read_as_c(project):
    """`.h` is an include extension: the words of a C header's comments became dependencies (``fobis bindings``
    writes one next to the shim). A C header is read as C: its quoted includes only, never compiled."""
    from fobis.fobis import parse_files
    from fobis.FoBiSConfig import FoBiSConfig

    (project / "src" / "api.h").write_text("/* use like the library */\n#include <stdint.h>\nvoid f(int32_t *n);\n")
    (project / "src" / "inc.h").write_text("integer, parameter :: n = 3\n")  # a Fortran include file
    pfiles = {p.name: p for p in parse_files(FoBiSConfig(fake_args=["build"]))}
    api = pfiles["src/api.h"]
    assert api.c_header and api.include and not api.nomodlib and api.dependencies == []
    assert not pfiles["src/inc.h"].c_header
