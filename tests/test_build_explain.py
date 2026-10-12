"""Tests for ``fobis build --explain``: parsing the GENUINE compiler/linker logs of tests/build-explain/ (gfortran 16,
ifx 2025.3, nvfortran 26.5, LFortran 0.63, GNU ld), demangling, the deterministic diagnoses, the grounded bundle,
and the build integration (real gfortran builds; the model is a FakeProvider)."""

from __future__ import annotations

import json
import os
import shutil

import pytest

from fobis.ai.diagnostics import Symbol, demangle, parse_diagnostics
from fobis.ai.explain import KINDS, BuildFacts, build_bundle, classify, explain, render_diagnoses
from fobis.ai.grounding import ContextBundle, Source, check_claims, claims_schema, load_prompt, render_answer, to_json
from fobis.fobis import run_fobis
from fobis.kb import KnowledgeBase
from fobis.llm import FakeProvider
from fobis.utils import BuildFailed, check_results

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build-explain")
SOURCES = ["geometry.f90", "semantic.f90", "linkmain.f90", "dup_a.f90", "dup_b.f90", "syntax.f90"]
MISSING_GEOMETRY = (
    "main.f90:2:5:\n\n    2 | use geometry\n      |     1\n"
    "Fatal Error: Cannot open module file \u2018geometry.mod\u2019 for reading at (1): No such file or directory\n"
)


def _log(name: str) -> str:
    with open(os.path.join(FIXTURE, name), encoding="utf-8") as handle:
        return handle.read()


def _summary(name: str) -> list[tuple]:
    return [(d.tool, d.severity, d.file, d.line, d.code, d.symbol) for d in parse_diagnostics(_log(name))]


def _answer(*claims: tuple[str, str, list[str]]) -> str:
    return json.dumps({"insufficient": False, "claims": [{"kind": k, "text": t, "citations": c} for k, t, c in claims]})


@pytest.fixture
def facts(monkeypatch) -> BuildFacts:
    monkeypatch.chdir(FIXTURE)
    return BuildFacts.scan(SOURCES, deps_dir=os.path.join(FIXTURE, "no-deps"))


# ── parsing ────────────────────────────────────────────────────────────────────


def test_parse_gfortran():
    assert _summary("gnu-semantic.txt") == [
        ("gnu", "error", "semantic.f90", 11, None, None),
        ("gnu", "error", "semantic.f90", 9, None, None),
        ("gnu", "error", "semantic.f90", 10, None, None),
        ("gnu", "error", "semantic.f90", 10, None, None),
    ]
    first = parse_diagnostics(_log("gnu-semantic.txt"))[0]
    assert first.column == 18 and first.message == "Symbol \u2018undeclared\u2019 at (1) has no IMPLICIT type"
    assert first.text.splitlines()[2] == "   11 | total = undeclared + 1.0"  # the excerpt is kept
    assert _summary("gnu-missing_mod.txt") == [("gnu", "fatal", "missing_mod.f90", 2, None, None)]
    plain = parse_diagnostics("a.f90:3:7: Error: Unexpected junk\n")  # -fdiagnostics-plain-output
    assert [(d.file, d.line, d.column, d.message) for d in plain] == [("a.f90", 3, 7, "Unexpected junk")]


def test_parse_intel_nvidia_lfortran():
    assert _summary("intel-semantic.txt")[0] == ("intel", "error", "semantic.f90", 9, "6780", "N")
    assert _summary("intel-missing_mod.txt")[0] == ("intel", "error", "missing_mod.f90", 2, "7002", "PENF")
    assert len(_summary("intel-missing_mod.txt")) == 5
    assert parse_diagnostics(_log("intel-syntax.txt"))[0].text.splitlines()[1] == "if (i > 3 then"
    assert _summary("nv-semantic.txt") == [
        ("nvfortran", "error", "semantic.f90", 10, "0187", None),
        ("nvfortran", "warning", "semantic.f90", 5, "0194", None),
        ("nvfortran", "error", "semantic.f90", 5, "0038", None),
    ]
    assert _summary("nv-missing_mod.txt") == [("nvfortran", "fatal", "missing_mod.f90", 2, "0004", None)]
    lfortran = parse_diagnostics(_log("lf-semantic.txt"))  # ANSI colours in the genuine log
    assert [(d.tool, d.file, d.line, d.column, d.message) for d in lfortran] == [
        ("lfortran", "semantic.f90", 9, 1, "Cannot assign to an intent(in) variable `n`")
    ]
    assert "\x1b" not in lfortran[0].text
    assert _summary("lf-syntax.txt") == [("lfortran", "error", "syntax.f90", 7, "syntax error", None)]


