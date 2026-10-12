"""Tests for ``fobis run --explain`` / ``fobis test --explain``: parsing the GENUINE runtime failures of
tests/run-explain/ (gfortran 16, ifx 2025.3, nvfortran 26.5; each program built with a debug and an -O3 build),
the optimisation rules, the deterministic notes, the bundle, and real gfortran runs (the model is a FakeProvider)."""

from __future__ import annotations

import configparser
import json
import os
import shutil
from types import SimpleNamespace

import pytest

from fobis.ai.crash import (
    BACKTRACES_LIE,
    GFORTRAN_EFAULT,
    NVFORTRAN_719,
    ModeInfo,
    RunContext,
    build_bundle,
    classify_crash,
    explain_crash,
    mode_infos,
    optimisation,
    parse_crash,
    render_notes,
    trusted_location,
)
from fobis.ai.explain import KINDS, BuildFacts
from fobis.ai.grounding import claims_schema, load_prompt
from fobis.fobis import run_fobis
from fobis.llm import FakeProvider

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run-explain")
SOURCES = ["kernels.f90", "segv.f90", "bounds.f90", "alloc.f90", "fpe.f90", "stop.f90"]
# Exit status of each capture as subprocess reports it (negative: killed by that signal); by case, then overrides
EXIT = {"segv": -11, "bounds": 2, "alloc": 2, "fpe": -8, "stop": 1}
EXIT_OVERRIDES = {
    "intel-debug-segv": 152,
    "intel-debug-bounds": 152,
    "intel-opt-segv": 174,
    "intel-debug-alloc": 151,
    "intel-opt-alloc": 151,
    "intel-debug-fpe": -6,
    "intel-debug-stop": 128,
    "intel-opt-stop": 128,
    "nv-debug-segv": 127,
    "nv-debug-bounds": 127,
    "nv-debug-alloc": 127,
    "nv-opt-alloc": 127,
}
MODES = {
    "gnu-debug": ModeInfo("gnu-debug", "gnu", "-c -O0 -g -fcheck=all -fbacktrace"),
    "gnu-opt": ModeInfo("gnu-opt", "gnu", "-c -O3"),
    "intel-debug": ModeInfo("intel-debug", "intel_nextgen", "-c -O0 -g -traceback -check all"),
    "intel-opt": ModeInfo("intel-opt", "intel_nextgen", "-c -O3"),
    "nv-debug": ModeInfo("nv-debug", "nvfortran", "-c -O0 -g -Mbounds -traceback"),
    "nv-opt": ModeInfo("nv-opt", "nvfortran", "-c -O3"),
}


def _crash(name: str):
    with open(os.path.join(FIXTURE, f"{name}.txt"), encoding="utf-8") as handle:
        return parse_crash(handle.read(), EXIT_OVERRIDES.get(name) or EXIT[name.split("-")[-1]])


@pytest.fixture
def facts(monkeypatch) -> BuildFacts:
    monkeypatch.chdir(FIXTURE)
    return BuildFacts.scan(SOURCES)


def _ctx(facts: BuildFacts, mode: str, modes=None) -> RunContext:
    return RunContext(MODES[mode], list(MODES.values()) if modes is None else modes, facts)


def _answer(kind: str, text: str) -> str:
    return json.dumps({"insufficient": False, "claims": [{"kind": kind, "text": text, "citations": ["S1"]}]})


# ── parsing ────────────────────────────────────────────────────────────────────


def test_parse_gfortran_debug():
    bounds = _crash("gnu-debug-bounds")
    assert (bounds.tool, bounds.kind, bounds.file, bounds.line) == ("gnu", "bounds", "kernels.f90", 18)
    assert bounds.detail == {"array": "a", "index": "11", "bound": "10", "side": "upper", "dim": "1"}
    assert [(f.function, f.line) for f in bounds.located_frames] == [("smooth", 18), ("bounds", 6), ("main", 2)]
    assert bounds.located_frames[0].file == "kernels.f90"  # scratch path stripped from the genuine log
    fpe = _crash("gnu-debug-fpe")
    assert (fpe.kind, fpe.file, fpe.signal) == ("fpe", None, "SIGFPE")
    assert fpe.located_frames[0].line == 5  # "at .../libc_sigaction.c:0" is not a Fortran frame
    stop = _crash("gnu-debug-stop")
    assert (stop.kind, stop.message) == ("error-stop", "negative density")


