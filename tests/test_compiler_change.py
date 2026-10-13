"""Tests for the compiler-change guard of ``fobis build``: when the compiler behind the mode's command changes (a
module swap keeps the name ``gfortran`` but changes its path and ``--version``), the next build recompiles
everything instead of linking objects of two compilers; the record is written only after a build that compiled
without failure, and a missing record (first build, objects of an older FoBiS) forces nothing."""

from __future__ import annotations

import json
import os
import shutil

import pytest

from fobis.fobis import COMPILER_RECORD, run_fobis

pytestmark = pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran")


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "m.f90").write_text(
        "module m\ncontains\nsubroutine hello()\nprint *, 'hi'\nend subroutine\nend module\n"
    )
    (tmp_path / "src" / "app.f90").write_text("program app\nuse m\ncall hello()\nend program\n")
    (tmp_path / "fobos").write_text(
        "[default]\ncompiler = gnu\nsrc = ./src/\nbuild_dir = ./build/\ntarget = src/app.f90\ncflags = -c\n"
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _build(capsys):
    try:
        run_fobis(fake_args=["build"])
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def _mtime(project):
    return os.stat(project / "build" / "obj" / "m.o").st_mtime_ns


def _swap_compiler(project, monkeypatch, version):
    """A ``gfortran`` earlier on PATH: the real compiler, another ``--version`` (as after a module swap)."""
    real = shutil.which("gfortran")
    wrapper = project / "toolchain" / "gfortran"
    wrapper.parent.mkdir(exist_ok=True)
    wrapper.write_text(
        f'#!/bin/sh\n[ "$1" = --version ] && {{ echo "GNU Fortran {version}"; exit 0; }}\nexec {real} "$@"\n'
    )
    wrapper.chmod(0o755)
    monkeypatch.setenv("PATH", f"{wrapper.parent}{os.pathsep}{os.environ['PATH']}")


def test_unchanged_compiler_rebuilds_nothing(project, capsys):
    assert _build(capsys)[0] == 0
    record = json.loads((project / "build" / "obj" / COMPILER_RECORD).read_text())
    assert record["command"] == "gfortran" and record["version"].startswith("GNU Fortran")
    before = _mtime(project)
    code, out = _build(capsys)
    assert code == 0 and _mtime(project) == before and "compiler changed" not in out


def test_changed_compiler_rebuilds_everything_once(project, capsys, monkeypatch):
    assert _build(capsys)[0] == 0
    before = _mtime(project)
    _swap_compiler(project, monkeypatch, "99.1.0")
    code, out = _build(capsys)
    assert code == 0 and "The compiler changed since the last build" in out and "99.1.0" in out
    assert _mtime(project) > before
    record = json.loads((project / "build" / "obj" / COMPILER_RECORD).read_text())
    assert record["version"] == "GNU Fortran 99.1.0" and record["path"] == str(project / "toolchain" / "gfortran")
    after = _mtime(project)
    code, out = _build(capsys)
    assert code == 0 and _mtime(project) == after and "compiler changed" not in out


def test_no_record_forces_nothing(project, capsys):
    assert _build(capsys)[0] == 0
    (project / "build" / "obj" / COMPILER_RECORD).unlink()  # objects built by an older FoBiS
    before = _mtime(project)
    code, out = _build(capsys)
    assert "compiler changed" not in out
    assert code == 0 and _mtime(project) == before and (project / "build" / "obj" / COMPILER_RECORD).exists()


def test_failed_build_keeps_the_rebuild_pending(project, capsys, monkeypatch):
    assert _build(capsys)[0] == 0
    _swap_compiler(project, monkeypatch, "99.2.0")
    (project / "src" / "app.f90").write_text("program app\nuse m\ncall hello(\nend program\n")  # a syntax error
    code, out = _build(capsys)
    assert code != 0 and "99.2.0" in out
    record = json.loads((project / "build" / "obj" / COMPILER_RECORD).read_text())
    assert record["version"] != "GNU Fortran 99.2.0"  # not written: the next build is forced again
    (project / "src" / "app.f90").write_text("program app\nuse m\ncall hello()\nend program\n")
    code, out = _build(capsys)
    assert code == 0 and "The compiler changed since the last build" in out