def test_parse_linkers():
    assert _summary("gnu-link.txt") == [
        ("linker", "error", "linkmain.f90", None, None, "__geometry_MOD_area"),
        ("linker", "error", "linkmain.f90", None, None, "external_thing_"),
    ]
    assert parse_diagnostics(_log("gnu-link.txt"))[0].context == "MAIN__"
    assert [d.symbol for d in parse_diagnostics(_log("intel-link.txt"))] == ["geometry_mp_area_", "external_thing_"]
    nv = parse_diagnostics(_log("nv-link.txt"))  # nvfortran objects carry line numbers
    assert [(d.line, d.symbol) for d in nv] == [(4, "geometry_area_"), (5, "external_thing_")]
    multiple = parse_diagnostics(_log("gnu-multiple.txt"))
    assert [(d.message, d.file, d.context) for d in multiple] == [
        ("multiple definition of helper_", "dup_b.f90", "mix/dup_a.o:dup_a.f90")
    ]
    assert len(parse_diagnostics(_log("intel-mixed.txt"))) == 8
    lld = parse_diagnostics("ld.lld: error: undefined symbol: foo_\n>>> referenced by a.f90\n")
    assert [d.symbol for d in lld] == ["foo_"]


def test_parse_internal_compiler_errors():
    gnu = parse_diagnostics("f951: internal compiler error: Segmentation fault\n0x1234 crash_signal\n")
    nv = parse_diagnostics("NVFORTRAN-F-0000-Internal compiler error. size_of: attempt to get size (k.f90: 3)\n")
    intel = parse_diagnostics("k.f90(12): catastrophic error #5623: **Internal compiler error: segmentation fault**\n")
    assert [d.severity for d in (*gnu, *nv, *intel)] == ["ice", "ice", "ice"]
    assert (nv[0].file, nv[0].line) == ("k.f90", 3)
    assert parse_diagnostics("random text\ncollect2: error: ld returned 1 exit status\n") == []


def test_demangle():
    assert demangle("__geometry_MOD_area") == Symbol("area", "geometry")
    assert demangle("geometry_mp_area_") == Symbol("area", "geometry")
    assert demangle("geometry_area_", {"geometry", "geo"}) == Symbol("area", "geometry")  # longest module first
    assert demangle("geometry_area_") == Symbol("geometry_area")  # no module known: an external procedure
    assert demangle("external_thing_") == Symbol("external_thing")
    assert demangle("_gfortran_st_write") == Symbol("_gfortran_st_write", fortran=False)
    assert str(Symbol("area", "geometry")) == "geometry::area"


# ── deterministic diagnoses ────────────────────────────────────────────────────


def _classify(name: str, facts: BuildFacts):
    return classify(parse_diagnostics(_log(name)), facts)


def test_missing_module_unknown_and_unfetched(facts):
    diagnoses, remaining = _classify("gnu-missing_mod.txt", facts)
    assert remaining == [] and diagnoses[0].kind == "missing-module"
    assert "not a known library module" in diagnoses[0].facts[0] and "fobis fetch" in diagnoses[0].advice[0]
    facts.dependencies = {"penf": "https://github.com/szaghi/PENF"}
    diagnoses, _ = _classify("nv-missing_mod.txt", facts)
    assert "not fetched yet: penf" in diagnoses[0].facts[1] and diagnoses[0].advice == ["run `fobis fetch`"]


def test_missing_module_consequences_are_grouped(facts):
    diagnoses, remaining = _classify("intel-missing_mod.txt", facts)
    assert len(diagnoses) == 1 and remaining == [] and len(diagnoses[0].consequences) == 4
    assert "(4 later error(s) follow from this one)" in render_diagnoses(diagnoses)


