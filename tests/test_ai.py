"""Tests for fobis.ai — grounding (bundle, cited claims, the citation check), retrieval routing, project facts and
``fobis ask``. All on FakeProvider: no model runs."""

from __future__ import annotations

import json
import os

import pytest
from typer.testing import CliRunner

from fobis.ai.ask import ask, build_bundle, project_pack, route_packs
from fobis.ai.grounding import (
    ContextBundle,
    Source,
    check_claims,
    claims_schema,
    load_prompt,
    render_answer,
    to_json,
)
from fobis.analysis import read_source
from fobis.kb import KnowledgeBase
from fobis.kb.search import expand, tokenize
from fobis.lint.engine import analyse
from fobis.llm import FakeProvider

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "compiler-feedback")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _bundle() -> ContextBundle:
    return ContextBundle(
        sections=[("Question", "is x private?")],
        sources=[Source("p:a#one", "One", "x is private."), Source("p:b#two", "Two", "y is shared.")],
    )


def _answer(*claims, insufficient=False) -> str:
    return json.dumps({"insufficient": insufficient, "claims": [{"text": t, "citations": c} for t, c in claims]})


# ── grounding ──────────────────────────────────────────────────────────────────


def test_bundle_renders_sections_then_labelled_sources():
    text = _bundle().render()
    assert text.index("## Question") < text.index("## Sources")
    assert "[S1] One (p:a#one)\nx is private." in text and "[S2] Two (p:b#two)" in text
    assert _bundle().render() == text  # deterministic


def test_claims_schema_restricts_citations_to_the_labels():
    schema = claims_schema(["S1", "S2"])
    assert schema["properties"]["claims"]["items"]["properties"]["citations"]["items"]["enum"] == ["S1", "S2"]
    assert claims_schema([])["required"] == ["insufficient", "claims"]


def test_check_claims_keeps_cited_and_drops_the_rest():
    raw = _answer(
        ("x is private.", ["S1"]),
        ("y is shared.", ["[s2]", "S2"]),  # lower case, brackets, duplicates tolerated
        ("z is magic.", []),
        ("w is invented.", ["S9"]),
    )
    result = check_claims(raw, _bundle())
    assert [c.text for c in result.claims] == ["x is private.", "y is shared."]
    assert [s.id for s in result.claims[1].sources] == ["p:b#two"]
    assert result.dropped == ["z is magic.", "w is invented."] and not result.insufficient
    assert [s.id for s in result.cited] == ["p:a#one", "p:b#two"]


def test_check_claims_non_json_or_insufficient():
    assert check_claims("I think it is private.", _bundle()).insufficient
    assert check_claims("I think it is private.", _bundle()).dropped == ["I think it is private."]
    assert check_claims(_answer(insufficient=True), _bundle()).insufficient
    assert check_claims("<think>hm</think>" + _answer(("x is private.", ["S1"])), _bundle()).claims


def test_render_answer_and_json():
    result = check_claims(_answer(("x is private.", ["S1"]), ("uncited", [])), _bundle())
    text = render_answer(result)
    assert text.startswith("- x is private. [1]") and "[1] One  (p:a#one)" in text
    assert "1 statement(s) without a valid citation were dropped. Show them with --verbose." in text
    assert "dropped: uncited" in render_answer(result, verbose=True)
    assert render_answer(check_claims(_answer(insufficient=True), _bundle())).startswith("The sources found do not")
    assert to_json(result) == {
        "insufficient": False,
        "claims": [{"text": "x is private.", "sources": ["p:a#one"]}],
        "dropped": ["uncited"],
        "sources": [{"id": "p:a#one", "title": "One"}],
    }


def test_prompt_template_ships():
    assert "ONLY the numbered sources" in load_prompt("ask")
    with open(os.path.join(ROOT, "pyproject.toml")) as handle:
        assert '"ai/prompts/*.md"' in handle.read()  # package data: installed wheels and the zipapp


# ── retrieval ──────────────────────────────────────────────────────────────────


def test_tokenize_folds_plurals_and_expand_adds_synonyms():
    assert tokenize("Loop variables, indices and libraries; process mpi_isends") == [
        "loop",
        "variable",
        "index",
        "library",
        "process",
        "mpi_isend",
        "mpi",
        "isend",
    ]
    assert expand(["hang", "index"]) == ["hang", "index", "deadlock", "iteration"]


