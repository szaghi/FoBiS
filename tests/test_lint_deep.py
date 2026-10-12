"""Tests for ``fobis lint --deep`` and ``fobis lint --ask``: grouping findings by region, the review bundle, the
review schema and its check (no uncited verdict, nothing hidden), rendering, and the CLI (FakeProvider only)."""

from __future__ import annotations

import json
import os

import pytest

from fobis.ai.deep import (
    MECHANICAL_FAMILIES,
    DeepReport,
    annotations,
    build_bundle,
    check_review,
    group_findings,
    locate,
    parse_location,
    review,
    review_schema,
    to_json,
)
from fobis.ai.grounding import load_prompt
from fobis.fobis import run_fobis
from fobis.kb import KnowledgeBase
from fobis.lint import lint_files, select_rules
from fobis.llm import FakeProvider, LLMError

FEEDBACK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "compiler-feedback")
HEAT = """\
module heat
implicit none
contains
subroutine step(u, unew, n, total)
real, intent(in) :: u(:)
real, intent(out) :: unew(:)
integer, intent(in) :: n
real, intent(out) :: total
integer :: i
real :: flux
total = 0.0
!$omp parallel do
do i = 2, n - 1
  flux = u(i + 1) - 2.0 * u(i) + u(i - 1)
  unew(i) = u(i) + 0.1 * flux
  total = total + unew(i)
end do
!$omp end parallel do
call report(total)
end subroutine step

subroutine report(x)
real, intent(in) :: x
if (x .eq. 0.0) print *, x
end subroutine report
end module heat
"""


@pytest.fixture
def heat(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "heat.f90").write_text(HEAT)
    return lint_files(["heat.f90"], select_rules(["ALL"]))


def _verdict(label, verdict, reason, citations):
    return {"finding": label, "verdict": verdict, "reason": reason, "citations": citations}


def _reply(verdicts=(), concerns=()):
    return json.dumps({"verdicts": list(verdicts), "concerns": list(concerns)})


# ── groups ─────────────────────────────────────────────────────────────────────


def test_groups_regions_first_and_mechanical_families_skipped(heat):
    groups = group_findings(heat)
    assert groups[0].title == "!$omp parallel do (line 12)" and (groups[0].first, groups[0].last) == (12, 17)
    assert [f.rule for _, f in groups[0].findings] == ["OMP001", "OMP002"] and groups[0].labels == ["F1", "F2"]
    reviewed = {f.rule for g in groups for _, f in g.findings}
    assert not any(r.startswith(MECHANICAL_FAMILIES) for r in reviewed)
    assert any(f.rule.startswith(MECHANICAL_FAMILIES) for f in heat.findings)  # reported, just not reviewed
    assert all(g.region is None for g in groups[1:])


