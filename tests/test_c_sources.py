"""C sources among the Fortran ones (issue #206 step 6): compiled with the family's C compiler, linked like files that
define no module (every program, every library), rebuilt when a project header changes; the Makefile export, the
compilation database, the compiler guard, ``build --json`` diagnostics and ``introspect`` cover them; lint skips them.
Real gcc + gfortran builds; nvfortran + nvc and ifx + icx when they are on PATH."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from argparse import Namespace

import pytest

from fobis.ai.diagnostics import parse_diagnostics
from fobis.Compiler import C_COMPILERS, Compiler
from fobis.fobis import COMPILER_RECORD, run_fobis

pytestmark = pytest.mark.skipif(
    shutil.which("gfortran") is None or shutil.which("gcc") is None, reason="gfortran and gcc"
)

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build-explain")

HEADER = "/* the scale of the project */\n#define SCALE 2.0\ndouble c_twice(double x);\n"
C_SOURCE = '#include <stdio.h>\n#include "clock.h"\ndouble c_twice(double x) { return SCALE * x; }\n'
INTERFACE = """module timer
use iso_c_binding, only: c_double
implicit none
interface
  function c_twice(x) bind(c, name="c_twice") result(y)
    import :: c_double
    real(c_double), value :: x
    real(c_double) :: y
  end function
end interface
end module
"""
PROGRAM = "program main\nuse timer\nimplicit none\nprint '(F4.1)', c_twice(1.5d0)\nend program\n"
FOBOS = """[modes]
modes = default static shared

[default]
compiler = gnu
cflags = -c -O2
src = src
build_dir = build

[static]
compiler = gnu
cflags = -c
src = src
build_dir = lib-static
target = timer.f90
mklib = static

[shared]
compiler = gnu
cflags = -c -fPIC
c_cflags = -c -fPIC
src = src
build_dir = lib-shared
target = timer.f90
mklib = shared
"""


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A Fortran program calling a C function through bind(c); the C file includes a project header in its own
    directory, and ``timer.f90`` sits next to ``timer.c`` (objects ``timer.o`` and ``timer.c.o``)."""
    (tmp_path / "src" / "csrc").mkdir(parents=True)
    (tmp_path / "src" / "csrc" / "clock.h").write_text(HEADER)
    (tmp_path / "src" / "csrc" / "timer.c").write_text(C_SOURCE)
    (tmp_path / "src" / "timer.f90").write_text(INTERFACE)
    (tmp_path / "src" / "main.f90").write_text(PROGRAM)
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


def _run(path):
    return subprocess.run([str(path)], capture_output=True, text=True, check=True).stdout.strip()


def test_a_fortran_program_calls_a_c_function(project, capsys):
    code, out, _ = _fobis(capsys, "build", "--mode", "default")
    assert code == 0, out
    assert _run(project / "build" / "main") == "3.0"
    assert sorted(os.listdir(project / "build" / "obj")) == [COMPILER_RECORD, "main.o", "timer.c.o", "timer.o"]


def test_a_changed_header_recompiles_the_c_file_only(project, capsys):
    assert _fobis(capsys, "build", "--mode", "default")[0] == 0
    obj = project / "build" / "obj"
    stamps = {name: os.stat(obj / name).st_mtime_ns for name in ("timer.c.o", "timer.o", "main.o")}
    code, out, _ = _fobis(capsys, "build", "--mode", "default")
    assert code == 0 and "Compiling src/" not in out
    header = project / "src" / "csrc" / "clock.h"
    os.utime(header, ns=(stamps["timer.c.o"] + 10**9,) * 2)
    code, out, _ = _fobis(capsys, "build", "--mode", "default")
    assert code == 0 and "Compiling src/csrc/timer.c" in out
    assert os.stat(obj / "timer.c.o").st_mtime_ns > stamps["timer.c.o"]
    assert all(os.stat(obj / n).st_mtime_ns == stamps[n] for n in ("timer.o", "main.o"))


def test_an_include_with_a_directory(project, capsys):
    """``#include "csrc/clock.h"`` from src/: the header is found by its path tail, and src/ is the include dir."""
    (project / "src" / "csrc" / "timer.c").unlink()
    (project / "src" / "timer.c").write_text(C_SOURCE.replace('"clock.h"', '"csrc/clock.h"'))
    code, out, _ = _fobis(capsys, "build", "--mode", "default")
    assert code == 0 and "unreachable" not in out, out
    assert _run(project / "build" / "main") == "3.0"


@pytest.mark.skipif(shutil.which("nm") is None, reason="nm")
@pytest.mark.parametrize(("mode", "library", "options"), [("static", "timer.a", []), ("shared", "timer.so", ["-D"])])
def test_libraries_hold_the_c_object(project, capsys, mode, library, options):
    code, out, _ = _fobis(capsys, "build", "--mode", mode)
    assert code == 0, out
    symbols = subprocess.run(
        ["nm", *options, str(project / f"lib-{mode}" / library)], capture_output=True, text=True, check=True
    ).stdout
    assert any(line.endswith(" T c_twice") for line in symbols.splitlines()), symbols


