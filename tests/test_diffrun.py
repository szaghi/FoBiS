"""Tests for ``fobis diff-run`` (phase V5 of PLAN-verification.md): a revision exported with its submodules at the
commits it records (the user's repository untouched), the files and procedures changed, each outcome of a case
(equivalent, differs, run failed on either side, within the working tree's own spread), and the command for real
with gfortran (an equivalent refactoring, a change located, JSON, ``--assess``, ``--keep``, errors)."""

from __future__ import annotations

import json
import os
import subprocess

import pytest

from fobis.fobis import run_fobis
from fobis.verification import Quantity, RunResult
from fobis.verification.diffrun import (
    DiffRunError,
    changed_files,
    compare,
    export_revision,
    judge,
    resolve,
)

GIT = ["git", "-c", "user.name=T", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]


def _git(cwd, *args):
    return subprocess.run([*GIT, *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


@pytest.fixture(autouse=True)
def _gitconfig(tmp_path, monkeypatch):
    config = tmp_path / "gitconfig"
    config.write_text('[protocol "file"]\n\tallow = always\n[color]\n\tui = always\n')
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))


def test_export_revision(tmp_path):
    sub = tmp_path / "dep"
    sub.mkdir()
    (sub / "dep.f90").write_text("! v1\n")
    _git(sub, "init", "-q", "-b", "master")
    _git(sub, "add", ".")
    _git(sub, "commit", "-qm", "v1")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.f90").write_text("! old\n")
    _git(repo, "init", "-q", "-b", "master")
    _git(repo, "submodule", "add", "-q", str(sub), "third/dep")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "old")
    old = resolve(str(repo), "HEAD")
    (repo / "third" / "dep" / "dep.f90").write_text("! v2\n")  # the submodule moves on after the revision
    _git(repo / "third" / "dep", "commit", "-qam", "v2")
    (repo / "a.f90").write_text("! new\n")
    status = _git(repo, "status", "--porcelain")
    notes = []
    export_revision(str(repo), old, str(tmp_path / "out"), notes)
    assert (tmp_path / "out" / "a.f90").read_text() == "! old\n"
    assert (tmp_path / "out" / "third" / "dep" / "dep.f90").read_text() == "! v1\n" and notes == []
    assert _git(repo, "status", "--porcelain") == status and len(_git(repo, "worktree", "list").splitlines()) == 1
    with pytest.raises(DiffRunError, match="'nope' is not a revision"):
        resolve(str(repo), "nope")


def test_changed_files(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "m.f90").write_text(
        "module m\ncontains\nsubroutine s(x)\nreal :: x\nx = 1.0\nend subroutine s\nend module m\n"
    )
    _git(repo, "init", "-q", "-b", "master")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "init")
    (repo / "m.f90").write_text((repo / "m.f90").read_text().replace("x = 1.0", "x = 2.0"))
    (repo / "new.f90").write_text("program p\nend program p\n")
    found = {c.path: c for c in changed_files(str(repo), resolve(str(repo), "HEAD"))}
    assert found["m.f90"].status == "M" and found["m.f90"].procedures == ["m::s"]
    assert found["new.f90"].status == "?"


def _result(values, status="ok"):
    return RunResult("c", "v", status, 0, quantities=[Quantity(n, [v]) for n, v in values.items()])


