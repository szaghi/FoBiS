"""Files named alike in several directories (fpm's ``hello_fpm_path``: three ``say_hello.f90``): each gets an object
named after its path, so all are compiled and linked; the other objects keep ``<name>.o``. Real gfortran builds, the
Makefile export and the compilation database."""

from __future__ import annotations

import json
import os
import shutil
import subprocess

import pytest

from fobis.fobis import run_fobis

pytestmark = pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran")

GREETER = "module {m}\nimplicit none\ncontains\nsubroutine hello_{m}()\nprint '(A)', 'hello from {m}'\nend subroutine\nend module {m}\n"
PROGRAM = "program main\nuse one\nuse two\nuse three\ncall hello_one()\ncall hello_two()\ncall hello_three()\nend program main\n"


@pytest.fixture
def project(tmp_path, monkeypatch):
    for folder, module in (("lib/one", "one"), ("lib/two", "two"), ("vendor/three", "three")):
        (tmp_path / folder).mkdir(parents=True)
        (tmp_path / folder / "say_hello.f90").write_text(GREETER.format(m=module))
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.f90").write_text(PROGRAM)
    (tmp_path / "fobos").write_text(
        "[default]\ncompiler = gnu\ncflags = -c\nsrc = ./lib/ ./vendor/ ./app/\nbuild_dir = ./build/\n"
        "target = app/main.f90\n"
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _fobis(capsys, *args):
    try:
        run_fobis(fake_args=list(args))
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def _hello(path):
    return subprocess.run([str(path)], capture_output=True, text=True, check=True).stdout.split("\n")[:3]


def test_files_named_alike_get_objects_of_their_own(project, capsys):
    code, out = _fobis(capsys, "build")
    assert code == 0, out
    assert sorted(os.listdir(project / "build" / "obj")) == [
        ".fobis-compiler.json",
        "lib_one_say_hello.f90.o",
        "lib_two_say_hello.f90.o",
        "main.o",
        "vendor_three_say_hello.f90.o",
    ]
    assert _hello(project / "build" / "main") == ["hello from one", "hello from two", "hello from three"]
    code, out = _fobis(capsys, "build")
    assert code == 0 and "Nothing to compile" in out
    obj = project / "build" / "obj"
    stamp = os.stat(obj / "lib_one_say_hello.f90.o").st_mtime_ns
    os.utime(project / "lib" / "two" / "say_hello.f90", ns=(stamp + 10**9,) * 2)
    code, out = _fobis(capsys, "build")
    assert code == 0 and "Compiling lib/two/say_hello.f90 serially" in out
    assert os.stat(obj / "lib_one_say_hello.f90.o").st_mtime_ns == stamp  # the others are up to date


def test_compilation_database_and_makefile(project, capsys):
    assert _fobis(capsys, "build", "--compile-commands")[0] == 0
    outputs = sorted(os.path.basename(e["output"]) for e in json.loads((project / "compile_commands.json").read_text()))
    assert outputs == ["lib_one_say_hello.f90.o", "lib_two_say_hello.f90.o", "main.o", "vendor_three_say_hello.f90.o"]
    if shutil.which("make") is None:
        pytest.skip("make")
    assert _fobis(capsys, "build", "--makefile", "Makefile")[0] == 0
    assert "$(DOBJ)vendor_three_say_hello.f90.o: vendor/three/say_hello.f90\n" in (project / "Makefile").read_text()
    subprocess.run(["make"], cwd=project, capture_output=True, text=True, check=True)
    assert _hello(project / "build" / "main") == ["hello from one", "hello from two", "hello from three"]


def test_programs_named_alike(tmp_path, monkeypatch, capsys):
    """Two programs in files named alike: their objects differ, a warning says their executables would not."""
    for folder, word in (("a", "first"), ("b", "second")):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "main.f90").write_text(f"program main\nprint '(A)', '{word}'\nend program main\n")
    (tmp_path / "fobos").write_text("[default]\ncompiler = gnu\ncflags = -c\nsrc = ./a/ ./b/\nbuild_dir = ./build/\n")
    monkeypatch.chdir(tmp_path)
    code, out = _fobis(capsys, "build", "--target", "a/main.f90", "--output", "first")
    assert code == 0 and "programs a/main.f90, b/main.f90 are named alike" in out
    assert _fobis(capsys, "build", "--target", "b/main.f90", "--output", "second")[0] == 0
    run = [
        subprocess.run([str(tmp_path / "build" / n)], capture_output=True, text=True, check=True).stdout.strip()
        for n in ("first", "second")
    ]
    assert run == ["first", "second"]