def test_locate_long_procedures_by_window(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    body = "\n".join(f"x = x + {i}" for i in range(200))
    (tmp_path / "long.f90").write_text(f"subroutine long(x)\nreal :: x\n{body}\nend subroutine long\n")
    result = lint_files(["long.f90"], select_rules(["ALL"]))
    group = locate(result.units["long.f90"], "long.f90", 100)
    assert (group.first, group.last, group.title) == (85, 115, "subroutine long")
    assert locate(result.units["long.f90"], "long.f90", 1).first == 1


def test_parse_location():
    assert parse_location("src/flux.F90:120") == ("src/flux.F90", 120)
    assert parse_location("src") == ("src", None)


# ── bundle ─────────────────────────────────────────────────────────────────────


def test_bundle_of_a_region(heat):
    group = group_findings(heat)[0]
    bundle = build_bundle(group, heat.units, heat.project, KnowledgeBase.load())
    ids = [s.id for s in bundle.sources]
    assert ids[:4] == ["code:heat.f90:12-17", "fact:heat.f90#step", "rule:OMP001", "rule:OMP002"]
    assert "openmp:ch07-data-environment#frameworks-introduced" in ids  # OMP002's pack reference
    assert "14 >   flux = u(i + 1) - 2.0 * u(i) + u(i - 1)" in bundle.sources[0].text
    assert "13 | do i = 2, n - 1" in bundle.sources[0].text
    findings = dict(bundle.sections)["Findings of the rules"]
    assert findings.startswith("F1 OMP001 shared-scalar-written-in-parallel-region [warning] line 14:")


def test_bundle_of_a_procedure_has_called_interfaces(heat):
    group = locate(heat.units["heat.f90"], "heat.f90", 19)
    assert group.title == "subroutine step"
    bundle = build_bundle(group, heat.units, heat.project, kb=None, question="is total right?")
    assert bundle.sections[0] == ("Question", "is total right?")
    interface = next(s for s in bundle.sources if s.id == "fact:heat.f90#report")
    assert interface.text.splitlines() == ["subroutine report(x)", "real, intent(in) :: x"]


def test_bundle_has_compiler_feedback(monkeypatch):
    monkeypatch.chdir(FEEDBACK)
    with open("nvfortran-build.txt") as handle:
        log = handle.read()
    result = lint_files(["src/kernels.f90", "src/main.f90"], select_rules(["ACC", "OMP"]), feedback=log)
    group = next(g for g in group_findings(result) if any(f.rule == "ACC001" for _, f in g.findings))
    bundle = build_bundle(group, result.units, result.project, kb=None, feedback=result.feedback[group.path])
    feedback = next(s for s in bundle.sources if s.id == "feedback:src/kernels.f90")
    assert "Generating implicit copy" in feedback.text


# ── review ─────────────────────────────────────────────────────────────────────


def test_review_schema_uses_enums():
    schema = review_schema(["F1", "F2"], ["S1", "S2", "S3"])
    verdict = schema["properties"]["verdicts"]["items"]["properties"]
    assert verdict["finding"]["enum"] == ["F1", "F2"]
    assert verdict["verdict"]["enum"] == ["confirmed", "dismissed", "uncertain"]
    assert verdict["citations"]["items"]["enum"] == ["S1", "S2", "S3"]
    assert schema["properties"]["concerns"]["items"]["required"] == ["line", "text", "citations"]


def test_check_review(heat):
    group = group_findings(heat)[0]
    bundle = build_bundle(group, heat.units, heat.project, kb=None)
    first, second = (index for index, _ in group.findings)
    raw = _reply(
        [
            _verdict("F1", "dismissed", "flux is a temporary.", []),  # dismissed without a citation
            _verdict("F2", "confirmed", "total is summed by all threads.", ["S1", "S4"]),
            _verdict("F2", "dismissed", "duplicate, ignored", ["S1"]),
            _verdict("F9", "confirmed", "unknown finding", ["S1"]),
        ],
        [
            {"line": 15, "text": "unew(i) reads flux of another thread.", "citations": ["S1"]},
            {"line": 99, "text": "outside the code: line dropped", "citations": ["S3"]},
            {"line": 14, "text": "uncited concern", "citations": []},
        ],
    )
    result = check_review(raw, group, bundle)
    assert result.verdicts[first].verdict == "uncertain" and result.verdicts[first].uncited
    assert result.verdicts[second].verdict == "confirmed"
    assert [s.id for s in result.verdicts[second].sources] == ["code:heat.f90:12-17", "rule:OMP002"]
    assert [(c.line, c.text) for c in result.concerns] == [
        (15, "unew(i) reads flux of another thread."),
        (None, "outside the code: line dropped"),
    ]
    assert result.dropped == ["uncited concern"]
    nothing = check_review("I think it is fine.", group, bundle)
    assert {v.verdict for v in nothing.verdicts.values()} == {"uncertain"}
    assert nothing.verdicts[first].reason == "not reviewed by the model"


def test_review_request(heat):
    group = group_findings(heat)[0]
    bundle = build_bundle(group, heat.units, heat.project, kb=None)
    provider = FakeProvider([_reply([_verdict("F1", "confirmed", "race on flux", ["S1"])])])
    result = review(group, bundle, provider)
    call = provider.calls[0]
    assert call.messages[0]["content"] == load_prompt("deep") and call.options["temperature"] == 0.0
    assert call.schema == review_schema(group.labels, bundle.labels)
    assert result.verdicts[group.findings[0][0]].verdict == "confirmed"


def test_annotations_and_json(heat):
    group = group_findings(heat)[0]
    bundle = build_bundle(group, heat.units, heat.project, kb=None)
    report = DeepReport(groups=3)
    raw = _reply(
        [_verdict("F1", "confirmed", "race on flux", ["S1"]), _verdict("F2", "dismissed", "no", [])],
        [{"line": 15, "text": "flux read", "citations": ["S2"]}],
    )
    report.add(check_review(raw, group, bundle))
    notes, tail = annotations(report)
    first, second = (index for index, _ in group.findings)
    assert notes[first] == ["    [llm] confirmed: race on flux [1]"]
    assert notes[second] == ["    [llm] uncertain (no valid citation): no"]
    text = "\n".join(tail)
    assert "  heat.f90:15: flux read [2]" in text and "[1] heat.f90 lines 12-17" in text
    assert "Review [llm]: 1 of 3 group(s); 1 confirmed, 0 dismissed, 1 uncertain." in text
    assert "Raise --deep-max" in text
    per_finding, top = to_json(report)
    assert per_finding[first] == {
        "verdict": "confirmed",
        "reason": "race on flux",
        "sources": ["code:heat.f90:12-17"],
        "uncited": False,
    }
    assert top["concerns"][0]["line"] == 15 and top["reviewed"] == 1


# ── CLI ────────────────────────────────────────────────────────────────────────


@pytest.fixture
def model(monkeypatch, tmp_path):
    replies: list = []

    def answer(messages):
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    provider = FakeProvider(answer)
    monkeypatch.setattr("fobis.llm.get_provider", lambda cfg, on_status=None: provider)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    (tmp_path / "heat.f90").write_text(HEAT)
    monkeypatch.chdir(tmp_path)
    return replies, provider


def _run(args, capsys) -> tuple[int, str]:
    try:
        run_fobis(fake_args=["lint", *args])
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    return code, capsys.readouterr().out


def test_cli_deep_annotates_and_keeps_the_exit_status(model, capsys):
    replies, provider = model
    replies.append(
        _reply(
            [
                _verdict("F1", "dismissed", "flux could be private.", ["S1"]),
                _verdict("F2", "confirmed", "total needs reduction(+:total).", ["S1", "S4"]),
            ]
        )
    )
    code, out = _run(["heat.f90", "--select", "OMP", "--deep"], capsys)
    assert code == 1  # a dismissed finding still counts
    assert "heat.f90:14: OMP001 [warning]" in out and "    [llm] dismissed: flux could be private. [1]" in out
    assert "    [llm] confirmed: total needs reduction(+:total). [1][2]" in out
    assert "Review [llm]: 1 of 1 group(s); 1 confirmed, 1 dismissed, 0 uncertain." in out
    assert len(provider.calls) == 1


def test_cli_deep_json(model, capsys):
    replies, _ = model
    replies.append(_reply([_verdict("F1", "confirmed", "race", ["S1"])]))
    _, out = _run(["heat.f90", "--select", "OMP", "--deep", "--format", "json"], capsys)
    data = json.loads(out)
    assert data["findings"][0]["review"]["verdict"] == "confirmed"
    assert data["findings"][1]["review"]["reason"] == "not reviewed by the model"
    assert data["review"]["groups"] == 1


def test_cli_deep_context_and_max(model, capsys):
    _, provider = model
    _, out = _run(["heat.f90", "--deep-context"], capsys)
    assert "=== system prompt ===" in out and "=== review of !$omp parallel do (line 12) in heat.f90 ===" in out
    assert provider.calls == []
    _, out = _run(["heat.f90", "--deep-context", "--deep-max", "1"], capsys)
    assert out.count("=== review of") == 1 and "more group(s) not shown" in out


def test_cli_deep_without_a_model(model, capsys):
    replies, _ = model
    replies.append(LLMError("no runtime installed"))
    code, out = _run(["heat.f90", "--select", "OMP", "--deep"], capsys)
    assert code == 1 and "heat.f90:14: OMP001" in out
    assert "Review [llm]: 0 of 1 group(s)" in out


def test_cli_deep_other_formats_are_not_annotated(model, capsys):
    _, out = _run(["heat.f90", "--select", "OMP", "--deep", "--format", "github"], capsys)
    assert "::warning file=heat.f90" in out and model[1].calls == []


def test_cli_ask(model, capsys):
    replies, provider = model
    claims = [{"text": "total is shared and summed by all threads.", "citations": ["S1"]}]
    replies.append(json.dumps({"insufficient": False, "claims": claims}))
    code, out = _run(["heat.f90:16", "--ask", "is this loop race-free?"], capsys)
    assert code == 0
    assert "!$omp parallel do (line 12) in heat.f90:" in out
    assert "- total is shared and summed by all threads. [1]" in out
    assert "## Question\n\nis this loop race-free?" in provider.calls[0].messages[1]["content"]
    _, out = _run(["heat.f90:16", "--ask", "race-free?", "--deep-context"], capsys)
    assert "=== system prompt ===" in out and len(provider.calls) == 1


def test_cli_ask_needs_a_line(model, capsys):
    code, _ = _run(["heat.f90", "--ask", "race-free?"], capsys)
    assert code == 1
