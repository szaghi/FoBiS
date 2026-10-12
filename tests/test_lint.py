"""Tests for fobis.lint — rules (positive and negative cases), engine, reports, CLI."""

from __future__ import annotations

import json
import re
import textwrap

import pytest

from fobis.fobis import run_fobis
from fobis.lint import (
    RULES,
    LintResult,
    apply_baseline,
    discover_files,
    lint_files,
    lint_text,
    load_baseline,
    render,
    select_rules,
    write_baseline,
)


def _lines(rule_id: str, code: str, path: str = "t.f90", **kwargs) -> list[int]:
    """Lines where *rule_id* fires on *code*."""
    findings = lint_text(code, path, [RULES[rule_id]], **kwargs)  # no dedent: fixed form needs its columns
    return [f.line for f in findings if f.rule == rule_id]


# Each case: rule id, Fortran code, lines expected to be reported (empty: the rule must stay silent).
CASES = [
    # COR001 implicit-typing
    ("COR001", "module m\ncontains\nend module m\n", [1]),
    ("COR001", "program p\nimplicit none\nend program p\n", []),
    ("COR001", "subroutine s()\nend subroutine s\n", [1]),
    (
        "COR001",
        "module m\nimplicit none\ncontains\nsubroutine s()\nimplicit real(a-h)\nend subroutine\nend module\n",
        [5],
    ),
    ("COR001", "submodule (p) c\nend submodule c\n", []),
    # COR002 interface-implicit-typing
    (
        "COR002",
        "module m\nimplicit none\ninterface\nsubroutine cb(x)\nreal :: x\nend subroutine\nend interface\nend module\n",
        [4],
    ),
    (
        "COR002",
        "module m\nimplicit none\ninterface\nsubroutine cb(x)\nimplicit none\nreal :: x\nend subroutine\nend interface\nend module\n",
        [],
    ),
    # COR003 implicit-external-procedures (opt-in)
    ("COR003", "program p\nimplicit none\nend program\n", [1]),
    ("COR003", "program p\nimplicit none (type, external)\nend program\n", []),
    # COR010 missing-intent
    ("COR010", "subroutine s(a, b)\nreal :: a\nreal, intent(in) :: b\nend subroutine\n", [2]),
    ("COR010", "subroutine s(a)\nend subroutine\n", [1]),  # undeclared: reported at the header
    ("COR010", "subroutine s(f, g, v)\nexternal f\nprocedure(iface) :: g\ninteger, value :: v\nend subroutine\n", []),
    (
        "COR010",
        "subroutine s(cb)\ninterface\nsubroutine cb(x)\nreal, intent(in) :: x\nend subroutine\nend interface\nend subroutine\n",
        [],
    ),
    ("COR010", "subroutine s(a)\nreal :: a\nintent(inout) :: a\nend subroutine\n", []),
    # COR011 assumed-size
    ("COR011", "subroutine s(a, b)\nreal, intent(in) :: a(*), b(3, *)\nend subroutine\n", [2, 2]),
    ("COR011", "subroutine s(a, c)\nreal, intent(in) :: a(:)\ncharacter(len=*), intent(in) :: c\nend subroutine\n", []),
    ("COR011", "function f(s) bind(c)\ncharacter(kind=c_char), intent(in) :: s(*)\nend function\n", []),
    # COR020 initialisation-in-declaration
    ("COR020", "subroutine s()\ninteger :: n = 0\nend subroutine\n", [2]),
    ("COR020", "subroutine s()\ninteger, save :: n = 0\ninteger, parameter :: m = 1\nend subroutine\n", []),
    ("COR020", "subroutine s()\nsave\ninteger :: n = 0\nend subroutine\n", []),
    ("COR020", "module m\ninteger :: n = 0\nend module\n", []),  # module variables are saved anyway
    ("COR020", "program p\ninteger :: n = 0\nend program\n", []),
    ("COR020", "module m\ntype :: t\ninteger :: n = 0\nend type\nend module\n", []),  # default initialisation
    # COR021 pointer-initialisation-in-declaration
    ("COR021", "subroutine s()\nreal, pointer :: p(:) => null()\nend subroutine\n", [2]),
    ("COR021", "subroutine s()\nreal, pointer :: p(:)\nnullify(p)\nend subroutine\n", []),
    # COR030 external-procedure
    ("COR030", "subroutine s()\nexternal :: solve\nreal, external :: f\nend subroutine\n", [2, 3]),
    ("COR030", "subroutine s()\nend subroutine\n", []),
    # COR031 procedure-not-in-module
    ("COR031", "subroutine s()\nend subroutine\nfunction f()\nend function\n", [1, 3]),
    (
        "COR031",
        "module m\ncontains\nsubroutine s()\nend subroutine\nend module\n"
        "program p\ncontains\nsubroutine q()\nend subroutine\nend program\n",
        [],
    ),
    # COR040 use-all
    ("COR040", "module m\nuse penf\nuse, intrinsic :: iso_fortran_env\nend module\n", [2, 3]),
    ("COR040", "module m\nuse penf, only: R8P\nend module\n", []),
    # COR041 missing-intrinsic
    ("COR041", "module m\nuse iso_fortran_env, only: real64\nuse :: iso_c_binding\nend module\n", [2, 3]),
    ("COR041", "module m\nuse, intrinsic :: iso_fortran_env, only: real64\nuse penf, only: R8P\nend module\n", []),
    # COR050 missing-accessibility-statement
    ("COR050", "module m\nimplicit none\nend module\n", [1]),
    ("COR050", "module m\nimplicit none\nprivate\nend module\n", []),
    ("COR050", "module m\npublic\nend module\n", []),
    # COR060 unchecked-stat
    ("COR060", "subroutine s(n)\nallocate(a(n), stat=ierr)\na = 0\nend subroutine\n", [2]),
    ("COR060", "subroutine s(n)\nallocate(a(n), stat=ierr)\nif (ierr /= 0) stop\nend subroutine\n", []),
    ("COR060", "subroutine s(n)\nallocate(a(n))\nend subroutine\n", []),
    # COR061 multiple-allocations-with-stat
    ("COR061", "subroutine s(n)\nallocate(a(n), b(n), stat=ierr)\nif (ierr /= 0) stop\nend subroutine\n", [2]),
    ("COR061", "subroutine s(n)\nallocate(a(n), b(n))\nallocate(c(n), stat=ierr, errmsg=msg)\nend subroutine\n", []),
    ("COR061", "subroutine s(n)\nallocate(real :: a(n), stat=ierr)\nend subroutine\n", []),
    # OBS001 common-block
    ("OBS001", "subroutine s()\ncommon /blk/ a, b\ncommon x\nend subroutine\n", [2, 3]),
    ("OBS001", "subroutine s()\ncommon = 1\nprint *, 'common /x/'\nend subroutine\n", []),
    # OBS002 equivalence-statement
    ("OBS002", "subroutine s()\nequivalence (a, b)\nend subroutine\n", [2]),
    # OBS003 block-data
    ("OBS003", "block data init\ncommon /c/ x\nend block data init\n", [1]),
    ("OBS003", "module m\nend module\n", []),
    # OBS004 entry-statement
    ("OBS004", "subroutine s(x)\nentry t(x)\nend subroutine\n", [2]),
    ("OBS004", "subroutine s()\nentry = 1\nend subroutine\n", []),
    # OBS005 specific-intrinsic-name
    ("OBS005", "subroutine s()\ny = dsqrt(x) + float(n) + amax1(a, b)\nend subroutine\n", [2, 2, 2]),
    ("OBS005", "subroutine s()\ny = sqrt(x) + real(n)\nend subroutine\n", []),
    ("OBS005", "subroutine s()\nreal :: dabs(3)\ny = dabs(1)\nend subroutine\n", []),  # a local array named dabs
    # OBS006 computed-go-to
    ("OBS006", "subroutine s(i)\ngo to (10, 20) i\ngoto (10) i\n10 continue\n20 continue\nend subroutine\n", [2, 3]),
    ("OBS006", "subroutine s()\ngo to 10\n10 continue\nend subroutine\n", []),
    # OBS007 pause-statement
    ("OBS007", "program p\npause\npause 'wait'\nend program\n", [2, 3]),
    ("OBS007", "program p\npause = 1\nend program\n", []),
    # OBS008 deprecated-character-syntax
    ("OBS008", "subroutine s()\ncharacter*20 :: a\ncharacter * (*) b\nend subroutine\n", [2, 3]),
    ("OBS008", "subroutine s()\ncharacter(len=20) :: a\nend subroutine\n", []),
    # OBS009 forall
    (
        "OBS009",
        "subroutine s()\nforall (i = 1:n) a(i) = 0\nlbl: forall (i = 1:n)\na(i) = 1\nend forall lbl\nend subroutine\n",
        [2, 3],
    ),
    ("OBS009", "subroutine s()\ndo concurrent (i = 1:n)\nend do\nend subroutine\n", []),
    # OBS010 arithmetic-if
    ("OBS010", "subroutine s()\nif (x - 1.0) 10, 20, 30\n10 continue\n20 continue\n30 continue\nend subroutine\n", [2]),
    ("OBS010", "subroutine s()\nif (x > 0) y = 1\nif (f(x, 2)) then\nend if\nend subroutine\n", []),
    # OBS011 labelled-do-loop
    ("OBS011", "subroutine s()\ndo 10 i = 1, n\n10 continue\ndo 20, j = 1, n\n20 continue\nend subroutine\n", [2, 4]),
    ("OBS011", "subroutine s()\ndo i = 1, n\nend do\nend subroutine\n", []),
    # OBS012 shared-do-termination
    ("OBS012", "subroutine s()\ndo 10 i = 1, n\ndo 10 j = 1, n\n10 continue\nend subroutine\n", [3]),
    ("OBS012", "subroutine s()\ndo 10 i = 1, n\n10 continue\ndo 20 j = 1, n\n20 continue\nend subroutine\n", []),
    # OBS013 bad-do-termination
    ("OBS013", "subroutine s()\ndo 10 i = 1, n\n10 a(i) = 0\nend subroutine\n", [2]),
    ("OBS013", "subroutine s()\ndo 10 i = 1, n\n10 end do\nend subroutine\n", []),
    # OBS020 deprecated-mpi-include
    ("OBS020", "subroutine s()\ninclude 'mpif.h'\nend subroutine\n", [2]),
    ("OBS020", "subroutine s()\nuse mpi_f08\nend subroutine\n", []),
    # OBS021 deprecated-omp-include
    ("OBS021", 'subroutine s()\ninclude "omp_lib.h"\nend subroutine\n', [2]),
]