def test_parse_optimised_builds_have_no_located_frames():
    for name in ("gnu-opt-segv", "gnu-opt-alloc", "intel-opt-segv", "intel-opt-alloc"):
        assert _crash(name).located_frames == []
    segv = _crash("gnu-opt-segv")
    assert (segv.kind, segv.message) == ("segv", "SIGSEGV: Segmentation fault - invalid memory reference.")
    alloc = _crash("gnu-opt-alloc")  # gfortran's runtime message keeps the line even at -O3
    assert (alloc.kind, alloc.file, alloc.line) == ("allocation", "alloc.f90", 6)


def test_parse_intel():
    segv = _crash("intel-debug-segv")
    assert (segv.tool, segv.kind, segv.detail["array"], segv.detail["code"]) == ("intel", "pointer", "p", "408")
    assert segv.message == "Attempt to use pointer P when it is not associated with a target"
    assert (segv.file, segv.line) == ("kernels.f90", 9)  # from the innermost traceback row
    bounds = _crash("intel-debug-bounds")
    assert (bounds.detail["index"], bounds.detail["bound"], bounds.detail["side"]) == ("11", "10", "upper")
    assert _crash("intel-debug-fpe").kind == "fpe"
    stop = _crash("intel-debug-stop")  # ifx prints the error stop message alone
    assert (stop.tool, stop.kind, stop.message) == ("unknown", "exit", "negative density")


def test_parse_nvfortran():
    bounds = _crash("nv-debug-bounds")
    assert (bounds.tool, bounds.kind, bounds.file, bounds.line) == ("nvfortran", "bounds", "kernels.f90", 18)
    assert (bounds.detail["side"], bounds.detail["bound"]) == ("upper", "10")
    segv = _crash("nv-debug-segv")  # an unassociated pointer: bounds 0:-1
    assert (segv.detail["upper"], segv.detail["array"]) == ("-1", "p")
    fpe = _crash("nv-debug-fpe")  # nvfortran prints nothing when it traps
    assert (fpe.kind, fpe.message) == ("fpe", "killed by SIGFPE, with no runtime message")
    assert _crash("nv-opt-segv").kind == "segv" and _crash("nv-debug-stop").kind == "error-stop"
    assert parse_crash("anything", 0) is None


def test_parse_timeout_and_unknown():
    assert parse_crash("TIMEOUT after 60.0s", -1).kind == "timeout"
    other = parse_crash("something went wrong\n", 3)
    assert (other.kind, other.message) == ("exit", "something went wrong")


# ── the build ──────────────────────────────────────────────────────────────────


def test_optimisation():
    assert optimisation("gnu", "-c") == (0, False, False)
    assert optimisation("gnu", "-c -O3 -g") == (3, True, False)
    assert optimisation("gnu", "-O2 -O0 -g -fcheck=all") == (0, True, True)  # the last -O wins
    assert optimisation("gnu", "-Ofast")[0] == 3 and optimisation("gnu", "-Os")[0] == 2
    assert optimisation("intel_nextgen", "-c") == (2, False, False)  # Intel's default is -O2
    assert optimisation("intel_nextgen", "-g -check all") == (0, True, True)  # ... and -O0 with -g
    assert optimisation("nvfortran", "-c")[0] == 1
    assert optimisation("nvfortran", "-fast -Mbounds") == (3, False, True)


