"""Tests for compiler feedback — parsing real nvfortran/gfortran logs, attribution, feedback rules, CLI.

The logs in tests/compiler-feedback/ are genuine output of ``fobis build`` with nvfortran 26.5 (-Minfo=accel,mp)
and gfortran (-fopt-info-vec-missed) on the sources next to them.
"""

from __future__ import annotations

import os

import pytest

from fobis.analysis import build_units, lex
from fobis.analysis.project import build_index
from fobis.fobis import run_fobis
from fobis.lint import RULES, discover_files, lint_files
from fobis.lint.feedback import FeedbackMessage, attribute, parse_log

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "compiler-feedback")
FEEDBACK_RULES = ("ACC001", "ACC012", "OMP008", "PRF001")


def _log(name: str) -> str:
    with open(os.path.join(FIXTURE, name), encoding="utf-8") as handle:
        return handle.read()


def test_parse_nvfortran_minfo():
    messages = parse_log(_log("nvfortran-build.txt"))
    assert all(m.compiler == "nvfortran" for m in messages)
    assert {m.procedure for m in messages} == {"axpy", "scan", "omp_off"}
    texts = [(m.procedure, m.line, m.text) for m in messages]
    assert ("axpy", 9, "Generating implicit copy(y(:n)) [if not already present]") in texts
    assert ("scan", 19, "Loop carried dependence of y prevents parallelization") in texts
    assert ("omp_off", 29, "Generating implicit map(tofrom:y(:))") in texts  # trailing blank stripped
    assert all(m.compiling == ("src/kernels.f90",) for m in messages)


def test_parse_gfortran_opt_info():
    messages = parse_log(_log("gfortran-build.txt"))
    assert all(m.compiler == "gfortran" and m.kind == "missed" for m in messages)
    assert ("src/kernels.f90", 19, "couldn't vectorize loop") in [(m.path, m.line, m.text) for m in messages]


def test_parse_ignores_unrelated_output():
    assert parse_log("Building src/a.f90\nLinking build/a\nsome: thing\n  12, not after a header\n") == []


def _units(path: str, text: str):
    return build_units(lex(text, path))


def test_attribution_resolves_duplicate_names_with_compiling_context():
    code = "module {m}\ncontains\nsubroutine work(x)\nreal, intent(inout) :: x\nx = 1\nend subroutine\nend module\n"
    a, b = _units("src/a.f90", code.format(m="a")), _units("src/b.f90", code.format(m="b"))
    project = build_index([a, b])
    in_b = FeedbackMessage("nvfortran", 5, "x", procedure="work", compiling=("src/b.f90",))
    unknown = FeedbackMessage("nvfortran", 5, "x", procedure="work")
    elsewhere = FeedbackMessage("nvfortran", 5, "x", procedure="not_in_project")
    result = attribute([in_b, unknown, elsewhere], [a, b], project)
    assert result.by_path == {"src/b.f90": [in_b]}
    assert result.unattributed == [unknown, elsewhere]  # ambiguous and unknown are counted, never guessed


def test_attribution_requires_the_line_inside_the_procedure():
    a = _units("src/a.f90", "module a\ncontains\nsubroutine work()\nend subroutine\nend module\n")
    message = FeedbackMessage("nvfortran", 40, "x", procedure="work")
    assert attribute([message], [a], build_index([a])).unattributed == [message]


@pytest.fixture
def fixture_files(monkeypatch):
    monkeypatch.chdir(FIXTURE)
    return discover_files(["src"], extensions=[".f90"])


def test_feedback_rules_on_nvfortran_log(fixture_files):
    result = lint_files(fixture_files, [RULES[r] for r in FEEDBACK_RULES], feedback=_log("nvfortran-build.txt"))
    found = [(f.rule, f.path, f.line) for f in result.findings]
    assert found == [
        ("ACC001", "src/kernels.f90", 9),
        ("ACC001", "src/kernels.f90", 18),
        ("ACC012", "src/kernels.f90", 19),
        ("OMP008", "src/kernels.f90", 29),
    ]
    assert "copyin(x(:n)), copy(y(:n))" in result.findings[0].message
    assert result.feedback_messages == 18 and result.feedback_unattributed == 0


def test_feedback_rules_on_gfortran_log(fixture_files):
    result = lint_files(fixture_files, [RULES["PRF001"]], feedback=_log("gfortran-build.txt"))
    assert [(f.path, f.line) for f in result.findings] == [("src/kernels.f90", 19), ("src/main.f90", 12)]
    assert "no vectype" in result.findings[0].message


def test_feedback_rules_silent_without_log(fixture_files):
    assert lint_files(fixture_files, [RULES[r] for r in FEEDBACK_RULES]).findings == []


def test_cli_compiler_feedback_and_missing_log(monkeypatch, capsys):
    monkeypatch.chdir(FIXTURE)
    args = ["lint", "--mode", "nv", "--select", "ACC001", "--baseline", "none.json", "--exit-zero"]
    run_fobis(fake_args=[*args, "--compiler-feedback", "nvfortran-build.txt"])
    out = capsys.readouterr().out
    assert "src/kernels.f90:9: ACC001" in out and "Compiler feedback: 18 message(s) read" in out
    with pytest.raises(SystemExit) as excinfo:
        run_fobis(fake_args=[*args, "--compiler-feedback", "missing.log"])
    assert excinfo.value.code == 1
    assert '--cflags "-Minfo=accel,mp"' in capsys.readouterr().out
