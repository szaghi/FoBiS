"""Volatile libraries (``vlibs``): a change of the library's content recompiles everything. The check crashed with a
traceback before the first build (no build directory for its hash file yet) and when the library was missing; now the
first build works and a missing library is reported, the link failing as for any library. Real gfortran builds."""

from __future__ import annotations

import shutil
import subprocess

import pytest

from fobis.fobis import run_fobis

pytestmark = pytest.mark.skipif(shutil.which("gfortran") is None or shutil.which("ar") is None, reason="tools")

LIBRARY = "module mylib\ncontains\ninteger function value()\nvalue = {n}\nend function value\nend module mylib\n"


def _library(root, n: int) -> None:
    """libmylib.a (and mylib.mod) in root/lib, built from a module whose function returns n."""
    lib = root / "lib"
    lib.mkdir(exist_ok=True)
    (lib / "mylib.f90").write_text(LIBRARY.format(n=n))
    subprocess.run(["gfortran", "-c", "mylib.f90"], cwd=lib, check=True)
    subprocess.run(["ar", "rcs", "libmylib.a", "mylib.o"], cwd=lib, check=True)


@pytest.fixture
def project(tmp_path, monkeypatch):
    _library(tmp_path, 1)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.f90").write_text("program main\nuse mylib\nprint '(I0)', value()\nend program main\n")
    (tmp_path / "fobos").write_text(
        "[default]\ncompiler = gnu\ncflags = -c\nsrc = ./src/\nbuild_dir = ./build/\ninclude = ./lib/\n"
        "vlibs = ./lib/libmylib.a\n"
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _build(capsys) -> tuple[int, str]:
    try:
        run_fobis(fake_args=["build"])
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def _run(project) -> str:
    return subprocess.run([str(project / "build" / "main")], capture_output=True, text=True, check=True).stdout


def test_the_first_build_and_a_changed_library(project, capsys):
    code, out = _build(capsys)
    assert code == 0, out  # no build directory yet: the hash file's directory is created
    assert _run(project).strip() == "1"
    code, out = _build(capsys)
    assert code == 0 and "forcing to (re-)compile all" not in out
    _library(project, 2)
    code, out = _build(capsys)
    assert code == 0 and "is changed with respect the last building: forcing to (re-)compile all" in out
    assert _run(project).strip() == "2"


def test_a_missing_library_is_reported_not_a_traceback(project, capsys):
    (project / "lib" / "libmylib.a").unlink()
    code, out = _build(capsys)
    assert "The volatile library ./lib/libmylib.a is not found!" in out
    assert "Traceback" not in out and code == 1  # the link fails, as for any missing library