def test_mode_infos_substitute_variables_and_profiles():
    parser = configparser.RawConfigParser()
    parser.optionxform = str
    parser.read_string(
        "[modes]\nmodes = rel dbg\n[rel]\ncompiler = Intel_NextGen\ncflags = -c $OPT\n"
        "[dbg]\nbuild_profile = debug\ncflags = -c\n"
    )
    rel, dbg = mode_infos(SimpleNamespace(fobos=parser, local_variables={"$OPT": "-O3 -xHost"}))
    assert rel == ModeInfo("rel", "intel_nextgen", "-c -O3 -xHost") and rel.family == "intel"
    assert dbg.compiler == "gnu" and optimisation(dbg.compiler, dbg.cflags)[:2] == (0, True)
    assert mode_infos(SimpleNamespace(fobos=None)) == []


def test_debug_mode_prefers_same_compiler(facts):
    assert _ctx(facts, "intel-opt").debug_mode().name == "intel-debug"
    assert _ctx(facts, "gnu-opt").debug_mode().name == "gnu-debug"
    assert _ctx(facts, "gnu-opt", [MODES["gnu-opt"]]).debug_mode() is None


# ── deterministic notes ────────────────────────────────────────────────────────


def test_bounds_in_debug_build(facts):
    notes, ask = classify_crash(_crash("gnu-debug-bounds"), _ctx(facts, "gnu-debug"))
    assert ask and len(notes) == 1
    assert notes[0].summary == "index 11 of array a is above its upper bound 10 at kernels.f90:18"
    assert notes[0].facts[1:] == [
        "statement: a(i) = 0.5 * (a(i) + a(i + 1))",
        "declaration: real, intent(inout) :: a(:) (kernels.f90:14)",
        "a is a dummy argument of smooth: the caller passes it, called from bounds.f90:6.",
    ]


def test_unassociated_pointer(facts):
    for name, mode in (("gnu-debug-segv", "gnu-debug"), ("nv-debug-segv", "nv-debug")):
        notes, _ = classify_crash(_crash(name), _ctx(facts, mode))
        assert any("p is a pointer and its bounds are empty" in f for f in notes[0].facts), name
    notes, ask = classify_crash(_crash("intel-debug-segv"), _ctx(facts, "intel-debug"))
    assert ask and notes[0].summary == "use of a pointer that is not associated at kernels.f90:9"


def test_error_stop_is_traced_to_its_statement(facts):
    for name, mode in (("gnu-opt-stop", "gnu-opt"), ("intel-debug-stop", "intel-debug"), ("nv-debug-stop", "nv-debug")):
        notes, ask = classify_crash(_crash(name), _ctx(facts, mode))
        assert not ask and [n.kind for n in notes] == ["error-stop"], name
        assert notes[0].summary == "the program stopped itself: error stop at stop.f90:5"
        assert notes[0].facts == ["statement: if (rho < 0.0) error stop 'negative density'"]


def test_optimised_build_is_not_explained_from_frames(facts):
    notes, ask = classify_crash(_crash("gnu-opt-segv"), _ctx(facts, "gnu-opt"))
    assert not ask and [n.kind for n in notes] == ["segv", "optimised-build"]
    note = notes[1]
    assert note.summary == "mode gnu-opt is optimised (-O3), without debug information (-g), without runtime checks"
    assert note.advice == ["reproduce it in a debug build first: fobis run --mode gnu-debug --explain"]
    assert note.refs == [BACKTRACES_LIE] and "located message" in note.facts[1]
    notes, ask = classify_crash(_crash("intel-opt-segv"), _ctx(facts, "intel-opt", [MODES["intel-opt"]]))
    assert not ask and "-O0 -g -traceback -check all -fpe0" in notes[1].advice[0]  # no debug mode in fobos


def test_optimised_build_with_a_located_runtime_message(facts):
    crash = _crash("gnu-opt-alloc")
    ctx = _ctx(facts, "gnu-opt")
    assert trusted_location(crash, ctx) == ("alloc.f90", 6)  # the runtime message's own line
    notes, ask = classify_crash(crash, ctx)
    assert ask and notes[0].facts[1] == "statement: allocate(x(20))"
    assert notes[1].facts[0].startswith("the location comes from the runtime message itself")
    assert trusted_location(_crash("intel-opt-alloc"), _ctx(facts, "intel-opt")) is None


