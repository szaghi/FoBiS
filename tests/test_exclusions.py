"""Exclusions (issue #218, phase 2): ``exclude_dirs`` by path components, command-line lists added to the mode's,
``:: src=DIR`` restricting what a source dependency contributes."""

from __future__ import annotations

import json
import os
import shutil

import pytest

from fobis.fobis import run_fobis
from fobis.FoBiSConfig import FoBiSConfig
from fobis.utils import dir_excluded

GFORTRAN = shutil.which("gfortran") is not None


@pytest.mark.parametrize(
    ("directory", "entries", "expected"),
    [
        ("src/dep/docs/snippets", ["docs"], True),
        ("src/dep/docs", ["docs/"], True),
        ("src/mydocs", ["docs"], False),
        ("src/dep/docs/snippets", ["nip"], False),  # the substring rule excluded it
        ("src/third_party/FOSSIL/docs/examples", ["FOSSIL/docs"], True),
        ("src/third_party/FOSSIL/src/lib", ["FOSSIL/docs"], False),
        ("./src/third_party/FOSSIL/docs", ["src/third_party/FOSSIL/docs/"], True),
        ("src/references", ["references/"], True),
        ("src/references_old", ["references/"], False),
        ("src/a", ["."], False),
        ("src/a", [""], False),
        ("src/a/b", ["./src/a"], True),
    ],
)
def test_dir_excluded_by_components(directory, entries, expected):
    assert dir_excluded(directory, entries) is expected


def test_dir_excluded_absolute_and_parent(tmp_path, monkeypatch):
    (tmp_path / "project" / "src").mkdir(parents=True)
    (tmp_path / "other").mkdir()
    monkeypatch.chdir(tmp_path / "project")
    assert dir_excluded("src/x", [str(tmp_path / "project" / "src")])
    assert not dir_excluded("src/x", [str(tmp_path / "other")])
    assert dir_excluded("../other/y", ["../other"])
    assert not dir_excluded("src", ["../other"])


def _config(tmp_path, monkeypatch, fobos, *args):
    (tmp_path / "fobos").write_text(fobos)
    monkeypatch.chdir(tmp_path)
    return FoBiSConfig(fake_args=["build", *args]).cliargs


MODE = """[default]
compiler     = gnu
src          = ./src/
exclude_dirs = references/
exclude      = old.f90
include      = ./inc/
libs         = a.a
"""


def test_command_line_lists_are_added_to_the_mode(tmp_path, monkeypatch):
    cliargs = _config(
        tmp_path,
        monkeypatch,
        MODE,
        "--exclude-dirs",
        "src/docs",
        "--exclude",
        "new.f90",
        "--include",
        "./more/",
        "--libs",
        "b.a",
    )
    assert cliargs.exclude_dirs == ["references", "src/docs"]
    assert cliargs.exclude == ["old.f90", "new.f90"]
    assert cliargs.include == ["inc", "more"]
    assert cliargs.libs == ["a.a", "b.a"]


def test_src_still_replaces(tmp_path, monkeypatch):
    cliargs = _config(tmp_path, monkeypatch, MODE, "--src", "./other/")
    assert cliargs.src == ["src"]  # the mode's: a source directory changes which files are scanned


def test_a_value_given_twice_is_kept_once(tmp_path, monkeypatch):
    cliargs = _config(tmp_path, monkeypatch, MODE, "--exclude-dirs", "references")
    assert cliargs.exclude_dirs == ["references"]


# --- building -----------------------------------------------------------------------------------------------------

LIB = "module dep_lib\ncontains\nsubroutine hello()\nprint *, 'hello'\nend subroutine\nend module\n"
DOCS_PROGRAM = "program demo\nuse dep_lib\ncall hello()\nend program\n"
BROKEN = "x = = 1\n"
MAIN = "program main\nuse dep_lib\ncall hello()\nend program main\n"


def _dependency(root):
    (root / "src" / "lib").mkdir(parents=True)
    (root / "docs" / "snippets").mkdir(parents=True)
    (root / "src" / "lib" / "dep_lib.f90").write_text(LIB)
    (root / "docs" / "snippets" / "demo.f90").write_text(DOCS_PROGRAM)
    (root / "docs" / "snippets" / "broken.f90").write_text(BROKEN)


@pytest.mark.skipif(not GFORTRAN, reason="gfortran not on PATH")
def test_src_restricts_a_fetched_dependency_under_the_sources(tmp_path, monkeypatch, capsys):
    # ADAM's layout: the deps dir is inside the project's sources
    project = tmp_path / "project"
    _dependency(project / "src" / "third_party" / "dep")
    (project / "src" / "app").mkdir(parents=True)
    (project / "src" / "app" / "main.f90").write_text(MAIN)
    (project / "fobos").write_text(
        "[dependencies]\ndeps_dir = src/third_party\ndep = https://github.com/someone/dep :: src=src/lib\n\n"
        "[default]\ncompiler = gnu\nsrc = ./src/\ntarget = main.f90\nbuild_dir = ./build/\n"
    )
    monkeypatch.chdir(project)
    run_fobis(fake_args=["introspect", "--sources"])
    capsys.readouterr()  # introspect does not load the dependencies: nothing to assert
    run_fobis(fake_args=["build", "--verbose"])
    out = capsys.readouterr().out
    assert "snippets" not in out  # never parsed: not even left out
    assert os.path.isfile(project / "build" / "main")


@pytest.mark.skipif(not GFORTRAN, reason="gfortran not on PATH")
def test_src_restricts_a_path_dependency(tmp_path, monkeypatch, capsys):
    _dependency(tmp_path / "dep")
    project = tmp_path / "project"
    (project / "app").mkdir(parents=True)
    (project / "app" / "main.f90").write_text(MAIN)
    (project / "fobos").write_text(
        "[dependencies]\ndep = path=../dep :: src=src/lib,src/missing\n\n"
        "[default]\ncompiler = gnu\nsrc = ./app/\ntarget = main.f90\n"
    )
    monkeypatch.chdir(project)
    run_fobis(fake_args=["build", "--json"])
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["status"] == "ok"
    assert result["objects_compiled"] == 2  # dep_lib and main: the snippets were never scanned
    assert "src=src/missing" in captured.out + captured.err


@pytest.mark.skipif(not GFORTRAN, reason="gfortran not on PATH")
def test_exclude_dirs_on_the_command_line_works_with_a_mode(tmp_path, monkeypatch, capsys):
    project = tmp_path
    (project / "src" / "docs").mkdir(parents=True)
    (project / "src" / "main.f90").write_text("program main\nend program main\n")
    (project / "src" / "docs" / "demo.f90").write_text("program demo\nend program demo\n")
    (project / "fobos").write_text("[default]\ncompiler = gnu\nsrc = ./src/\nexclude_dirs = references/\n")
    monkeypatch.chdir(project)
    run_fobis(fake_args=["build", "--exclude-dirs", "src/docs"])
    assert os.path.isfile(project / "main")
    assert not os.path.exists(project / "demo")  # before: the mode's list replaced the command line's
