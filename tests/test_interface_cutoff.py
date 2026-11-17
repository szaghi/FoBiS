"""The recompile cutoff at unchanged module interfaces (issue #218, phase 4)."""

from __future__ import annotations

import shutil
import subprocess
import time

import pytest

from fobis.fobis import run_fobis
from fobis.interfaces import module_digest, unsupported_reason

A = "module a\nimplicit none\ninteger, parameter :: k = 1\ncontains\nsubroutine say()\nprint *, 'one'\nend subroutine\nend module a\n"
B = "module b\nuse a\nimplicit none\ncontains\nsubroutine twice()\ncall say()\ncall say()\nend subroutine\nend module b\n"
C = "module c\nuse b\nimplicit none\ncontains\nsubroutine run()\ncall twice()\nend subroutine\nend module c\n"
P = "program p\nuse c\nuse a, only : k\ncall run()\nprint *, k\nend program p\n"

COMPILERS = [
    pytest.param("gnu", "gfortran", marks=pytest.mark.skipif(not shutil.which("gfortran"), reason="no gfortran")),
    pytest.param(
        "nvfortran", "nvfortran", marks=pytest.mark.skipif(not shutil.which("nvfortran"), reason="no nvfortran")
    ),
]


def _project(root):
    src = root / "src"
    src.mkdir()
    for name, text in {"a.f90": A, "b.f90": B, "c.f90": C, "p.f90": P}.items():
        (src / name).write_text(text)
    return src


def _edit(path, old, new):
    time.sleep(0.05)  # newer than the objects (a future mtime would make the file compile on every build)
    path.write_text(path.read_text().replace(old, new))


def _build(capsys, compiler, *extra):
    run_fobis(fake_args=["build", "--src", "src", "--target", "p.f90", "--compiler", compiler, "-j", "2", *extra])
    out = capsys.readouterr().out
    return sorted(line.split()[1] for line in out.splitlines() if line.startswith("Compiling src/")), out


def _run(root):
    return subprocess.run([str(root / "p")], capture_output=True, text=True, check=True).stdout.split()


@pytest.mark.parametrize(("compiler", "command"), COMPILERS)
def test_a_body_edit_compiles_one_file(tmp_path, monkeypatch, capsys, compiler, command):
    src = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    compiled, _ = _build(capsys, compiler, "--interface-cutoff")
    assert compiled == ["src/a.f90", "src/b.f90", "src/c.f90", "src/p.f90"]
    _edit(src / "a.f90", "'one'", "'uno'")
    compiled, out = _build(capsys, compiler, "--interface-cutoff")
    assert compiled == ["src/a.f90"]
    assert "interface_cutoff: 3 file(s) not compiled again" in out
    assert _run(tmp_path) == ["uno", "uno", "1"]
    compiled, out = _build(capsys, compiler, "--interface-cutoff")
    assert compiled == []
    assert "link skipped" in out


@pytest.mark.parametrize(("compiler", "command"), COMPILERS)
def test_an_interface_edit_compiles_the_dependents(tmp_path, monkeypatch, capsys, compiler, command):
    src = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    _build(capsys, compiler, "--interface-cutoff")
    _edit(src / "a.f90", "integer, parameter :: k = 1", "integer, parameter :: k = 7")  # a parameter's value
    compiled, _ = _build(capsys, compiler, "--interface-cutoff")
    assert compiled == ["src/a.f90", "src/b.f90", "src/c.f90", "src/p.f90"]
    assert _run(tmp_path) == ["one", "one", "7"]
    _edit(src / "b.f90", "subroutine twice()", "subroutine twice(n)\ninteger, optional :: n")  # a signature
    compiled, _ = _build(capsys, compiler, "--interface-cutoff")
    # p uses c, which uses b: its closure holds b, whose interface changed (conservative: an nvfortran .mod refers
    # to the modules it uses by name, so a change two modules down does not show in the module in between)
    assert compiled == ["src/b.f90", "src/c.f90", "src/p.f90"]


@pytest.mark.skipif(not shutil.which("gfortran"), reason="no gfortran")
def test_without_the_option_every_dependent_compiles(tmp_path, monkeypatch, capsys):
    src = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    _build(capsys, "gnu")
    _edit(src / "a.f90", "'one'", "'uno'")
    compiled, _ = _build(capsys, "gnu")
    assert compiled == ["src/a.f90", "src/b.f90", "src/c.f90", "src/p.f90"]


def test_unsupported():
    assert unsupported_reason("intel", "-c") and "not measured" in unsupported_reason("intel", "-c")
    assert "off with -flto" in unsupported_reason("gnu", "-c -O2 -flto")
    assert "off with -Mipa=fast" in unsupported_reason("nvfortran", "-c -Mipa=fast")
    assert unsupported_reason("nvfortran", "-c -fast -acc -gpu=cc89,lto") is None  # device LTO: at the link


def test_nvfortran_digest_ignores_the_date(tmp_path):
    one, two = tmp_path / "one.mod", tmp_path / "two.mod"
    one.write_text("V35 :0x24 m\n5 m.f90 S624 0\n11/16/2026  21:10:38\nuse x private\n")
    two.write_text("V35 :0x24 m\n5 m.f90 S624 0\n11/16/2026  23:59:01\nuse x private\n")
    assert module_digest(str(one), "nvfortran") == module_digest(str(two), "nvfortran")
    assert module_digest(str(one), "gnu") != module_digest(str(two), "gnu")