def test_no_location_in_a_debug_build_advises_a_debugger(facts):
    notes, ask = classify_crash(_crash("nv-debug-alloc"), _ctx(facts, "nv-debug"))
    assert not ask and "gdb --args" in notes[0].advice[0]
    notes, ask = classify_crash(_crash("gnu-debug-fpe"), _ctx(facts, "gnu-debug"))  # located by its frame
    assert ask and notes[0].summary == "floating-point exception at fpe.f90:5"


def test_known_gfortran_efault(facts):
    crash = parse_crash("HDF5-DIAG: Error detected\n  errno = 14, error message = 'Bad address'\n", 1)
    notes, ask = classify_crash(crash, RunContext(ModeInfo("rel", "gnu", "-O2"), [], facts))
    assert not ask and notes[-1].refs == [GFORTRAN_EFAULT]
    notes, _ = classify_crash(crash, RunContext(ModeInfo("dbg", "gnu", "-O0 -g"), [], facts))
    assert all(n.kind != "compiler-bug" for n in notes)  # not at -O0


def test_known_nvfortran_719(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "res.f90").write_text(
        "module res\nimplicit none\nreal, allocatable :: l2(:)\n!$acc declare create(l2)\ncontains\n"
        "subroutine norm(q, n)\nreal, intent(in) :: q(:)\ninteger, intent(in) :: n\ninteger :: i\n"
        "!$acc parallel loop reduction(+:l2(1:n))\ndo i = 1, n\nl2(1) = l2(1) + q(i)\nend do\n"
        "end subroutine norm\nend module res\n"
    )
    facts = BuildFacts.scan(["res.f90"])
    crash = parse_crash("Failing in Thread:1\ncall to cuLaunchKernel returned error 719: Launch failed\n", 1)
    notes, ask = classify_crash(crash, RunContext(ModeInfo("gpu", "nvfortran", "-acc -fast"), [], facts))
    bug = notes[-1]
    assert not ask and bug.refs == [NVFORTRAN_719] and bug.facts == ["reduction into l2 at res.f90:10"]
    assert "see: fobis kb show " + NVFORTRAN_719 in render_notes(notes)


# ── grounded explanation ───────────────────────────────────────────────────────


def test_bundle_has_failing_line_and_caller(facts):
    bundle = build_bundle(_crash("gnu-debug-bounds"), _ctx(facts, "gnu-debug"), kb=None)
    assert [s.id for s in bundle.sources] == [
        "code:kernels.f90:12-21",
        "fact:kernels.f90#smooth",
        "code:bounds.f90:1-8",
        "fact:bounds.f90#bounds",
    ]
    assert "18 >   a(i) = 0.5 * (a(i) + a(i + 1))" in bundle.sources[0].text
    assert "6 > call smooth(a, 10)" in bundle.sources[2].text and bundle.sources[2].title.endswith("(caller)")
    assert "optimisation -O0, debug information: yes, runtime checks: yes" in bundle.sections[1][1]


def test_bundle_of_an_optimised_build_has_no_caller(facts):
    bundle = build_bundle(_crash("gnu-opt-alloc"), _ctx(facts, "gnu-opt"), kb=None)
    assert [s.id for s in bundle.sources] == ["code:alloc.f90:1-8", "fact:alloc.f90#alloc"]


def test_explain_crash_request(facts):
    bundle = build_bundle(_crash("gnu-debug-bounds"), _ctx(facts, "gnu-debug"), kb=None)
    provider = FakeProvider([_answer("cause", "i + 1 reaches 11.")])
    result = explain_crash(bundle, provider)
    call = provider.calls[0]
    assert call.messages[0]["content"] == load_prompt("crash")
    assert call.schema == claims_schema(bundle.labels, kinds=KINDS)
    assert [c.kind for c in result.claims] == ["cause"]


# ── run / test integration (real gfortran builds and runs) ─────────────────────