def test_compilation_database_has_the_c_entry(project, capsys):
    assert _fobis(capsys, "build", "--mode", "default", "--compile-commands")[0] == 0
    entries = {os.path.basename(e["file"]): e for e in json.loads((project / "compile_commands.json").read_text())}
    entry = entries["timer.c"]
    assert entry["arguments"][:2] == ["gcc", "-c"] and "-Isrc/csrc" in entry["arguments"]
    assert entry["output"].endswith(os.path.join("build", "obj", "timer.c.o"))
    assert entries["main.f90"]["arguments"][0] == "gfortran"


@pytest.mark.skipif(shutil.which("make") is None, reason="make")
def test_the_makefile_builds_the_same_program(project, capsys):
    assert _fobis(capsys, "build", "--mode", "default", "--makefile", "Makefile")[0] == 0
    text = (project / "Makefile").read_text()
    assert "CC      = gcc\n" in text and "$(DOBJ)timer.c.o: src/csrc/timer.c src/csrc/clock.h\n" in text
    subprocess.run(["make"], cwd=project, capture_output=True, text=True, check=True)
    assert _run(project / "build" / "main") == "3.0"


def test_a_c_compile_error_is_a_located_diagnostic(project, capsys):
    (project / "src" / "csrc" / "timer.c").write_text(C_SOURCE.replace("SCALE * x", "SCALE * y"))
    code, out, _ = _fobis(capsys, "build", "--mode", "default", "--json")
    document = json.loads(out)
    assert code == 1 and document["status"] == "error"
    error = document["diagnostics"][0]
    assert (error["tool"], error["severity"], error["file"], error["line"]) == ("c", "error", "src/csrc/timer.c", 3)
    assert "y" in error["message"]


def test_explain_leaves_a_c_error_to_the_c_compiler(project, capsys):
    (project / "src" / "csrc" / "timer.c").write_text(C_SOURCE.replace("SCALE * x", "SCALE * y"))
    code, out, err = _fobis(capsys, "build", "--mode", "default", "--explain-context")
    assert code == 1 and "the first error is in a C source" in out + err
    assert "=== system prompt ===" not in out + err


def test_a_c_file_that_does_not_compile_fails_the_build(project, capsys):
    """Fortran files without modules that fail are dropped from the link with a warning (FoBiS's old rule); a C file
    is never optional."""
    (project / "src" / "csrc" / "timer.c").write_text("this is not C\n")
    code, _, _ = _fobis(capsys, "build", "--mode", "default")
    assert code == 1 and not (project / "build" / "main").exists()


def test_a_missing_c_compiler_is_an_error_not_a_traceback(project, capsys):
    code, out, _ = _fobis(capsys, "build", "--mode", "default", "--cc", "no-such-cc")
    assert code == 1 and "no-such-cc: command not found" in out


def test_the_c_compiler_change_rebuilds(project, capsys, monkeypatch):
    assert _fobis(capsys, "build", "--mode", "default")[0] == 0
    record = json.loads((project / "build" / "obj" / COMPILER_RECORD).read_text())
    assert record["c_command"] == "gcc" and record["c_version"].startswith("gcc")
    real = shutil.which("gcc")
    wrapper = project / "toolchain" / "gcc"
    wrapper.parent.mkdir()
    wrapper.write_text(f'#!/bin/sh\n[ "$1" = --version ] && {{ echo "gcc 99.1.0"; exit 0; }}\nexec {real} "$@"\n')
    wrapper.chmod(0o755)
    monkeypatch.setenv("PATH", f"{wrapper.parent}{os.pathsep}{os.environ['PATH']}")
    code, out, _ = _fobis(capsys, "build", "--mode", "default")
    assert code == 0 and "c_version 'gcc" in out and "'gcc 99.1.0'" in out


def test_a_record_without_the_c_compiler_forces_nothing(project, capsys):
    """Objects of a FoBiS before C sources: the record has no ``c_*`` keys, and no rebuild follows."""
    assert _fobis(capsys, "build", "--mode", "default")[0] == 0
    path = project / "build" / "obj" / COMPILER_RECORD
    record = {k: v for k, v in json.loads(path.read_text()).items() if not k.startswith("c_")}
    path.write_text(json.dumps(record))
    code, out, _ = _fobis(capsys, "build", "--mode", "default")
    assert code == 0 and "Compiling src/" not in out


def _compiler(**fields):
    defaults = {
        "compiler": "gnu",
        "fc": None,
        "cflags": None,
        "lflags": None,
        "preproc": None,
        "modsw": None,
        "mpi": False,
        "openmp": False,
        "openmp_offload": False,
        "coarray": False,
        "coverage": False,
        "profile": False,
        "mklib": None,
    }
    return Compiler(Namespace(**{**defaults, **fields}))