@pytest.mark.parametrize(("rule_id", "code", "expected"), CASES, ids=[f"{c[0]}-{i}" for i, c in enumerate(CASES)])
def test_rule_cases(rule_id, code, expected):
    assert _lines(rule_id, code) == expected


def test_every_rule_has_a_positive_case():
    covered = {rule_id for rule_id, _, expected in CASES if expected}
    engine_rules = {"LNT001", "LNT002", "LNT003", "LNT004"}  # tested below
    assert set(RULES) - engine_rules <= covered


def test_rules_are_documented_consistently():
    for rid, rul in RULES.items():
        assert re.fullmatch(r"[A-Z]{3}\d{3}", rid)
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", rul.name)
        assert rul.summary and rul.rationale.strip()
        assert rid in rul.explain()
    names = [r.name for r in RULES.values()]
    assert len(names) == len(set(names))
    equivalents = [r.equivalent for r in RULES.values() if r.equivalent]
    assert len(equivalents) == len(set(equivalents))


def test_fixed_form_obsolescent_code():
    code = "      SUBROUTINE S\n      COMMON /C/ X\n      DO 10 I = 1, 3\n   10 X = X + 1\n      END\n"
    assert _lines("OBS001", code, "t.f") == [2]
    assert _lines("OBS013", code, "t.f") == [3]