def test_missing_module_defined_in_project(facts):
    facts.built = set()
    facts.exclude_dirs = [FIXTURE]
    diag = classify(parse_diagnostics(MISSING_GEOMETRY), facts)[0][0]
    assert diag.facts[0].startswith("geometry is defined in geometry.f90, which this build does not compile")
    assert "`exclude_dirs` lists" in diag.facts[0]
    facts.built = None  # compiled by the build: a failed or stale module
    assert "which this build compiles" in classify(parse_diagnostics(MISSING_GEOMETRY), facts)[0][0].facts[0]


def test_missing_module_library_dependency_and_disabled(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "gated.F90").write_text("#ifdef WITH_GPU\nmodule gpu_kernels\nend module gpu_kernels\n#endif\n")
    dep = tmp_path / ".fobis_deps" / "PENF" / "src"
    dep.mkdir(parents=True)
    (dep / "penf.F90").write_text("module penf\nimplicit none\nend module penf\n")
    facts = BuildFacts.scan(["gated.F90"], deps_dir=".fobis_deps", defines={})

    def why(module: str):
        log = f"x.f90:1:5:\n\nFatal Error: Cannot open module file \u2018{module}.mod\u2019 for reading at (1): No such file\n"
        return classify(parse_diagnostics(log), facts)[0][0]

    assert "MPI library" in why("mpi_f08").facts[0] and "--mpi" in why("mpi_f08").advice[0]
    assert "--openmp" in why("omp_lib").advice[0]
    assert "preprocessor branch" in why("gpu_kernels").facts[0]
    assert "fetched dependency PENF" in why("penf").facts[0]


def test_undefined_references(facts):
    for log in ("gnu-link.txt", "intel-link.txt", "nv-link.txt"):
        diagnoses, remaining = _classify(log, facts)
        assert remaining == [] and [d.kind for d in diagnoses] == ["undefined-reference"] * 2
        assert diagnoses[0].summary.startswith("geometry::area is referenced (referenced from MAIN_")
        assert diagnoses[0].facts[0] == "area is defined in geometry.f90:6."
        assert diagnoses[1].facts == ["no project source or fetched dependency defines the procedure external_thing."]
    facts.built = {os.path.join(FIXTURE, n) for n in SOURCES}
    facts.linked = {os.path.join(FIXTURE, "linkmain.f90")}
    facts.target = os.path.join(FIXTURE, "linkmain.f90")
    diagnoses, _ = _classify("gnu-link.txt", facts)
    assert diagnoses[0].facts[1] == (
        "the target linkmain.f90 does not link that file: no file it links uses the module(s) geometry."
    )
    facts.built.discard(os.path.join(FIXTURE, "geometry.f90"))
    facts.src = [os.path.join(FIXTURE, "elsewhere")]
    assert "outside the source directories" in _classify("gnu-link.txt", facts)[0][0].facts[1]


def test_undefined_library_and_main(facts):
    log = (
        "x.f90:(.text+0x1): undefined reference to `mpi_init_'\n"
        "x.f90:(.text+0x9): undefined reference to `dgemm_'\n"
        "for_main.c:(.text+0x19): undefined reference to `MAIN__'\n"
    )
    diagnoses, _ = classify(parse_diagnostics(log), facts)
    assert [d.kind for d in diagnoses] == ["missing-library", "missing-library", "undefined-reference"]
    assert "MPI library" in diagnoses[0].summary and "-llapack" in diagnoses[1].advice[0]
    assert diagnoses[2].summary == "no main program is linked"


def test_wrong_runtime(facts):
    facts.compiler = "intel_nextgen"
    diagnoses, remaining = _classify("intel-mixed.txt", facts)
    assert [d.kind for d in diagnoses] == ["wrong-runtime"] and remaining == []
    assert diagnoses[0].summary == "objects compiled by gfortran are linked with Intel ifx"
    assert len(diagnoses[0].consequences) == 7 and "fobis clean" in diagnoses[0].advice[0]


def test_multiple_definition_and_ice(facts):
    diagnoses, _ = _classify("gnu-multiple.txt", facts)
    assert diagnoses[0].facts == ["helper is defined in dup_a.f90:1, dup_b.f90:1."]
    diagnoses, _ = classify(parse_diagnostics("f951: internal compiler error: in gfc_conv, at trans.cc:1\n"), facts)
    assert diagnoses[0].kind == "internal-compiler-error" and "compiler defect" in diagnoses[0].summary


