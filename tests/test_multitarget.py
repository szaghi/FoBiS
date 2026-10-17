"""Tests for multi-target builds and Fobos.get_targets() (issue #175)."""

from __future__ import annotations

import argparse
import os
import shutil
import tempfile

import pytest

from fobis.Fobos import Fobos


def _make_fobos_with_targets(root: str, content: str) -> Fobos:
    path = os.path.join(root, "fobos")
    with open(path, "w") as f:
        f.write(content)
    cliargs = argparse.Namespace(
        fobos=path,
        fobos_case_insensitive=False,
        mode=None,
        which="build",
    )
    return Fobos(cliargs=cliargs)


# ── get_targets() ────────────────────────────────────────────────────────────


def test_get_targets_parses_sections():
    """Three [target.X] sections → list of 3 dicts with correct names."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[default]\ncompiler=Gnu\n\n"
            "[target.solver]\nsource=src/solver.F90\noutput=solver\n\n"
            "[target.viewer]\nsource=src/viewer.F90\noutput=viewer\n\n"
            "[target.postproc]\nsource=src/postproc.F90\noutput=postproc\n"
        )
        fobos = _make_fobos_with_targets(root, content)
        targets = fobos.get_targets()
        assert len(targets) == 3
        names = {t["name"] for t in targets}
        assert names == {"solver", "viewer", "postproc"}


def test_get_targets_empty_no_sections():
    """No [target.*] sections → empty list."""
    with tempfile.TemporaryDirectory() as root:
        content = "[default]\ncompiler=Gnu\n"
        fobos = _make_fobos_with_targets(root, content)
        assert fobos.get_targets() == []


def test_get_targets_source_and_output():
    """Target dict must contain 'source', 'output', and 'name'."""
    with tempfile.TemporaryDirectory() as root:
        content = "[default]\ncompiler=Gnu\n\n[target.solver]\nsource=src/solver.F90\noutput=mysolver\n"
        fobos = _make_fobos_with_targets(root, content)
        targets = fobos.get_targets()
        assert targets[0]["name"] == "solver"
        assert targets[0]["source"] == "src/solver.F90"
        assert targets[0]["output"] == "mysolver"


def test_get_targets_extra_overrides():
    """Extra keys in [target.X] are included as overrides."""
    with tempfile.TemporaryDirectory() as root:
        content = "[default]\ncompiler=Gnu\n\n[target.solver]\nsource=src/solver.F90\noutput=solver\ncflags=-O0\n"
        fobos = _make_fobos_with_targets(root, content)
        targets = fobos.get_targets()
        assert targets[0].get("cflags") == "-O0"


def test_get_targets_example_prefix():
    """Section prefix 'example' finds [example.X] sections."""
    with tempfile.TemporaryDirectory() as root:
        content = "[default]\ncompiler=Gnu\n\n[example.demo]\nsource=examples/demo.F90\noutput=demo\n"
        fobos = _make_fobos_with_targets(root, content)
        examples = fobos.get_targets("example")
        targets = fobos.get_targets("target")
        assert len(examples) == 1
        assert examples[0]["name"] == "demo"
        assert targets == []


def test_get_targets_no_fobos_file():
    """No fobos file loaded → empty list."""
    cliargs = argparse.Namespace(
        fobos=None,
        fobos_case_insensitive=False,
        mode=None,
        which="build",
    )
    fobos = Fobos(cliargs=cliargs)
    assert fobos.get_targets() == []


# ── _cliargs_for_target() integration ────────────────────────────────────────


def test_cliargs_clone_applies_override():
    """target dict cflags=-O0 overrides mode cflags=-O2 in the clone."""
    import argparse

    from fobis.fobis import _cliargs_for_target

    base = argparse.Namespace(cflags="-O2", lflags="", build_dir="./", src=["./"])
    target_dict = {"name": "solver", "source": "solver.F90", "output": "solver", "cflags": "-O0"}
    cloned = _cliargs_for_target(base, target_dict)

    assert cloned.cflags == "-O0"
    assert base.cflags == "-O2"  # original unchanged


def test_cliargs_clone_does_not_mutate_base():
    """Deep copy — mutating the clone must not affect base."""
    from fobis.fobis import _cliargs_for_target

    base = argparse.Namespace(cflags="-O2", src=["./"], build_dir="./")
    target_dict = {"name": "solver", "output": "solver"}
    cloned = _cliargs_for_target(base, target_dict)
    cloned.cflags = "-O3"

    assert base.cflags == "-O2"


# ── a real build of several targets ──────────────────────────────────────────


@pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran")
def test_each_target_is_built_with_its_own_settings(tmp_path, monkeypatch):
    """A [target.NAME]'s output, mklib and track_build were ignored: the program was linked under the mode's name."""
    from fobis.fobis import run_fobis

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "greet.f90").write_text(
        "module greet\ncontains\nsubroutine hello()\nprint '(A)', 'hello'\nend subroutine hello\nend module greet\n"
    )
    (tmp_path / "src" / "main.f90").write_text("program main\nuse greet, only : hello\ncall hello\nend program main\n")
    (tmp_path / "fobos").write_text(
        "[default]\ncompiler = gnu\ncflags = -c\nsrc = ./src/\nbuild_dir = ./build/\n\n"
        "[target.app]\nsource = src/main.f90\noutput = mainprog\ntrack_build = True\n\n"
        "[target.lib]\nsource = src/greet.f90\nmklib = static\noutput = libgreet.a\n"
    )
    monkeypatch.chdir(tmp_path)
    run_fobis(fake_args=["build", "--quiet"])
    assert (tmp_path / "build" / "mainprog").is_file() and not (tmp_path / "build" / "main").exists()
    assert (tmp_path / "build" / ".main.f90.track_build").is_file()
    assert (tmp_path / "build" / "libgreet.a").is_file()
    assert not (tmp_path / "build" / ".greet.f90.track_build").exists()  # track_build is the app target's only
