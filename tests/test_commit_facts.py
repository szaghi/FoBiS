"""Tests for the facts of the staged change (``fobis.ai.change``) and their use by ``fobis commit``: scope
candidates from history and paths, Fortran line kinds on both sides of the diff, type hints, the scope enum and
its rendering, and ``--show-facts``. Real temporary git repositories (``color.ui=always``: the user's own
setting, which once put ANSI codes in the diff sent to the model); the model is a FakeProvider."""

from __future__ import annotations

import json
import subprocess
from collections import Counter

import pytest

import fobis.Commit as Commit
from fobis.ai.change import (
    ChangeFacts,
    change_facts,
    file_kind,
    history_scopes,
    path_scope,
    scope_candidates,
)
from fobis.fobis import run_fobis
from fobis.llm import FakeProvider

KERNEL = """\
module kernels
implicit none
contains
! scale an array
subroutine scale(a, s)
real, intent(inout) :: a(:)
real, intent(in) :: s
integer :: i
!$acc parallel loop
do i = 1, size(a)
  a(i) = a(i) * s
end do
end subroutine scale
end module kernels
"""


def _git(repo, *args) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout


def _write(repo, path: str, text: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    _git(tmp_path, "init", "-q", "-b", "main")
    config = (("user.name", "t"), ("user.email", "t@t"), ("color.ui", "always"), ("commit.gpgsign", "false"))
    for key, value in config:
        _git(tmp_path, "config", key, value)
    _write(tmp_path, "src/lib/fnl/kernels.f90", KERNEL)
    _write(tmp_path, "src/lib/common/grid.f90", "module grid\nend module grid\n")
    _write(tmp_path, "src/app/flume/main.f90", "program main\nend program main\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "feat(lib/fnl): add the kernels")
    _write(tmp_path, "src/lib/common/grid.f90", "module grid\nimplicit none\nend module grid\n")
    _git(tmp_path, "commit", "-q", "-am", "fix(lib): implicit none in grid")
    _write(tmp_path, "src/app/flume/main.f90", "program main\nprint *, 1\nend program main\n")
    _git(tmp_path, "commit", "-q", "-am", "feat(flume): print")
    _write(tmp_path, "README.md", "readme\n")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-q", "-m", "update the readme")  # not conventional: no scope evidence
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _stage(repo, path: str, text: str) -> None:
    _write(repo, path, text)
    _git(repo, "add", path)


def _async(text: str) -> str:
    return text.replace("!$acc parallel loop", "!$acc parallel loop async(1)")


# ── building blocks ────────────────────────────────────────────────────────────


def test_file_kind():
    assert file_kind("src/lib/a.F90") == "fortran"
    assert file_kind("docs/guide/x.md") == "docs" and file_kind("README.md") == "docs"
    assert file_kind("src/tests/t.f90") == "test" and file_kind("test_x.py") == "test"
    assert file_kind(".github/workflows/ci.yml") == "ci"
    assert file_kind("fobos") == "build" and file_kind("CMakeLists.txt") == "build"
    assert file_kind("fobis/Commit.py") == "other"


def test_path_scope():
    assert path_scope("src/lib/x.f90") == "lib"
    assert path_scope("src/main.f90") == "main"
    assert path_scope("fobis/ai/deep.py") == "ai"
    assert path_scope("fobis/Commit.py") == "commit"
    assert path_scope("README.md") is None


def test_history_scopes(repo):
    history = history_scopes()
    assert history["src/lib/fnl/kernels.f90"] == Counter({"lib/fnl": 1})
    assert history["src/lib/"] == Counter({"lib/fnl": 1, "lib": 1})
    assert "README.md" not in history  # a non-conventional subject is no evidence


def test_scope_candidates_vote_by_history_then_directory_then_path():
    history = {"src/lib/a.f90": Counter({"lib": 3, "core": 1}), "src/lib/": Counter({"lib": 4})}
    ranked = scope_candidates(["src/lib/a.f90"], history)
    assert [(c.name, round(c.score, 2)) for c in ranked] == [("lib", 0.75), ("core", 0.25)]
    assert ranked[0].reasons == ["3 of 4 past commits touching src/lib/a.f90 used it"]
    nearest = scope_candidates(["src/lib/new/b.f90"], history)
    assert nearest[0].name == "lib" and "src/lib/" in nearest[0].reasons[0]
    assert scope_candidates(["src/solver/c.f90"], {})[0].name == "solver"
    assert scope_candidates(["README.md"], {}) == []
    many = {"x.f90": Counter({"a": 20, "b": 1})}
    assert [c.name for c in scope_candidates(["x.f90"], many)] == ["a"]  # b is below the floor


# ── facts of real staged changes ───────────────────────────────────────────────


def test_directive_only_change_suggests_perf_acc(repo):
    _stage(repo, "src/lib/fnl/kernels.f90", _async(KERNEL))
    facts = change_facts()
    assert facts.scope_names == ["acc", "lib/fnl", "lib"]  # src/lib/ votes; the file's own commit breaks the tie
    assert ("perf(acc)", "only OpenACC directive lines changed, no code") in facts.hints
    assert facts.files[0].lines == Counter({"acc": 2})
    text = facts.render()
    assert "- acc: only these directives changed" in text
    assert "- src/lib/fnl/kernels.f90: changed lines (removed + added): 2 acc" in text


def test_comment_only_change(repo):
    _stage(repo, "src/lib/fnl/kernels.f90", KERNEL.replace("! scale an array", "! scale an array in place"))
    facts = change_facts()
    assert ("docs or style", "only comments and blank lines changed in the Fortran sources") in facts.hints
    assert facts.scope_names == ["lib/fnl", "lib"]


def test_code_and_interface_changes(repo):
    changed = KERNEL.replace("subroutine scale(a, s)", "subroutine scale(a, s, n)")
    changed = changed.replace("a(i) = a(i) * s", "a(i) = a(i) * s * 2")
    _stage(repo, "src/lib/fnl/kernels.f90", changed)
    facts = change_facts()
    change = facts.files[0]
    assert change.procedures == ["kernels::scale"] and change.interfaces == ["kernels::scale"]
    assert change.lines["code"] == 4
    assert "procedure headers changed (kernels::scale)" in dict(facts.hints)["breaking?"]


def test_new_deleted_renamed_and_mixed(repo):
    newton = "module newton\ncontains\nsubroutine solve()\nend subroutine solve\nend module newton\n"
    _stage(repo, "src/solver/newton.f90", newton)
    _git(repo, "rm", "-q", "src/lib/common/grid.f90")
    _git(repo, "mv", "src/app/flume/main.f90", "src/app/flume/driver.f90")
    facts = change_facts()
    by_path = {f.path: f for f in facts.files}
    assert by_path["src/solver/newton.f90"].status == "A" and by_path["src/lib/common/grid.f90"].status == "D"
    assert by_path["src/app/flume/driver.f90"].status == "R"
    assert by_path["src/lib/common/grid.f90"].lines["code"] == 3  # the deleted file is lexed from HEAD
    assert set(facts.scope_names) >= {"lib", "flume", "solver"}


def test_only_docs(repo):
    _stage(repo, "README.md", "readme, longer\n")
    facts = change_facts()
    assert facts.hints == [("docs", "only documentation files changed")] and facts.scopes == []
    assert "No scope candidate" in facts.render()


# ── commit integration ─────────────────────────────────────────────────────────


def test_commit_schema_and_render_keep_candidate_scopes():
    schema = Commit.commit_schema(["lib/fnl", "acc"])
    assert schema["properties"]["scope"]["enum"] == ["lib/fnl", "acc", ""]
    plain = Commit.commit_schema([])
    assert plain["properties"]["scope"] == {"type": "string", "maxLength": 40}  # no candidates: any scope, bounded
    assert (plain["properties"]["body"]["maxLength"], plain["properties"]["footers"]["maxItems"]) == (1500, 4)
    data = {"type": "perf", "scope": "lib/fnl", "breaking": False, "description": "x", "body": "", "footers": []}
    assert Commit.render_message(data, ["lib/fnl"]).startswith("perf(lib/fnl): x")
    assert Commit.render_message(data).startswith("perf(fnl): x")  # not a candidate: normalised as before


def test_generate_sends_the_facts_and_the_scope_enum(repo):
    _stage(repo, "src/lib/fnl/kernels.f90", _async(KERNEL))
    answer = {
        "type": "perf",
        "scope": "acc",
        "breaking": False,
        "description": "launch the scale loop asynchronously",
        "body": "",
        "footers": [],
    }
    provider = FakeProvider([json.dumps(answer)])
    assert Commit.generate(provider, 10000) == "perf(acc): launch the scale loop asynchronously"
    call = provider.calls[0]
    assert call.schema["properties"]["scope"]["enum"] == ["acc", "lib/fnl", "lib", ""]
    prompt = call.messages[1]["content"]
    assert "## Facts of the change" in prompt and "Type hint: perf(acc)" in prompt
    assert "\x1b[" not in prompt  # color.ui=always must not leak escape codes into the stat and diff
    plain = FakeProvider([json.dumps(answer)])
    Commit.generate(plain, 10000, facts=False)
    assert (
        plain.calls[0].schema == Commit.commit_schema(None) and "## Facts" not in plain.calls[0].messages[1]["content"]
    )


def test_cli_show_facts(repo, capsys):
    with pytest.raises(SystemExit) as caught:
        run_fobis(fake_args=["commit", "--show-facts"])
    assert caught.value.code == 1  # nothing staged
    _stage(repo, "src/lib/fnl/kernels.f90", KERNEL.replace("! scale an array", "! scales"))
    run_fobis(fake_args=["commit", "--show-facts"])
    assert "## Facts of the change" in capsys.readouterr().out


def test_empty_facts_render():
    assert ChangeFacts().render().startswith("## Facts of the change")