def test_preprocessor_defines_select_linted_code():
    code = "subroutine s()\n#ifdef MPI\ninclude 'mpif.h'\n#else\ncommon /c/ x\n#endif\nend subroutine\n"
    assert _lines("OBS020", code, "t.F90", defines={"MPI": "1"}) == [3]
    assert _lines("OBS001", code, "t.F90", defines={"MPI": "1"}) == []
    assert _lines("OBS001", code, "t.F90") == [5]


# ── engine: selection ──────────────────────────────────────────────────────────


def test_select_rules_default_prefix_all_and_ignore():
    default = {r.id for r in select_rules()}
    assert "COR003" not in default and "COR001" in default
    assert {r.id for r in select_rules(["COR00"])} == {"COR001", "COR002", "COR003"}
    assert {r.id for r in select_rules(["ALL"])} == set(RULES)
    assert "COR040" not in {r.id for r in select_rules([], ["COR04"])}
    with pytest.raises(ValueError, match="XYZ"):
        select_rules(["XYZ"])


# ── engine: suppressions ───────────────────────────────────────────────────────

_SUPPRESS_RULES = [RULES[r] for r in ("COR020", "LNT001", "LNT002", "LNT003")]


def _found(code: str) -> list[tuple[int, str]]:
    return [(f.line, f.rule) for f in lint_text(textwrap.dedent(code), "t.f90", _SUPPRESS_RULES)]