def test_outcomes():
    assert compare(_result({"x": 1.0}), _result({"x": 1.0}), {}).status == "equivalent"
    differs = compare(_result({"x": 1.0 + 1e-12, "y": 2.0}), _result({"x": 1.0, "y": 2.0}), {})
    assert differs.status == "differs" and not differs.ok
    assert compare(_result({"x": 1.0 + 1e-12}), _result({"x": 1.0}), {"x": "rel 1e-10"}).status == "equivalent"
    old_failed = compare(_result({}), _result({}, status="build-failed"), {})
    assert old_failed.status == "old-failed" and old_failed.to_dict()["old_run"]["status"] == "build-failed"
    assert compare(_result({}, status="failed"), _result({"x": 1.0}), {}).status == "new-failed"
    judge(differs, {"x": 11.5, "y": float("inf")})
    assert differs.status == "within-uncertainty" and differs.ok  # 1e-12 below the 10**-11.5 spread
    assert differs.spread["y"] == {"digits": "inf", "max_rel": 0.0}
    beyond = compare(_result({"x": 1.001}), _result({"x": 1.0}), {})
    judge(beyond, {"x": 6.0})
    assert beyond.status == "differs" and beyond.spread["x"]["within"] is False


# ── the command, for real ──────────────────────────────────────────────────────

PROGRAM = """\
program series
use iso_fortran_env, only: real64
implicit none
integer :: i
real(real64) :: s, x(4)
s = 0.0_real64
do i = 1, 1000
  s = s + 1.0_real64 / real(i, real64)**2
end do
x = [1.0_real64, 2.0_real64, 3.0_real64, 4.0_real64]
print '(a,es24.17)', 'zeta2 = ', s
print '(4es24.17)', x
end program series
"""


@pytest.fixture
def project(tmp_path, monkeypatch):
    repo = tmp_path / "proj"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "series.f90").write_text(PROGRAM)
    (repo / "fobos").write_text(
        "[modes]\nmodes = gnu\n\n[gnu]\ncompiler = gnu\nsrc = ./src/\nbuild_dir = ./build/\ncflags = -c -O2\n\n"
        "[case:series]\ntarget = src/series.f90\nquantities =\n    stdout\n"
        '    x : regex stdout "(\\S+)" all\n\n'
        "[assess:series]\nfamilies = rounding\nrounding =\n    O0: -O0\n    O3: -O3\n"
    )
    (repo / ".gitignore").write_text("build/\n.fobis/\n")
    _git(repo, "init", "-q", "-b", "master")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "feat: series")
    _git(repo, "tag", "v1")
    monkeypatch.chdir(repo)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr("tempfile.tempdir", str(scratch))
    return repo


def _run(args, capsys):
    try:
        run_fobis(fake_args=args)
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_diff_run(project, capsys, tmp_path):
    source = project / "src" / "series.f90"
    source.write_text(PROGRAM.replace("s = s +", "s = (s +").replace("**2\n", "**2)\n"))  # a refactoring
    code, out, err = _run(["diff-run", "v1"], capsys)
    assert code == 0 and "series: EQUIVALENT" in out and "M src/series.f90: series" in out
    assert "extracting v1" in err and os.listdir(tmp_path / "scratch") == []  # scratch removed
    assert not (project / "build").exists() and not (project / ".fobis").exists()  # nothing built in the project
    source.write_text(PROGRAM.replace("3.0_real64, 4.0", "3.5_real64, 4.0"))
    code, out, _ = _run(["diff-run", "v1"], capsys)
    assert code == 1 and "series: DIFFERS" in out
    assert "x: 1/" in out and "worst at [4]: 3.5 vs v1 3.0" in out  # the probe reads zeta2 first: [4] is x(3)
    code, out, _ = _run(["diff-run", "v1", "series", "--json", "--keep", "--assess"], capsys)
    data = json.loads(out)
    case = data["cases"][0]
    assert data["status"] == "differs" and data["commit"] == resolve(str(project), "v1")
    assert case["status"] == "differs" and case["spread"]["x"]["within"] is False
    assert data["changed"] == [{"path": "src/series.f90", "status": "M", "procedures": ["series"]}]
    assert os.path.isdir(os.path.join(data["scratch"], "revision", "src"))
    for args, message in (
        (["diff-run", "nope"], "'nope' is not a revision"),
        (["diff-run", "v1", "x"], "unknown case"),
    ):
        code, out, _ = _run(args, capsys)
        assert code == 2 and message in out
