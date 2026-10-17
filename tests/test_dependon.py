"""Tests for ``dependon``: a program built against another FoBiS project's library. The library's mode sets no
``mod_dir`` (the module files are in ``<build_dir>/mod``: before, the include path missed them and the program did not
compile); a change of the library's interface (a newer ``.mod``) recompiles the program's files that use it, a change
of its body only relinks. Real gfortran builds."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran")


@pytest.fixture
def projects(tmp_path):
    lib = tmp_path / "lib"
    (lib / "src").mkdir(parents=True)
    (lib / "src" / "m.f90").write_text(
        "module m\ncontains\ninteger function one()\none = 1\nend function\nend module\n"
    )
    (lib / "fobos").write_text(
        "[modes]\nmodes = static\n\n[static]\ncompiler = gnu\ncflags = -c\nsrc = ./src/\nbuild_dir = ./build/\ntarget = src/m.f90\n"
        "mklib = static\noutput = libm.a\n"
    )
    app = tmp_path / "app"
    (app / "src").mkdir(parents=True)
    (app / "src" / "p.f90").write_text("program p\nuse m\nprint *, one()\nend program\n")
    (app / "fobos").write_text(
        "[default]\ncompiler = gnu\ncflags = -c\nsrc = ./src/\ntarget = src/p.f90\ndependon = ../lib/fobos:static\n"
    )
    return lib, app


def _build(app):
    return subprocess.run(
        [sys.executable, "-m", "fobis", "build", "--quiet"], cwd=app, capture_output=True, text=True, check=False
    )


def _mtime(path):
    return os.stat(path).st_mtime_ns


def test_dependon_finds_the_module_files_and_follows_interface_changes(projects):
    lib, app = projects
    result = _build(app)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "build/mod" in result.stdout  # the include path holds the library's module files
    obj = app / "obj" / "p.o"
    before = _mtime(obj)
    source = lib / "src" / "m.f90"
    source.write_text(source.read_text().replace("one = 1", "one = 2"))  # the body only: the .mod is unchanged
    assert _build(app).returncode == 0 and _mtime(obj) == before
    source.write_text(
        source.read_text().replace("end module", "integer function two()\ntwo = 2\nend function\nend module")
    )
    result = _build(app)  # a new procedure: the interface, and the .mod, changed
    assert result.returncode == 0 and _mtime(obj) > before
    assert "Compiling src/p.f90" in result.stdout


def test_a_dependon_path_is_relative_to_its_fobos(projects, tmp_path):
    """dependon = ../lib/fobos is relative to the fobos that writes it (as a path= dependency), not to the directory
    fobis runs in: building the app from its parent directory used to look for ../lib/fobos next to the parent."""
    lib, app = projects
    (app / "fobos").write_text(  # src is relative to where fobis runs (here the parent), dependon to this fobos
        "[default]\ncompiler = gnu\ncflags = -c\nsrc = ./app/src/\nbuild_dir = ./app/\nobj_dir = ./app/obj/\n"
        "mod_dir = ./app/mod/\ntarget = app/src/p.f90\ndependon = ../lib/fobos:static\n"
    )
    result = subprocess.run(
        [sys.executable, "-m", "fobis", "build", "--quiet", "-f", "app/fobos"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (lib / "build" / "libm.a").is_file() and (app / "p").is_file()