def test_route_packs_by_programming_model():
    available = ["fortran-std", "hpc-practice", "openmp", "openacc", "mpi", "project"]
    assert route_packs("does !$omp atomic flush?", available) == ["openmp", "fortran-std", "hpc-practice", "project"]
    assert route_packs("MPI_Isend with OpenACC data", available)[:2] == ["openacc", "mpi"]
    assert route_packs("what is a pure procedure?", available) is None
    assert route_packs("accumulate the sum", available) is None  # "acc" only as a word
    available += ["compilers", "libraries", "numerics"]
    assert route_packs("why does ifx crash on a large automatic array?", available)[0] == "compilers"
    assert route_packs("mpirun says not enough slots", available)[0] == "libraries"
    assert route_packs("how many significant digits can I trust?", available)[0] == "numerics"


def test_synonyms_find_the_deadlock_section():
    kb = KnowledgeBase.load()
    bundle = build_bundle("why does my mpi code hang when every rank sends first?", kb, k=3)
    assert bundle.sources[0].id == "mpi:cheatsheet#avoid-deadlock"
    assert all(s.id.split(":")[0] in ("mpi", "fortran-std", "hpc-practice") for s in bundle.sources)


def test_project_pack_describes_procedures(monkeypatch):
    monkeypatch.chdir(FIXTURE)
    files = [analyse(read_source(p), p) for p in ("src/kernels.f90", "src/main.f90")]
    pack = project_pack(files)
    axpy = next(c for c in pack.chunks if c.id == "project:src/kernels.f90#axpy")
    assert axpy.heading.startswith("subroutine axpy (src/kernels.f90:")
    assert "!$acc parallel loop" in axpy.text and "arguments: n, a, x, y" in axpy.text
    kb = KnowledgeBase([*KnowledgeBase.load().packs.values(), pack])
    bundle = build_bundle("where is the axpy kernel?", kb, k=3)
    assert bundle.sources[0].id == "project:src/kernels.f90#axpy"


# ── ask ────────────────────────────────────────────────────────────────────────


def test_ask_sends_prompt_schema_and_checks_the_answer():
    provider = FakeProvider([_answer(("x is private.", ["S1"]))])
    result = ask(_bundle(), provider)
    call = provider.calls[0]
    assert call.messages[0]["content"] == load_prompt("ask") and "[S2] Two" in call.messages[1]["content"]
    assert call.schema == claims_schema(["S1", "S2"]) and call.options["temperature"] == 0.0
    assert [c.text for c in result.claims] == ["x is private."]


@pytest.fixture
def cli(monkeypatch, tmp_path):
    from fobis.cli import app

    replies: list[str] = []
    provider = FakeProvider(lambda messages: replies.pop(0))
    monkeypatch.setattr("fobis.llm.get_provider", lambda cfg, on_status=None: provider)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    return CliRunner(), app, replies, provider


def test_cli_ask_answers_with_sources(cli):
    runner, app, replies, _ = cli
    replies.append(_answer(("Use mpi_sendrecv or non-blocking calls.", ["S1"]), ("Invented.", [])))
    result = runner.invoke(app, ["ask", "why does my mpi code hang?"])
    assert result.exit_code == 0, result.output
    assert "- Use mpi_sendrecv or non-blocking calls. [1]" in result.output
    assert "(mpi:" in result.output and "1 statement(s) without a valid citation" in result.output
    replies.append(_answer(("Use mpi_sendrecv.", ["S1"])))
    data = json.loads(runner.invoke(app, ["ask", "why does my mpi code hang?", "--json"]).output)
    assert data["claims"][0]["sources"][0].startswith("mpi:")


def test_cli_ask_show_context_runs_no_model(cli):
    runner, app, _, provider = cli
    result = runner.invoke(app, ["ask", "--show-context", "-p", os.path.join(FIXTURE, "src"), "where is axpy?"])
    assert result.exit_code == 0 and "=== system prompt ===" in result.output and "subroutine axpy" in result.output
    assert provider.calls == []


def test_cli_ask_errors(cli):
    runner, app, _, provider = cli
    assert runner.invoke(app, ["ask", "   "]).exit_code == 1
    nothing = runner.invoke(app, ["ask", "zzqx qqzzv"])
    assert nothing.exit_code == 1 and "no knowledge-pack section matches" in nothing.output
    assert runner.invoke(app, ["ask", "x", "--pack", "nope"]).exit_code == 1
    assert provider.calls == []
