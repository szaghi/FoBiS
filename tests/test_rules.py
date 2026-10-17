"""Tests for FoBiS.py custom rule execution."""

import os

import pytest

from fobis.fobis import run_fobis
from tests.helpers import run_rule


@pytest.mark.parametrize("n", range(1, 2))
def test_rule(monkeypatch, n):
    """Test custom rule scenario n."""
    assert run_rule(monkeypatch, f"rule-test{n}"), f"rule-test{n} failed"


def test_rule_runs_through_shell(monkeypatch, tmp_path):
    """Rules are shell command lines: globs, command chains and redirections must be interpreted."""
    obj = tmp_path / "obj"
    obj.mkdir()
    for name in ("penf.gcda", "penf_stringify.gcda", "keep.gcda"):
        (obj / name).touch()
    (tmp_path / "fobos").write_text(
        "[rule-test]\nquiet = true\nrule_1 = rm -f obj/penf*\nrule_2 = cd obj && ls > listing.txt\n"
    )
    monkeypatch.chdir(tmp_path)

    run_fobis(fake_args=["rule", "-ex", "test"])

    assert sorted(path.name for path in obj.iterdir()) == ["keep.gcda", "listing.txt"]
    assert (obj / "listing.txt").read_text().split() == ["keep.gcda", "listing.txt"]


@pytest.mark.parametrize(("status", "code"), [(0, 0), (2, 1)])
def test_ford_failure_fails_the_rule(monkeypatch, tmp_path, status, code):
    """rule --ford printed FORD's failure and exited 0."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "ford").write_text(f"#!/bin/sh\necho ford ran\nexit {status}\n")
    (bindir / "ford").chmod(0o755)
    (tmp_path / "fobos").write_text("[default]\ncompiler = gnu\n")
    monkeypatch.setenv("PATH", f"{bindir}:{os.environ['PATH']}")
    monkeypatch.chdir(tmp_path)
    try:
        run_fobis(fake_args=["rule", "--ford", "project.md"])
        exit_code = 0
    except SystemExit as exc:
        exit_code = exc.code or 0
    assert exit_code == code
