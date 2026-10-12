"""Tests for ``fobis review``: the reviewed revision (worktree, staged, base), findings on changed lines only
(legacy code stays quiet; a changed directive counts its whole region), markdown for pull requests, the risk
bundle (diff, regions, dependents of changed headers) and the CLI. Real temporary git repositories; the model is
a FakeProvider."""

from __future__ import annotations

import json
import subprocess

import pytest

from fobis.ai.change import WORKTREE
from fobis.ai.review import (
    ReviewError,
    diff_scope,
    effective_lines,
    in_scope,
    render_markdown,
    review_revision,
    risk_bundle,
    scoped_result,
)
from fobis.fobis import run_fobis
from fobis.lint import lint_files, select_rules
from fobis.llm import FakeProvider

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
!$omp parallel do private(flux) reduction(+:total)
do i = 2, n - 1
  flux = u(i + 1) - 2.0 * u(i) + u(i - 1)
  unew(i) = u(i) + 0.1 * flux
  total = total + unew(i)
end do
!$omp end parallel do
end subroutine step
end module heat
"""
LEGACY = """\
subroutine legacy(x)
real :: x
real :: y
!$omp parallel
y = x
!$omp end parallel
x = y
end subroutine legacy
"""
DRIVER = "program driver\nuse heat\nimplicit none\nend program driver\n"
CLAUSES = " private(flux) reduction(+:total)"


def _git(repo, *args) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    config = (("user.name", "t"), ("user.email", "t@t"), ("color.ui", "always"), ("commit.gpgsign", "false"))
    for key, value in config:
        _git(tmp_path, "config", key, value)
    (tmp_path / "heat.f90").write_text(HEAT)
    (tmp_path / "legacy.f90").write_text(LEGACY)
    (tmp_path / "driver.f90").write_text(DRIVER)
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "feat(heat): add the solver")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _edit(repo, name: str, old: str, new: str) -> None:
    path = repo / name
    path.write_text(path.read_text().replace(old, new))


def _lint():
    return lint_files(["heat.f90", "legacy.f90", "driver.f90"], select_rules(["OMP", "COR"]))


def _run(args, capsys) -> tuple[int, str]:
    try:
        run_fobis(fake_args=["review", *args])
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    return code, capsys.readouterr().out


# ── revision and scope ─────────────────────────────────────────────────────────


def test_review_revision(repo):
    worktree = review_revision()
    assert (worktree.diff, worktree.old, worktree.new) == (("HEAD",), "HEAD", WORKTREE)
    assert worktree.root.endswith(repo.name)
    assert review_revision(staged=True).diff == ("--cached",)
    head = _git(repo, "rev-parse", "HEAD").strip()
    base = review_revision(base="main")
    assert (base.diff, base.old, base.new) == ((head, "HEAD"), head, "HEAD")
    with pytest.raises(ReviewError, match="no merge base"):
        review_revision(base="no-such-branch")


def test_review_revision_outside_git(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ReviewError, match="not inside a git repository"):
        review_revision()


def test_only_findings_on_changed_lines(repo):
    _edit(repo, "heat.f90", "  unew(i) = u(i) + 0.1 * flux", "  unew(i) = u(i) + 0.2 * flux\n  flux = 0.0")
    scope = diff_scope(review_revision())
    result = _lint()
    assert any(f.path == "legacy.f90" for f in result.findings)  # legacy findings exist ...
    kept = in_scope(result.findings, scope, lines=effective_lines(scope, result))
    assert {result.findings[i].path for i in kept} <= {"heat.f90"}  # ... and are not reviewed
    assert scope.changed_lines == 2


def test_a_changed_directive_reviews_its_whole_region(repo):
    _edit(repo, "heat.f90", CLAUSES, "")
    scope = diff_scope(review_revision())
    result = _lint()
    assert in_scope(result.findings, scope) == []  # by the changed lines alone the race would be missed
    kept = in_scope(result.findings, scope, lines=effective_lines(scope, result))
    assert sorted(result.findings[i].rule for i in kept) == ["OMP001", "OMP002"]


def test_context_widens_the_lines(repo):
    _edit(repo, "legacy.f90", "x = y", "x = 2 * y")
    scope = diff_scope(review_revision())
    result = _lint()
    assert not any(result.findings[i].path == "legacy.f90" for i in in_scope(result.findings, scope))
    assert any(result.findings[i].path == "legacy.f90" for i in in_scope(result.findings, scope, context=2))


def test_markdown(repo):
    _edit(repo, "heat.f90", CLAUSES, "")
    scope = diff_scope(review_revision())
    result = _lint()
    scoped = scoped_result(result, in_scope(result.findings, scope, lines=effective_lines(scope, result)))
    text = render_markdown(scoped, scope)
    assert text.startswith("### fobis review\n\n2 finding(s) on the changed lines (2 warning)")
    assert "| warning | `OMP001` shared-scalar-written-in-parallel-region | `heat.f90:14` |" in text
    assert "<details><summary>Rules</summary>" in text
    empty = render_markdown(scoped_result(result, []), scope)
    assert "No finding on the changed lines (1 line(s) in 1 Fortran file(s))." in empty


def test_risk_bundle_has_diff_regions_and_dependents(repo):
    _edit(repo, "heat.f90", "subroutine step(u, unew, n, total)", "subroutine step(u, unew, n, total, dt)")
    _edit(repo, "heat.f90", CLAUSES, "")
    scope = diff_scope(review_revision())
    bundle = risk_bundle(_lint(), scope, [])
    ids = [s.id for s in bundle.sources]
    assert ids[0] == "diff:heat.f90"
    assert "-!$omp parallel do private(flux) reduction(+:total)" in bundle.sources[0].text
    assert "region:heat.f90:12-17" in ids
    dependents = next(s for s in bundle.sources if s.id == "fact:dependents#heat")
    assert dependents.text == "changed headers: heat::step\nused by: driver.f90"
    assert "M heat.f90 (procedures changed: heat::step) (headers changed: heat::step)" in bundle.sections[0][1]


# ── CLI ────────────────────────────────────────────────────────────────────────


@pytest.fixture
def model(monkeypatch, tmp_path):
    replies: list[str] = []
    provider = FakeProvider(lambda messages: replies.pop(0))
    monkeypatch.setattr("fobis.llm.get_provider", lambda cfg, on_status=None: provider)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    return replies, provider


def test_cli_text_and_exit_status(repo, capsys):
    code, out = _run([], capsys)
    assert code == 0 and "Reviewed 0 changed line(s) in 0 Fortran file(s)." in out
    _edit(repo, "heat.f90", CLAUSES, "")
    code, out = _run(["--select", "OMP"], capsys)
    assert code == 1 and "heat.f90:14: OMP001" in out and "legacy.f90" not in out
    code, _ = _run(["--select", "OMP", "--exit-zero"], capsys)
    assert code == 0


def test_cli_staged_and_base(repo, capsys):
    _git(repo, "checkout", "-q", "-b", "topic")
    _edit(repo, "heat.f90", CLAUSES, "")
    code, out = _run(["--staged", "--select", "OMP"], capsys)
    assert code == 0 and "Reviewed 0 changed line(s)" in out  # nothing staged yet
    _git(repo, "add", "heat.f90")
    code, out = _run(["--staged", "--select", "OMP"], capsys)
    assert code == 1 and "OMP001" in out
    _git(repo, "commit", "-q", "-m", "perf(heat): drop clauses")
    code, out = _run(["--base", "main", "--select", "OMP"], capsys)
    assert code == 1 and "OMP002" in out
    _edit(repo, "heat.f90", "total = 0.0", "total = 0.0\n! note")
    _, out = _run(["--base", "main", "--select", "OMP"], capsys)
    assert "Warning: heat.f90 has uncommitted changes" in out


def test_cli_markdown_json_and_formats(repo, capsys):
    _edit(repo, "heat.f90", CLAUSES, "")
    _, out = _run(["--select", "OMP", "--format", "markdown"], capsys)
    assert out.startswith("### fobis review")
    _, out = _run(["--select", "OMP", "--format", "json"], capsys)
    data = json.loads(out)
    assert data["changed_lines"] == 1 and [f["rule"] for f in data["findings"]] == ["OMP001", "OMP002"]
    _, out = _run(["--select", "OMP", "--format", "sarif"], capsys)
    assert json.loads(out)["version"] == "2.1.0"
    code, _ = _run(["--format", "html"], capsys)
    assert code == 1


def test_cli_deep(repo, capsys, model):
    replies, provider = model
    _edit(repo, "heat.f90", CLAUSES, "")
    answer = {
        "insufficient": False,
        "claims": [
            {"kind": "risk", "text": "flux and total are now shared in the step loop.", "citations": ["S1", "S3"]},
            {"kind": "check", "text": "Compare total with the serial result.", "citations": ["S1"]},
        ],
    }
    replies.append(json.dumps(answer))
    code, out = _run(["--select", "OMP", "--deep"], capsys)
    assert code == 1
    assert "Risk summary [llm]:\nRisks:\n  - flux and total are now shared in the step loop. [1][2]" in out
    assert "To check:\n  - Compare total with the serial result. [1]" in out
    assert "## Findings on the changed lines" in provider.calls[0].messages[1]["content"]
    replies.append(json.dumps(answer))
    _, out = _run(["--select", "OMP", "--deep", "--format", "markdown"], capsys)
    assert "#### Risk summary [llm]" in out
    _, out = _run(["--deep-context"], capsys)
    assert "=== system prompt ===" in out and len(provider.calls) == 2
