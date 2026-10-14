"""The compilation database ``compile_commands.json`` written by every build: one entry per compiled source with
the command the build runs, linked from the project root, never written over a file that is not FoBiS's, and
printed without compiling by ``fobis introspect --compile-commands``. Real gfortran builds."""

from __future__ import annotations

import json
import os
import shlex
import shutil

import pytest

from fobis import compile_commands
from fobis.fobis import run_fobis

pytestmark = pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran")

MODULE = 'module a\ninclude "k.inc"\ncontains\nsubroutine s\nprint *, K\nend subroutine s\nend module a\n'
FOBOS = (
    "[modes]\nmodes = gnu other\n\n"
    "[gnu]\ncompiler = gnu\nsrc = ./src/\nbuild_dir = ./build/\ncflags = -c -O1\npreproc = -DFOO=2\n"
    "compile_commands = True\n\n"
    "[other]\ncompiler = gnu\nsrc = ./src/\nbuild_dir = ./other/\ncflags = -c -O0\ncompile_commands = True\n"
)


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A module including a file from another directory, a program using it, two modes."""
    (tmp_path / "src" / "inc").mkdir(parents=True)
    (tmp_path / "src" / "a.F90").write_text(MODULE)
    (tmp_path / "src" / "inc" / "k.inc").write_text("integer, parameter :: K = 3\n")
    (tmp_path / "src" / "p.f90").write_text("program p\nuse a\ncall s\nend program p\n")
    (tmp_path / "fobos").write_text(FOBOS)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _run(args, capsys) -> tuple[int, str]:
    try:
        run_fobis(fake_args=args)
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    return code, capsys.readouterr().out


def _database(path) -> list[dict]:
    return json.loads(path.read_text())


def test_one_entry_per_compiled_source_with_the_command_the_build_runs(project, capsys):
    code, out = _run(["build", "--verbose"], capsys)
    assert code == 0
    database = _database(project / "build" / "compile_commands.json")
    root = str(project)
    assert [e["file"] for e in database] == [f"{root}/src/a.F90", f"{root}/src/p.f90"]  # no entry for k.inc
    for item in database:
        assert item["directory"] == root
        assert item["output"] == f"{root}/build/obj/{os.path.splitext(os.path.basename(item['file']))[0]}.o"
        assert f"('{shlex.join(item['arguments'])}', None)" in out  # the command the build executed
        assert {"-O1", "-DFOO=2", "-Isrc/inc"} <= set(item["arguments"])


def test_the_root_links_to_the_build_directory(project, capsys):
    assert _run(["build"], capsys)[0] == 0
    link = project / "compile_commands.json"
    assert link.is_symlink() and os.readlink(link) == os.path.join("build", "compile_commands.json")
    assert _run(["build", "--mode", "other"], capsys)[0] == 0  # another mode: the root follows the last build
    assert os.readlink(link) == os.path.join("other", "compile_commands.json")
    assert "-O0" in _database(link)[0]["arguments"]


def test_complete_after_an_incremental_build_and_rewritten_only_on_change(project, capsys):
    assert _run(["build"], capsys)[0] == 0
    path = project / "build" / "compile_commands.json"
    first, stamp = path.read_text(), path.stat().st_mtime_ns
    os.utime(project / "src" / "p.f90")  # one file to compile again
    code, out = _run(["build", "--verbose"], capsys)
    assert code == 0 and "src/a.F90 -o" not in out  # a.F90 was not compiled ...
    assert path.read_text() == first and path.stat().st_mtime_ns == stamp  # ... and still has its entry, file kept
    assert _run(["build", "--cflags", "-g"], capsys)[0] == 0  # flags appended: rewritten
    assert all("-g" in e["arguments"] for e in _database(path))


def test_opt_in(project, capsys):
    """Off unless asked: a new file in the root of every project would make clean-tree checks fail."""
    (project / "fobos").write_text(FOBOS.replace("compile_commands = True\n", ""))
    assert _run(["build"], capsys)[0] == 0
    assert not (project / "build" / "compile_commands.json").exists()
    assert not os.path.lexists(project / "compile_commands.json")
    assert _run(["build", "--compile-commands"], capsys)[0] == 0
    assert (project / "build" / "compile_commands.json").is_file()
    (project / "fobos").write_text(FOBOS.replace("compile_commands = True\n", "compile_commands = False\n"))
    assert _run(["clean"], capsys)[0] == 0
    assert _run(["build", "--compile-commands"], capsys)[0] == 0  # a mode key replaces the command line's value
    assert not (project / "build" / "compile_commands.json").exists()


def test_a_shadow_build_keeps_its_database_apart(project, capsys):
    assert _run(["build"], capsys)[0] == 0
    assert _run(["build", "--shadow", "checks"], capsys)[0] == 0
    shadow = project / ".fobis" / "shadow" / "gnu-checks" / "compile_commands.json"
    assert "-fcheck=all" in _database(shadow)[0]["arguments"]
    assert os.readlink(project / "compile_commands.json") == os.path.join("build", "compile_commands.json")


def test_a_file_of_the_user_is_never_replaced(project, capsys):
    mine = project / "compile_commands.json"
    mine.write_text('[{"directory": "/elsewhere", "file": "x.f90", "arguments": []}]\n')
    code, out = _run(["build"], capsys)
    assert code == 0 and "left untouched" in out
    assert json.loads(mine.read_text())[0]["directory"] == "/elsewhere"
    assert (project / "build" / "compile_commands.json").is_file()


def test_a_copy_where_links_are_unavailable_is_refreshed(project, capsys, monkeypatch):
    def no_links(*args, **kwargs):
        raise OSError("links unavailable")

    monkeypatch.setattr(os, "symlink", no_links)
    assert _run(["build"], capsys)[0] == 0
    copy = project / "compile_commands.json"
    assert not copy.is_symlink() and copy.read_text() == (project / "build" / "compile_commands.json").read_text()
    assert _run(["build", "--mode", "other"], capsys)[0] == 0  # FoBiS's own copy: replaced
    assert "-O0" in _database(copy)[0]["arguments"]


def test_a_separate_preprocessor_names_the_original_source(project, capsys, monkeypatch):
    tools = project / "tools"
    tools.mkdir()
    stub = tools / "mypp"
    stub.write_text('#!/bin/sh\ncp "$1" "$3"\n')  # mypp SOURCE -o OUTPUT
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tools}{os.pathsep}{os.environ['PATH']}")
    assert _run(["build", "--preprocessor", "mypp"], capsys)[0] == 0
    database = _database(project / "build" / "compile_commands.json")
    for item in database:
        source = os.path.relpath(item["file"], project)
        assert source in item["arguments"] and not any(w.endswith(".pp.f90") for w in item["arguments"])


def test_targets_of_one_run_share_the_database(project, capsys):
    (project / "src" / "q.f90").write_text("program q\nuse a\ncall s\nend program q\n")
    (project / "fobos").write_text(
        FOBOS + "\n[target.p]\nsource = src/p.f90\n\n[target.q]\nsource = src/q.f90\ncflags = -c -O2\n"
    )
    assert _run(["build"], capsys)[0] == 0
    database = _database(project / "build" / "compile_commands.json")
    flags = {(os.path.basename(e["file"]), "-O2" in e["arguments"]) for e in database}
    assert {("q.f90", True), ("p.f90", False)} <= flags  # each target's flags, all in one file


def test_introspect_prints_it_and_compiles_nothing(project, capsys):
    code, out = _run(["introspect", "--compile-commands", "--mode", "other"], capsys)
    assert code == 0
    printed = json.loads(out)
    assert [os.path.basename(e["file"]) for e in printed] == ["a.F90", "p.f90"] and "-O0" in printed[0]["arguments"]
    written = [p for p in (project / "other").rglob("*") if p.is_file()] if (project / "other").exists() else []
    assert written == []  # no object, no database (the Builder only creates its empty directories)
    assert _run(["build", "--mode", "other"], capsys)[0] == 0
    assert printed == _database(project / "other" / "compile_commands.json")
    code, _ = _run(["introspect", "--compile-commands", "--sources"], capsys)
    assert code == 2


def test_written_before_compiling(project, capsys):
    (project / "src" / "p.f90").write_text("program p\nuse a\ncall s(\nend program p\n")  # a syntax error
    assert _run(["build"], capsys)[0] == 1
    assert len(_database(project / "build" / "compile_commands.json")) == 2


def test_link_root_unit(tmp_path):
    build = tmp_path / "build"
    build.mkdir()
    database = build / compile_commands.NAME
    compile_commands.write(str(database), [{"directory": str(tmp_path), "file": "a.f90", "arguments": []}])
    assert compile_commands.link_root(str(database), str(tmp_path)) == str(tmp_path / compile_commands.NAME)
    assert compile_commands.link_root(str(database), str(tmp_path))  # idempotent
    same = tmp_path / "x" / compile_commands.NAME
    assert compile_commands.link_root(str(same), str(tmp_path / "x")) == str(same)  # the root itself: nothing to do


def test_clean_removes_the_database_and_its_root_link(project, capsys):
    assert _run(["build"], capsys)[0] == 0
    assert _run(["clean"], capsys)[0] == 0
    assert not (project / "build" / "compile_commands.json").exists()
    assert not os.path.lexists(project / "compile_commands.json")


def test_clean_leaves_a_link_to_another_build_alone(project, capsys):
    assert _run(["build", "--mode", "other"], capsys)[0] == 0
    assert _run(["build"], capsys)[0] == 0
    assert _run(["build", "--mode", "other"], capsys)[0] == 0  # the root links to other/
    assert _run(["clean"], capsys)[0] == 0  # cleans the first mode's build
    assert os.readlink(project / "compile_commands.json") == os.path.join("other", "compile_commands.json")
