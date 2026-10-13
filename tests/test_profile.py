"""Tests for ``fobis profile`` (phase V11 of PLAN-verification.md): the gprof flat profile and the raw callgrind
format parsed from GENUINE outputs in ``tests/profile/`` (gfortran 16 ``-O2 -pg -g`` of ``workmod.f90`` +
``app.f90``: ``gprof-flat.txt``; ``-O0`` ``tiny*.f90``, a run shorter than one sample: ``gprof-zero.txt``; valgrind
3.22 callgrind of the single-file ``work.f90`` at ``-O2 -g``, where everything is inlined into the main program:
``callgrind-inlined.txt``), the callgrind syntax rules on a small hand-written file (name compression, relative
positions, inlined files, the inclusive cost after ``calls=``), the mapping to procedures and lines (module scope),
the command for real (gprof always; callgrind when valgrind is installed) and its errors."""

from __future__ import annotations

import json
import os
import shutil

import pytest

from fobis.fobis import run_fobis
from fobis.lint import lint_files
from fobis.verification import profile as pf

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profile")


def _read(name):
    with open(os.path.join(HERE, name)) as handle:
        return handle.read()


def _source(*names):
    return pf.SourceMap(lint_files([os.path.join(HERE, n) for n in names], []).units, root=HERE)


def test_gprof():
    routines, sample = pf.parse_gprof(_read("gprof-flat.txt"))
    assert sample == 0.01 and [(r.symbol, r.self_cost, r.calls) for r in routines] == [
        ("__work_MOD_heavy", 0.88, 5),
        ("MAIN__", 0.0, 1),
        ("__work_MOD_light", 0.0, 1),
    ]
    profile = pf.from_gprof(_read("gprof-flat.txt"), _source("workmod.f90", "app.f90"), top=10)
    first = profile.routines[0]
    assert (first.procedure, first.location, first.percent) == ("work::heavy", "workmod.f90:4", 100.0)
    assert profile.routines[1].procedure == "app" and profile.project_share == 100.0
    assert "88 samples" in profile.notes[0]
    zero = pf.from_gprof(_read("gprof-zero.txt"), _source("tiny.f90", "tiny_p.f90"), top=10)
    assert zero.project_share is None and zero.notes[0].startswith("no time measured")
    assert [(r.procedure, r.calls) for r in zero.routines] == [("tiny_m::twice", 1000), ("tiny", 1)]
    with pytest.raises(pf.ProfileError, match="no samples"):
        pf.from_gprof("Flat profile:\n", _source("tiny.f90"), top=5)
    profile.processes = [0.24, 0.45]
    assert profile.imbalance == pytest.approx(0.45 / 0.345)
    assert "imbalance max/mean 1.30" in pf.render_text("app", profile)


SYNTHETIC = """\
# callgrind format
version: 1
positions: line
events: Ir
fl=(1) a.f90
fn=(1) __m_MOD_f
10 100
+2 50
fi=(2) b.inc
5 7
fe=(1)
* 3
cfn=(2) __m_MOD_g
calls=4 20
13 999
-1 1
fn=(2)
20 40
totals: 201
"""


def test_callgrind_format():
    data = pf.parse_callgrind(SYNTHETIC)
    assert data.total == 201
    assert data.functions == {"__m_MOD_f": 161, "__m_MOD_g": 40}  # the 999 after calls= is inclusive: skipped
    assert data.calls[("__m_MOD_f", "__m_MOD_g")] == 999 and data.call_counts[("__m_MOD_f", "__m_MOD_g")] == 4
    assert data.lines == {
        ("a.f90", 10): 100,
        ("a.f90", 12): 51,  # +2 from 10, then -1 from the skipped 13
        ("b.inc", 5): 7,  # inlined file
        ("a.f90", 5): 3,  # back to a.f90 at the same position (*)
        ("a.f90", 20): 40,  # g, by its compressed name
    }


def test_callgrind_inlined():
    """Everything inlined into MAIN__: the source lines still find work::heavy."""
    profile = pf.from_callgrind(pf.parse_callgrind(_read("callgrind-inlined.txt")), _source("work.f90"), top=5)
    assert profile.total == 1401346145 and profile.routines[0].symbol == "MAIN__"
    assert profile.routines[0].procedure == "app"
    assert profile.procedures[0]["procedure"] == "work::heavy" and profile.procedures[0]["percent"] == 99.9
    assert profile.lines[0]["location"] == "work.f90:10" and "sqrt" in profile.lines[0]["text"]
    assert "work::heavy" in profile.notes[-1] and "inlined by the compiler" in profile.notes[-1]


def test_source_map():
    source = _source("workmod.f90", "app.f90")
    assert source.symbol("__work_MOD_light") == ("work::light", "workmod.f90:14")
    assert source.symbol("malloc") == ("", "")
    assert source.line("workmod.f90", 21)[1] == "work::light::helper"
    assert source.line("workmod.f90", 24) == ("workmod.f90", "work (module scope)", "end module work")
    assert source.line("elsewhere.f90", 3) == ("", "", "")
    assert pf.wrap(["mpirun", "-np", "2", "./p", "a"], ["./p"], ["a"], ["valgrind"]) == [
        "mpirun",
        "-np",
        "2",
        "valgrind",
        "./p",
        "a",
    ]


# ── the command, for real ──────────────────────────────────────────────────────


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    shutil.copy(os.path.join(HERE, "workmod.f90"), root / "src" / "work.f90")
    shutil.copy(os.path.join(HERE, "app.f90"), root / "src" / "app.f90")
    (root / "fobos").write_text(
        "[modes]\nmodes = gnu\n\n[gnu]\ncompiler = gnu\nsrc = ./src/\nbuild_dir = ./build/\ncflags = -c -O2\n\n"
        "[case:app]\ntarget = src/app.f90\nquantities = stdout\n\n[case:cmd]\ncommand = true\n"
    )
    monkeypatch.chdir(root)
    return root


def _run(args, capsys):
    try:
        run_fobis(fake_args=args)
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.mark.skipif(shutil.which("gprof") is None, reason="gprof not installed")
def test_profile_gprof(project, capsys):
    code, out, err = _run(["profile", "app", "--json"], capsys)
    data = json.loads(out)
    assert code == 0 and data["tool"] == "gprof" and data["mode"] == "gnu"
    assert data["routines"][0]["procedure"] == "work::heavy" and data["routines"][0]["calls"] == 5
    assert data["routines"][0]["location"] == "src/work.f90:4" and "building app for gprof" in err
    assert not (project / "build").exists()  # the -pg build is a variant, apart from the mode's objects
    for args, message in (
        (["profile", "nope"], "unknown case"),
        (["profile", "app", "--tool", "nsys"], "nsys/ncu are not supported yet"),
        (["profile", "cmd"], "gprof needs a program FoBiS builds"),
    ):
        code, out, err = _run(args, capsys)
        assert code == 2 and message in out + err


@pytest.mark.skipif(shutil.which("valgrind") is None, reason="valgrind not installed")
def test_profile_callgrind(project, capsys):
    code, out, _ = _run(["profile", "app", "--tool", "callgrind", "--top", "3"], capsys)
    assert code == 0 and "profile app (callgrind)" in out
    assert "work::heavy (src/work.f90:4)" in out and "src/work.f90:10  y(i) = sqrt(" in out