def test_syntax_and_semantic_errors_are_left_to_the_model(facts):
    for log in ("gnu-syntax.txt", "intel-semantic.txt", "nv-semantic.txt", "lf-external.txt"):
        diagnoses, remaining = _classify(log, facts)
        assert diagnoses == [] and remaining and all(d.is_error for d in remaining)


# ── grounded explanation ───────────────────────────────────────────────────────


def test_bundle_has_code_declarations_and_interfaces(facts):
    mismatch = _classify("gnu-semantic.txt", facts)[1][2]  # Type mismatch in argument 'r', line 10
    bundle = build_bundle(mismatch, facts, kb=None)
    assert [s.id for s in bundle.sources] == [
        "code:semantic.f90:4-14",
        "fact:semantic.f90#bad",
        "fact:geometry.f90#area",
    ]
    assert "10 > total = area(1, 2)" in bundle.sources[0].text and "9  | n = 3" in bundle.sources[0].text
    assert bundle.sources[1].text.splitlines() == [
        "subroutine bad(n, x)",
        "integer, intent(in) :: n",
        "real, intent(in) :: x(n)",
        "real :: total",
    ]
    assert bundle.sources[2].title == "interface of function area (module geometry), geometry.f90:6"
    assert "real, intent(in) :: r" in bundle.sources[2].text
    assert bundle.sections[0][1].startswith("semantic.f90:10:8:") and "gfortran (gnu)" in bundle.sections[1][1]


def test_bundle_pack_sections_are_clipped_and_filtered(facts):
    kb = KnowledgeBase.load()
    intent = _classify("intel-semantic.txt", facts)[1][0]  # an INTENT(IN) dummy defined
    packs = [
        s for s in build_bundle(intent, facts, kb, max_chars=300).sources if not s.id.startswith(("code:", "fact:"))
    ]
    assert packs and all(len(s.text) <= 310 for s in packs) and packs[0].id.startswith("fortran-std:ch08")
    syntax = _classify("gnu-syntax.txt", facts)[1][0]  # "Missing ')'": no pack section scores enough
    assert all(s.id.startswith(("code:", "fact:")) for s in build_bundle(syntax, facts, kb).sources)


def test_explain_request_and_answer(facts):
    bundle = build_bundle(_classify("gnu-semantic.txt", facts)[1][2], facts, kb=None)
    provider = FakeProvider(
        [
            _answer(
                ("cause", "area takes a real r, line 10 passes the integers 1 and 2.", ["S1", "S3"]),
                ("fix", "Call area(1.0).", ["S3"]),
                ("fix", "Recompile with -O0.", []),
            )
        ]
    )
    result = explain(bundle, provider)
    call = provider.calls[0]
    assert call.messages[0]["content"] == load_prompt("explain") and call.options["temperature"] == 0.0
    assert call.schema == claims_schema(bundle.labels, kinds=KINDS)
    text = render_answer(result, groups={"cause": "Cause", "fix": "Fix"})
    assert text.startswith("Cause:\n  - area takes a real r") and "Fix:\n  - Call area(1.0). [2]" in text
    assert "1 statement(s) without a valid citation were dropped" in text


def test_grounding_kinds():
    item = claims_schema(["S1"], kinds=["cause", "fix"])["properties"]["claims"]["items"]
    assert item["required"] == ["kind", "text", "citations"] and item["properties"]["kind"]["enum"] == ["cause", "fix"]
    assert "kind" not in claims_schema(["S1"])["properties"]["claims"]["items"]["properties"]
    bundle = ContextBundle(sources=[Source("a", "A", "x")])
    result = check_claims(_answer(("Fix", "t", ["S1"])), bundle)
    assert result.claims[0].kind == "fix" and to_json(result)["claims"][0]["kind"] == "fix"
    other = check_claims(_answer(("note", "n", ["S1"])), bundle)  # an unknown kind goes under the last heading
    assert render_answer(other, groups={"cause": "Cause", "fix": "Fix"}).startswith("Fix:\n  - n [1]")


# ── build integration ──────────────────────────────────────────────────────────


