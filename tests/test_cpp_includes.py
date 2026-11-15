"""Files a preprocessed source pulls in with cpp ``#include`` (issue #212): cpp expands them before the parser reads
the source, so they are found in its linemarkers (``# 1 "src/body.INC" 1``) and matched to the project's files by
path. An edit of one rebuilds the file that includes it (nested includes too, an include under an inactive ``#if``
not); a header found outside the sources through an include directory is no unresolved dependency.
Real cpp + gfortran builds."""

from __future__ import annotations

import json
import os
import shutil
import subprocess

import pytest

from fobis.fobis import run_fobis

pytestmark = pytest.mark.skipif(shutil.which("gfortran") is None or shutil.which("cpp") is None, reason="gfortran, cpp")

MODULE = """module m
implicit none
contains
function f() result(y)
integer :: y
#include "body.INC"
#ifdef NEVER
#include "unused.INC"
#endif
end function
end module m
"""
PROGRAM = "program p\nuse m\nimplicit none\nprint '(I0)', f()\nend program p\n"
FOBOS = """[default]
compiler = gnu
cflags = -c
src = src/
build_dir = build/
target = p.F90
output = p
"""


@pytest.fixture
def project(tmp_path, monkeypatch):
    """The reproducer of #212: ``m.F90`` cpp-includes ``body.INC``, which sits next to it."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "m.F90").write_text(MODULE)
    (tmp_path / "src" / "p.F90").write_text(PROGRAM)
    (tmp_path / "src" / "body.INC").write_text("y = 1\n")
    (tmp_path / "src" / "unused.INC").write_text("y = -1\n")
    (tmp_path / "fobos").write_text(FOBOS)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _fobis(capsys, *args):
    try:
        run_fobis(fake_args=list(args))
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _run(project):
    return subprocess.run([str(project / "build" / "p")], capture_output=True, text=True, check=True).stdout.strip()


def _edit(path, text, newer_than):
    """Write *text* and date the file after *newer_than* (an object): no sleep, no reliance on mtime granularity."""
    path.write_text(text)
    stamp = os.stat(newer_than).st_mtime_ns + 10**9
    os.utime(path, ns=(stamp, stamp))


def test_an_edited_cpp_include_rebuilds_its_includer(project, capsys):
    code, out, _ = _fobis(capsys, "build", "--verbose")
    assert code == 0, out
    assert "-I " not in out  # no include directory derived from the cwd-relative name (an empty -I ate the source)
    assert _run(project) == "1"
    code, out, _ = _fobis(capsys, "build")
    assert code == 0 and "Nothing to compile" in out
    _edit(project / "src" / "body.INC", "y = 2\n", project / "build" / "obj" / "m.o")
    code, out, _ = _fobis(capsys, "build")
    assert code == 0 and "Compiling src/m.F90" in out, out
    assert _run(project) == "2"


def test_an_edited_nested_cpp_include_rebuilds_its_includer(project, capsys):
    (project / "src" / "body.INC").write_text('#include "deep.INC"\n')
    (project / "src" / "deep.INC").write_text("y = 3\n")
    assert _fobis(capsys, "build")[0] == 0
    assert _run(project) == "3"
    _edit(project / "src" / "deep.INC", "y = 4\n", project / "build" / "obj" / "m.o")
    code, out, _ = _fobis(capsys, "build")
    assert code == 0 and "Compiling src/m.F90" in out, out
    assert _run(project) == "4"


def test_an_include_under_an_inactive_if_is_no_dependency(project, capsys):
    assert _fobis(capsys, "build")[0] == 0
    _edit(project / "src" / "unused.INC", "y = -2\n", project / "build" / "obj" / "m.o")
    code, out, _ = _fobis(capsys, "build")
    assert code == 0 and "Nothing to compile" in out, out


def test_a_header_outside_the_sources_is_no_unresolved_dependency(project, capsys):
    vendor = project.parent / (project.name + "-vendor")
    vendor.mkdir()
    (vendor / "answer.h").write_text("integer, parameter :: answer = 42\n")
    (project / "src" / "m.F90").write_text('module m\nimplicit none\n#include "answer.h"\nend module m\n')
    (project / "src" / "p.F90").write_text("program p\nuse m\nimplicit none\nprint '(I0)', answer\nend program p\n")
    (project / "fobos").write_text(FOBOS + f"include = {vendor}\n")
    code, out, err = _fobis(capsys, "build")
    assert code == 0, out
    assert "unreachable" not in out + err
    assert _run(project) == "42"
    code, out, _ = _fobis(capsys, "check", "--json")
    data = json.loads(out)
    assert code == 0 and data["unresolved"] == [], data