FOBOS = (
    "[modes]\nmodes = opt debug\n\n"
    "[opt]\ncompiler = gnu\ncflags = -c -O3\nsrc = ./src/\nbuild_dir = ./build-opt/\ntarget = {target}\n"
    "output = prog\n\n"
    "[debug]\ncompiler = gnu\ncflags = -c -O0 -g -fcheck=all -fbacktrace\nsrc = ./src/\nbuild_dir = ./build-dbg/\n"
    "target = {target}\noutput = prog\n"
)


@pytest.fixture
def model(monkeypatch, tmp_path):
    replies: list[str] = []
    provider = FakeProvider(lambda messages: replies.pop(0))
    monkeypatch.setattr("fobis.llm.get_provider", lambda cfg, on_status=None: provider)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    return replies, provider


def _project(tmp_path, monkeypatch, target: str) -> None:
    (tmp_path / "src").mkdir()
    for name in ("kernels.f90", target):
        shutil.copy(os.path.join(FIXTURE, name), tmp_path / "src" / name)
    (tmp_path / "fobos").write_text(FOBOS.format(target=target))
    monkeypatch.chdir(tmp_path)


def test_run_explain_debug_build_asks_the_model(tmp_path, monkeypatch, capsys, model):
    replies, provider = model
    _project(tmp_path, monkeypatch, "bounds.f90")
    replies.append(_answer("cause", "a(i + 1) reaches 11."))
    with pytest.raises(SystemExit) as caught:
        run_fobis(fake_args=["run", "--mode", "debug", "--explain"])
    out = capsys.readouterr().out
    assert caught.value.code == 2
    assert "index 11 of array a is above its upper bound 10 at src/kernels.f90:18" in out
    assert "Cause:\n    - a(i + 1) reaches 11. [1]" in out
    assert "src/bounds.f90 lines 1-8 (caller)" in provider.calls[0].messages[1]["content"]


def test_run_explain_optimised_build_names_the_debug_mode(tmp_path, monkeypatch, capsys, model):
    _project(tmp_path, monkeypatch, "segv.f90")
    with pytest.raises(SystemExit) as caught:
        run_fobis(fake_args=["run", "--explain"])
    out = capsys.readouterr().out
    assert caught.value.code != 0
    assert "mode opt is optimised (-O3), without debug information (-g), without runtime checks" in out
    assert "fix: reproduce it in a debug build first: fobis run --mode debug --explain" in out
    assert model[1].calls == []


def test_run_explain_context(tmp_path, monkeypatch, capsys, model):
    _project(tmp_path, monkeypatch, "bounds.f90")
    with pytest.raises(SystemExit):
        run_fobis(fake_args=["run", "--mode", "debug", "--explain-context"])
    out = capsys.readouterr().out
    assert "=== system prompt ===" in out and "## Runtime error" in out and model[1].calls == []


def test_test_explain(tmp_path, monkeypatch, capsys, model):
    replies, provider = model
    (tmp_path / "test").mkdir()
    shutil.copy(os.path.join(FIXTURE, "kernels.f90"), tmp_path / "kernels.f90")
    shutil.copy(os.path.join(FIXTURE, "bounds.f90"), tmp_path / "test" / "test_bounds.f90")
    shutil.copy(os.path.join(FIXTURE, "stop.f90"), tmp_path / "test" / "test_stop.f90")
    (tmp_path / "fobos").write_text(
        "[modes]\nmodes = debug\n\n[debug]\ncompiler = gnu\ncflags = -c -O0 -g -fcheck=all -fbacktrace\n"
        "src = ./\nbuild_dir = ./build/\n"
    )
    monkeypatch.chdir(tmp_path)
    replies.append(json.dumps({"insufficient": True, "claims": []}))
    with pytest.raises(SystemExit) as caught:
        run_fobis(fake_args=["test", "--explain"])
    out = capsys.readouterr().out
    assert caught.value.code == 1
    assert "Explanation of test bounds (fobis test --explain)" in out
    assert "the program stopped itself: error stop at test/test_stop.f90:5" in out
    assert len(provider.calls) == 1  # the model is asked for the first failure only