def test_check_results_raises_build_failed():
    with pytest.raises(BuildFailed) as caught:
        check_results([[0, ""], [1, "boom\n"]])
    assert caught.value.code == 1 and caught.value.outputs == ["boom\n"] and isinstance(caught.value, SystemExit)


def _project(tmp_path, monkeypatch, files: dict[str, str], extra: str = "") -> None:
    for name, source in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if source.startswith("@"):
            shutil.copy(os.path.join(FIXTURE, source[1:]), path)
        else:
            path.write_text(source)
    fobos = f"[modes]\nmodes = gnu\n\n[gnu]\ncompiler = gnu\nsrc = ./src/\nbuild_dir = ./build/\n{extra}"
    (tmp_path / "fobos").write_text(fobos)
    monkeypatch.chdir(tmp_path)


SEMANTIC_PROJECT = {
    "src/geometry.f90": "@geometry.f90",
    "src/semantic.f90": "@semantic.f90",
    "src/p.f90": "program p\nuse semantic\nend program p\n",
}


@pytest.fixture
def model(monkeypatch, tmp_path):
    replies: list[str] = []
    provider = FakeProvider(lambda messages: replies.pop(0))
    monkeypatch.setattr("fobis.llm.get_provider", lambda cfg, on_status=None: provider)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    return replies, provider


def test_build_explain_excluded_module(tmp_path, monkeypatch, capsys, model):
    files = {"src/main.f90": "@linkmain.f90", "src/extra/geometry.f90": "@geometry.f90"}
    _project(tmp_path, monkeypatch, files, "exclude_dirs = ./src/extra/\n")
    with pytest.raises(SystemExit) as caught:
        run_fobis(fake_args=["build", "--explain"])
    out = capsys.readouterr().out
    assert caught.value.code == 1
    assert "src/main.f90:2: module geometry is not available" in out
    assert "defined in src/extra/geometry.f90, which this build does not compile: `exclude_dirs` lists" in out
    assert model[1].calls == []  # explained from facts: no model


def test_build_explain_module_not_linked(tmp_path, monkeypatch, capsys, model):
    things = (
        "module things\nimplicit none\nend module things\n\n"
        "subroutine external_thing(n)\ninteger, intent(in) :: n\nprint *, n\nend subroutine external_thing\n"
    )
    files = {"src/main.f90": "@linkmain.f90", "src/geometry.f90": "@geometry.f90", "src/things.f90": things}
    _project(tmp_path, monkeypatch, files)
    with pytest.raises(SystemExit):
        run_fobis(fake_args=["build", "--explain"])
    out = capsys.readouterr().out
    assert "link: external_thing is referenced (referenced from MAIN__) but not linked" in out
    assert "does not link that file: no file it links uses the module(s) things." in out


def test_build_explain_asks_the_model(tmp_path, monkeypatch, capsys, model):
    replies, provider = model
    _project(tmp_path, monkeypatch, SEMANTIC_PROJECT)
    replies.append(_answer(("cause", "undeclared has no declaration.", ["S1"])))
    with pytest.raises(SystemExit):
        run_fobis(fake_args=["build", "--explain"])
    out = capsys.readouterr().out
    assert "src/semantic.f90:11: Symbol \u2018undeclared\u2019 at (1) has no IMPLICIT type" in out
    assert "Cause:\n    - undeclared has no declaration. [1]" in out and "3 more error(s) not explained" in out
    assert "## Compiler message" in provider.calls[0].messages[1]["content"]


def test_build_explain_context_runs_no_model(tmp_path, monkeypatch, capsys, model):
    _project(tmp_path, monkeypatch, SEMANTIC_PROJECT)
    with pytest.raises(SystemExit):
        run_fobis(fake_args=["build", "--explain-context"])
    out = capsys.readouterr().out
    assert "=== system prompt ===" in out and "11 > total = undeclared + 1.0" in out
    assert model[1].calls == []


def test_build_without_explain_is_unchanged(tmp_path, monkeypatch, capsys, model):
    _project(tmp_path, monkeypatch, {"src/main.f90": "@linkmain.f90"})
    with pytest.raises(SystemExit) as caught:
        run_fobis(fake_args=["build"])
    assert caught.value.code == 1 and "Explanation" not in capsys.readouterr().out