def test_c_settings():
    plain = _compiler()
    assert (plain.ccs, plain.c_cflags, plain.c_explicit) == ("gcc", "-c", False)
    assert _compiler(compiler="nvfortran").ccs == "nvc"
    assert _compiler(compiler="intel_nextgen", mpi=True).ccs == "mpiicx"
    assert _compiler(compiler="nag").ccs == "gcc"  # nag renames itself gnu: the family is read before
    assert _compiler(mpi=True).ccs == "mpicc"
    flags = _compiler(c_cflags="-O3", c_preproc="-DFAST", openmp=True, cflags="-c -fcheck=all")
    assert flags.c_cflags == "-c -O3 -fopenmp -DFAST" and flags.c_explicit  # -c added; the Fortran cflags never
    assert _compiler(cc="clang").ccs == "clang"
    profiled = _compiler(c_profile_cflags="-O0 -g", c_cflags="-c -O2")
    assert profiled.c_cflags == "-O0 -g -c -O2" and profiled.c_explicit  # the profile's first: the mode's win
    assert not _compiler(c_profile_cflags="-O0 -g").c_explicit
    assert set(C_COMPILERS) >= set(Compiler.supported)


def test_mode_keys_and_build_profile(project, capsys):
    (project / "fobos").write_text(
        "[default]\ncompiler = gnu\nsrc = src\nbuild_dir = build\nbuild_profile = debug\nc_preproc = -DSCALE=3.0\n"
    )
    (project / "src" / "csrc" / "clock.h").write_text("double c_twice(double x);\n")
    (project / "src" / "csrc" / "timer.c").write_text(
        '#include "clock.h"\ndouble c_twice(double x) { return SCALE * x; }\n'
    )
    code, out, _ = _fobis(capsys, "build", "--verbose")
    assert code == 0, out
    assert "gcc -O0 -g -Wall -Wextra -c -DSCALE=3.0 -Isrc/csrc src/csrc/timer.c" in out
    assert _run(project / "build" / "main") == "4.5"


def test_introspect_shows_the_c_compiler_and_files(project, capsys):
    code, out, _ = _fobis(capsys, "introspect", "--mode", "shared", "--compiler", "--sources")
    data = json.loads(out)
    assert code == 0 and (data["compiler"]["cc"], data["compiler"]["c_cflags"]) == ("gcc", "-c -fPIC")
    languages = {os.path.basename(s["file"]): s["language"] for s in data["sources"]}
    assert languages == {"clock.h": "c", "timer.c": "c", "main.f90": "fortran", "timer.f90": "fortran"}


def test_lint_skips_c_sources(project):
    from fobis.lint import discover_files

    files = discover_files([str(project / "src")], extensions=[".f90", ".c"])
    assert sorted(os.path.basename(f) for f in files) == ["main.f90", "timer.f90"]
    assert discover_files([str(project / "src" / "csrc" / "timer.c")], extensions=[".c"]) == []


def test_c_diagnostics_of_genuine_compilers():
    """gcc 16, icx 2026.1 (Clang) and nvc 26.5 (EDG) on ``c_error.c``: an undeclared name, an unused variable."""

    def parsed(name):
        with open(os.path.join(FIXTURE, name), encoding="utf-8") as handle:
            return parse_diagnostics(handle.read())

    def summary(name):
        return [(d.tool, d.severity, d.file, d.line, d.column) for d in parsed(name)]

    assert summary("c-gcc.txt") == [
        ("c", "error", "c_error.c", 3, 41),
        ("c", "info", "c_error.c", 3, 41),
        ("c", "warning", "c_error.c", 2, 12),
    ]
    assert summary("c-icx.txt") == [("c", "error", "c_error.c", 3, 41)]
    assert summary("c-nvc.txt") == [("c", "error", "c_error.c", 3, None), ("c", "warning", "c_error.c", 2, None)]
    first = parsed("c-nvc.txt")[0]
    assert first.message == 'identifier "y" is undefined' and "return 2.0 * y" in first.text


@pytest.mark.parametrize(
    ("compiler", "fortran", "c"), [("nvfortran", "nvfortran", "nvc"), ("intel_nextgen", "ifx", "icx")]
)
def test_other_compiler_families(project, capsys, compiler, fortran, c):
    if shutil.which(fortran) is None or shutil.which(c) is None:
        pytest.skip(f"{fortran} and {c} not on PATH")
    (project / "fobos").write_text(f"[default]\ncompiler = {compiler}\ncflags = -c -O2\nsrc = src\nbuild_dir = build\n")
    code, out, _ = _fobis(capsys, "build", "--verbose")
    assert code == 0 and f"('{c} -c -Isrc/csrc src/csrc/timer.c" in out, out
    assert _run(project / "build" / "main") == "3.0"
