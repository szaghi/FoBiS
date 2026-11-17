"""An up-to-date link is skipped (issue #218): same command, no input newer than the output."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time

import pytest

from fobis.fobis import run_fobis

pytestmark = pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran not on PATH")


def _project(root):
    src = root / "src"
    src.mkdir()
    (src / "a.f90").write_text("module a\ncontains\nsubroutine sa()\nend subroutine\nend module\n")
    (src / "b.f90").write_text("module b\nuse a\ncontains\nsubroutine sb()\ncall sa()\nend subroutine\nend module\n")
    (src / "c.f90").write_text("module c\nend module\n")
    (src / "p.f90").write_text("program p\nuse b\nuse c\ncall sb()\nend program\n")
    return src


def _build(capsys, *args):
    run_fobis(fake_args=["build", "--src", "src", "--target", "p.f90", *args])
    return capsys.readouterr().out


def _later(path):
    """Make *path* newer than anything built so far (file systems with a coarse clock)."""
    stamp = time.time() + 2
    os.utime(path, (stamp, stamp))


def test_second_build_skips_the_link(tmp_path, monkeypatch, capsys):
    _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert "Linking ./p" in _build(capsys)
    built = os.path.getmtime(tmp_path / "p")
    out = _build(capsys)
    assert "Target ./p is up to date: link skipped" in out
    assert "Linking" not in out.replace("Linking flags", "")
    assert os.path.getmtime(tmp_path / "p") == built


@pytest.mark.parametrize(
    "change",
    ["touch", "lflags", "force", "delete", "library"],
)
def test_what_links_again(tmp_path, monkeypatch, capsys, change):
    src = _project(tmp_path)
    extra = []
    if change == "library":
        (tmp_path / "libx.a").write_bytes(b"!<arch>\n")
        extra = ["--libs", "libx.a"]
    monkeypatch.chdir(tmp_path)
    _build(capsys, *extra)
    if change == "touch":
        _later(src / "c.f90")
    elif change == "lflags":
        extra = [*extra, "--lflags", "-O1"]
    elif change == "force":
        extra = [*extra, "--force-compile"]
    elif change == "delete":
        os.remove(tmp_path / "p")
    elif change == "library":
        _later(tmp_path / "libx.a")
    assert "Linking ./p" in _build(capsys, *extra)


def test_a_library_found_by_name_in_lib_dir(tmp_path, monkeypatch, capsys):
    _project(tmp_path)
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "liby.a").write_bytes(b"!<arch>\n")
    monkeypatch.chdir(tmp_path)
    args = ["--ext-libs", "y", "--lib-dir", "lib"]
    _build(capsys, *args)
    assert "link skipped" in _build(capsys, *args)
    _later(tmp_path / "lib" / "liby.a")
    assert "Linking ./p" in _build(capsys, *args)


def test_static_library_archive_skipped(tmp_path, monkeypatch, capsys):
    src = _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    args = ["build", "--src", "src", "--target", "b.f90", "--mklib", "static", "--output", "libb.a"]
    run_fobis(fake_args=args)
    capsys.readouterr()
    run_fobis(fake_args=args)
    assert "Target ./libb.a is up to date: archive skipped" in capsys.readouterr().out
    _later(src / "a.f90")
    run_fobis(fake_args=args)
    assert "Linking ./libb.a" in capsys.readouterr().out


def test_skipped_across_processes(tmp_path):
    # the link command lists the objects in a fixed order: a set's order differs between Python processes
    _project(tmp_path)
    env = {**os.environ, "PYTHONPATH": os.path.dirname(os.path.dirname(os.path.abspath(__file__)))}
    command = [sys.executable, "-m", "fobis", "build", "--src", "src", "--target", "p.f90", "-j", "1"]
    subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, check=True)
    for seed in ("1", "2", "3"):
        out = subprocess.run(
            command, cwd=tmp_path, env={**env, "PYTHONHASHSEED": seed}, capture_output=True, text=True, check=True
        ).stdout
        assert "link skipped" in out