def test_inline_suppression_with_reason():
    code = "subroutine s()\ninteger :: n = 0 ! fobis: ignore[COR020] counter kept on purpose\nend subroutine\n"
    assert _found(code) == []


def test_own_line_suppression_applies_to_next_statement():
    code = "subroutine s()\n! fobis: ignore[COR020] intended\ninteger :: n = 0\ninteger :: m = 0\nend subroutine\n"
    assert _found(code) == [(4, "COR020")]


def test_suppression_covers_a_continued_statement():
    code = "subroutine s()\ninteger :: n = &\n  0 ! fobis: ignore[COR020] intended\nend subroutine\n"
    assert _found(code) == []


def test_suppression_without_reason_unused_and_unknown():
    code = (
        "subroutine s()\n"
        "integer :: n = 0 ! fobis: ignore[COR020]\n"
        "integer :: m ! fobis: ignore[COR020] stale\n"
        "integer :: k ! fobis: ignore[COR999] typo\n"
        "end subroutine\n"
    )
    assert _found(code) == [(2, "LNT001"), (3, "LNT002"), (4, "LNT003")]


def test_unused_suppression_of_a_rule_not_run_is_not_reported():
    code = "subroutine s()\ninteger :: m ! fobis: ignore[OBS001] not selected\nend subroutine\n"
    assert _found(code) == []


def test_preprocessor_assumption_reported_as_info():
    findings = lint_text("#if FOO(1)\n#endif\n", "t.F90", [RULES["LNT004"]])
    assert [(f.rule, f.severity) for f in findings] == [("LNT004", "info")]


# ── engine: files and baseline ─────────────────────────────────────────────────


def _project(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.f90").write_text("subroutine a()\ninteger :: n = 0\nend subroutine\n")
    (tmp_path / "src" / "b.F").write_text("      SUBROUTINE B\n      COMMON /C/ X\n      END\n")
    (tmp_path / "src" / "notes.txt").write_text("not fortran\n")
    (tmp_path / ".fobis_deps" / "dep").mkdir(parents=True)
    (tmp_path / ".fobis_deps" / "dep" / "d.f90").write_text("subroutine d()\nend\n")
    return tmp_path


def test_discover_files_skips_fetched_dependencies(tmp_path):
    root = _project(tmp_path)
    files = discover_files([str(root)], extensions=[".f90", ".F"])
    assert [f.split("/")[-1] for f in files] == ["a.f90", "b.F"]
    assert discover_files([str(root)], extensions=[".f90", ".F"], exclude=["b.F"])[-1].endswith("a.f90")


def test_baseline_round_trip_hides_recorded_findings(tmp_path):
    root = _project(tmp_path)
    files = discover_files([str(root / "src")], extensions=[".f90", ".F"])
    rules = [RULES["COR020"], RULES["OBS001"]]
    result = lint_files(files, rules)
    assert len(result.findings) == 2
    baseline = tmp_path / "baseline.json"
    assert write_baseline(str(baseline), result.findings) == 2
    # a line shift does not invalidate the baseline: fingerprints ignore line numbers
    (root / "src" / "a.f90").write_text("subroutine a()\n! moved\ninteger :: n = 0\ninteger :: k = 1\nend subroutine\n")
    again = lint_files(files, rules)
    apply_baseline(again, load_baseline(str(baseline)))
    assert again.baselined == 2
    assert [(f.rule, f.line) for f in again.findings] == [("COR020", 4)]


def test_load_baseline_missing_and_invalid(tmp_path):
    assert not load_baseline(str(tmp_path / "none.json"))
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(ValueError, match="invalid lint baseline"):
        load_baseline(str(bad))


# ── reports ────────────────────────────────────────────────────────────────────


def _result() -> LintResult:
    code = "subroutine s()\ninteger :: n = 0\ncommon /c/ x\nend subroutine\n"
    findings = lint_text(code, "src/s.f90", select_rules(["COR020", "OBS001"]))
    return LintResult(findings=findings, files=1)


def test_render_text():
    text = render(_result(), "text")
    assert "src/s.f90:2: COR020 [warning]" in text
    assert "2 finding(s) in 1 file(s): COR020 x1, OBS001 x1" in text


def test_render_json():
    data = json.loads(render(_result(), "json"))
    assert [f["rule"] for f in data["findings"]] == ["COR020", "OBS001"]
    assert data["findings"][0]["name"] == "initialisation-in-declaration"


def test_render_sarif():
    log = json.loads(render(_result(), "sarif"))
    run = log["runs"][0]
    assert log["version"] == "2.1.0"
    assert [r["id"] for r in run["tool"]["driver"]["rules"]] == ["COR020", "OBS001"]
    first = run["results"][0]
    assert first["ruleId"] == "COR020" and first["level"] == "warning"
    assert first["locations"][0]["physicalLocation"]["region"]["startLine"] == 2
    assert first["partialFingerprints"]["fobisLint/v1"]


def test_render_github():
    lines = render(_result(), "github").splitlines()
    assert lines[0].startswith("::warning file=src/s.f90,line=2,endLine=2,title=COR020 initialisation-in-declaration::")


# ── CLI ────────────────────────────────────────────────────────────────────────


def _cli_project(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "m.F90").write_text(
        "module m\nimplicit none\nprivate\ncontains\nsubroutine s(n)\ninteger :: n\n"
        "#ifdef USE_MPI\ninclude 'mpif.h'\n#else\ncommon /c/ x\n#endif\nend subroutine s\nend module m\n"
    )
    (tmp_path / "fobos").write_text(
        "[modes]\nmodes = gnu\n\n[gnu]\ncompiler = gnu\ncflags = -c -DUSE_MPI\nsrc = ./src/\n\n[lint]\nignore = COR040\n"
    )
    monkeypatch.chdir(tmp_path)


def _run(args, capsys) -> tuple[int, str]:
    try:
        run_fobis(fake_args=["lint", *args])
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    return code, capsys.readouterr().out


def test_cli_lint_uses_mode_defines_and_lint_section(tmp_path, monkeypatch, capsys):
    _cli_project(tmp_path, monkeypatch)
    code, out = _run([], capsys)
    assert code == 1
    assert "src/m.F90:6: COR010" in out and "src/m.F90:8: OBS020" in out
    assert "OBS001" not in out  # the #else branch is not compiled in mode gnu


def test_cli_baseline_update_then_clean_run(tmp_path, monkeypatch, capsys):
    _cli_project(tmp_path, monkeypatch)
    code, _ = _run(["--update-baseline"], capsys)
    assert code == 0 and (tmp_path / ".fobis-lint-baseline.json").exists()
    code, out = _run([], capsys)
    assert code == 0
    assert "2 hidden by the baseline" in out


def test_cli_exit_zero_select_and_format(tmp_path, monkeypatch, capsys):
    _cli_project(tmp_path, monkeypatch)
    code, out = _run(["--select", "OBS", "--format", "json", "--exit-zero"], capsys)
    assert code == 0
    assert [f["rule"] for f in json.loads(out)["findings"]] == ["OBS020"]


def test_cli_list_and_explain(tmp_path, monkeypatch, capsys):
    _cli_project(tmp_path, monkeypatch)
    code, out = _run(["--list-rules"], capsys)
    assert code == 0 and "COR020  initialisation-in-declaration" in out
    code, out = _run(["--explain", "cor020"], capsys)
    assert code == 0 and "save attribute" in out.lower()
    code, _ = _run(["--explain", "NOPE01"], capsys)
    assert code == 1


def test_cli_rejects_unknown_selector_and_format(tmp_path, monkeypatch, capsys):
    _cli_project(tmp_path, monkeypatch)
    assert _run(["--select", "XYZ"], capsys)[0] == 1
    assert _run(["--format", "xml"], capsys)[0] == 1
