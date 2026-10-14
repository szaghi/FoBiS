"""Tests for ``fobis merge-assist``: hunks from the index stages, the deterministic pre-pass, the git operation and
side names, proposals (checked), compile verification with retries (real gfortran), applying to the working tree
without touching the user's own edits, the CLI (the index is never touched), and the replay of historical merges.
Real temporary git repositories; the model is a FakeProvider."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from fobis.ai.merge import (
    ConflictFile,
    Hunk,
    Operation,
    Resolution,
    apply_to_worktree,
    build_bundle,
    check_proposal,
    conflicted_files,
    intent,
    load_conflict,
    merge_adjacent,
    merge_pins,
    merge_schema,
    merge_uses,
    operation,
    parse_merged,
    pre_pass,
    replay,
    resolve_file,
    verify,
)
from fobis.fobis import run_fobis
from fobis.llm import FakeProvider

SOLVER = """\
module solver
use kinds, only: rk
implicit none
contains
subroutine step(q, n, dt)
real(rk), intent(inout) :: q(:)
integer, intent(in) :: n
real(rk), intent(in) :: dt
integer :: i
!$acc parallel loop firstprivate(n)
do i = 1, n
  q(i) = q(i) * dt
end do
end subroutine step
end module solver
"""
KINDS = (
    "module kinds\nimplicit none\ninteger, parameter :: rk = kind(1.d0)\ninteger, parameter :: ik = kind(1)\n"
    "end module kinds\n"
)
FOBOS = "[modes]\nmodes = gnu\n\n[gnu]\ncompiler = gnu\ncflags = -c\nsrc = ./\nbuild_dir = ./build/\nmod_dir = ./mod/\n"
ACC = "!$acc parallel loop firstprivate(n)"


def _git(repo, *args, check=True) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=check, capture_output=True, text=True).stdout


def _sub(repo, name, old, new):
    path = repo / name
    path.write_text(path.read_text().replace(old, new))


@pytest.fixture
def conflict(tmp_path, monkeypatch):
    """A merge of branch amd into main, stopped on three conflicts in solver.f90 (kinds.mod built)."""
    _git(tmp_path, "init", "-q", "-b", "main")
    config = (("user.name", "t"), ("user.email", "t@t"), ("commit.gpgsign", "false"), ("color.ui", "always"))
    for key, value in config:
        _git(tmp_path, "config", key, value)
    (tmp_path / "solver.f90").write_text(SOLVER)
    (tmp_path / "kinds.f90").write_text(KINDS)
    (tmp_path / "fobos").write_text(FOBOS)
    (tmp_path / ".gitignore").write_text("build/\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "feat(solver): first")
    _git(tmp_path, "checkout", "-q", "-b", "amd")
    _sub(tmp_path, "solver.f90", "use kinds, only: rk", "use kinds, only: rk, ik")
    _sub(tmp_path, "solver.f90", f"{ACC}\n", f"{ACC}\n!$omp OMPLOOP firstprivate(n)\n")
    _sub(tmp_path, "solver.f90", "  q(i) = q(i) * dt", "  q(i) = q(i) * dt * 0.5_rk")
    _git(tmp_path, "commit", "-q", "-am", "feat(solver): amd openmp offload path")
    _git(tmp_path, "checkout", "-q", "main")
    _sub(tmp_path, "solver.f90", "use kinds, only: rk", "use kinds, only: rk\nuse iso_fortran_env, only: output_unit")
    _sub(tmp_path, "solver.f90", ACC, "!$acc parallel loop firstprivate(n, dt)")
    _sub(tmp_path, "solver.f90", "  q(i) = q(i) * dt", "  q(i) = q(i) + dt")
    _git(tmp_path, "commit", "-q", "-am", "fix(solver): explicit increment")
    _git(tmp_path, "merge", "-q", "amd", check=False)
    (tmp_path / "build" / "mod").mkdir(parents=True)
    compile_kinds = ["gfortran", "-c", "kinds.f90", "-J", "build/mod", "-o", "build/kinds.o"]
    subprocess.run(compile_kinds, cwd=tmp_path, check=True)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _hunk(base, ours, theirs) -> Hunk:
    return Hunk(0, ours, base, theirs)


def _file(path, hunk, before=()) -> ConflictFile:
    return ConflictFile(path, [list(before), hunk] if before else [hunk])


# ── parsing and rendering ──────────────────────────────────────────────────────


def test_parse_and_render():
    text = "a\n<<<<<<< ours\nB1\n||||||| base\nb\n=======\nB2\n>>>>>>> theirs\nc\n"
    cf = parse_merged("x.f90", text)
    assert [type(s).__name__ for s in cf.segments] == ["list", "Hunk", "list"]
    (hunk,) = cf.hunks
    assert (hunk.ours, hunk.base, hunk.theirs) == (["B1"], ["b"], ["B2"])
    assert cf.render()[0] == text  # unresolved: diff3 markers
    hunk.resolution = Resolution("user", "custom", ["B"])
    assert cf.render() == ("a\nB\nc\n", {0: (2, 2)})
    assert cf.render(accept=set())[0] == text
    assert cf.context(hunk) == (["a"], ["c"])


def test_apply_to_worktree_keeps_the_users_edits():
    stages = (
        "<<<<<<< ours\nA1\n||||||| base\na\n=======\nA2\n>>>>>>> theirs\nmid\n"
        "<<<<<<< ours\nB1\n||||||| base\nb\n=======\nB2\n>>>>>>> theirs\n"
    )
    cf = parse_merged("x.f90", stages)
    for hunk in cf.hunks:
        hunk.resolution = Resolution("pre-pass", "custom", [f"R{hunk.index}"])
    worktree = "<<<<<<< HEAD\nA1\n=======\nA2\n>>>>>>> amd\nmid\nB by hand\n"  # merge style; B resolved by hand
    assert apply_to_worktree(worktree, cf, {0, 1}) == ("R0\nmid\nB by hand\n", {0})
    assert apply_to_worktree(worktree, cf, set()) == (worktree, set())


# ── pre-pass ───────────────────────────────────────────────────────────────────


def test_pre_pass_simple_rules():
    assert pre_pass(_file("a.f90", h := _hunk(["x"], ["x"], ["y"])), h).lines == ["y"]
    assert pre_pass(_file("a.f90", h := _hunk(["x"], ["y"], ["x"])), h).lines == ["y"]
    assert pre_pass(_file("a.f90", h := _hunk(["x"], ["y"], ["y"])), h).rationale == "both sides made the same change"
    spaces = _hunk(["x"], ["a = b + c"], ["a=b+c"])
    resolution = pre_pass(_file("a.f90", spaces), spaces)
    assert resolution.lines == ["a = b + c"] and "whitespace" in resolution.rationale
    both = _hunk(["x = 1"], ["x = 2"], ["x = 3"])
    assert pre_pass(_file("a.f90", both), both) is None


def test_merge_uses_is_three_way():
    base = ["use kinds, only: rk, ik", "use old_mod"]
    ours = ["use kinds, only: rk, ik, i8", "use old_mod", "use iso_fortran_env, only: output_unit"]
    theirs = ["use kinds, only: rk", "use mpi_f08"]  # theirs removed ik and old_mod
    assert merge_uses(base, ours, theirs) == [
        "use kinds, only: rk, i8",
        "use iso_fortran_env, only: output_unit",
        "use mpi_f08",
    ]
    assert merge_uses(["use m, only: a"], ["use m, only: a, b"], ["use m"]) == ["use m"]  # the whole module wins
    assert merge_uses([], ["use m, only: a"], ["x = 1"]) is None
    intrinsic = merge_uses([], ["use, intrinsic :: iso_c_binding"], ["use m"])
    assert intrinsic == ["use, intrinsic :: iso_c_binding", "use m"]


def test_merge_adjacent():
    ours = ["!$acc parallel loop firstprivate(n, dt)"]
    theirs = [ACC, "!$omp OMPLOOP firstprivate(n)"]
    lines, how = merge_adjacent([ACC], ours, theirs)
    assert lines == ["!$acc parallel loop firstprivate(n, dt)", "!$omp OMPLOOP firstprivate(n)"]
    assert how.startswith("theirs appended")
    lines, how = merge_adjacent(["b"], ["p", "b"], ["B"])
    assert lines == ["p", "B"] and how.startswith("ours prepended")
    assert merge_adjacent([], ["a"], ["b"]) is None
    resolution = pre_pass(_file("s.f90", h := _hunk([ACC], ours, theirs)), h)
    assert resolution.confidence == "medium" and "consistent" in resolution.note


def test_merge_pins_only_in_dependencies():
    base = ["penf = https://github.com/szaghi/PENF :: tag=v1.5.0"]
    ours = ["penf = https://github.com/szaghi/PENF :: tag=v1.6.0"]
    theirs = ["penf = https://github.com/szaghi/PENF :: tag=v1.5.2"]
    lines, moved = merge_pins(base, ours, theirs)
    assert lines == ours and moved == "penf: v1.6.0 vs v1.5.2 -> v1.6.0"
    hunk = _hunk(base, ours, theirs)
    res = pre_pass(_file("fobos", hunk, before=["[dependencies]"]), hunk)
    assert res.lines == ours and "review" in res.note
    assert pre_pass(_file("fobos", hunk, before=["[gnu]"]), hunk) is None
    other = ["penf = https://github.com/other/PENF :: tag=v1.7.0"]
    assert merge_pins(base, ours, other) is None  # not the same dependency


# ── git state ──────────────────────────────────────────────────────────────────


def test_operation_and_files(conflict):
    op = operation()
    assert (op.kind, op.ours_name, op.theirs_name) == ("merge", "main (HEAD)", "amd")
    assert conflicted_files() == ["solver.f90"]
    cf = load_conflict("solver.f90")
    assert len(cf.hunks) == 3
    assert cf.hunks[2].ours == ["  q(i) = q(i) + dt"] and cf.hunks[2].theirs == ["  q(i) = q(i) * dt * 0.5_rk"]
    assert intent(op, "solver.f90", "ours") == "fix(solver): explicit increment"
    assert intent(op, "solver.f90", "theirs") == "feat(solver): amd openmp offload path"


def test_operation_rebase_names_the_sides(conflict):
    _git(conflict, "merge", "--abort")
    _git(conflict, "checkout", "-q", "amd")
    _git(conflict, "rebase", "main", check=False)
    op = operation()
    assert op.kind == "rebase" and op.ours_name.startswith("upstream")
    assert op.theirs_name.startswith("your commit")
    assert op.theirs_name.endswith("feat(solver): amd openmp offload path")
    cf = load_conflict("solver.f90")
    assert "During a rebase, ours (stage 2) is the upstream" in build_bundle(cf, cf.hunks[2], op).render()


# ── model proposals ────────────────────────────────────────────────────────────


def test_bundle_and_schema(conflict):
    cf = load_conflict("solver.f90")
    op = operation()
    bundle = build_bundle(cf, cf.hunks[2], op)
    ids = [s.id for s in bundle.sources]
    assert ids[:4] == ["base:solver.f90#3", "ours:solver.f90#3", "theirs:solver.f90#3", "context:solver.f90#3"]
    assert "intent:ours" in ids and "intent:theirs" in ids and "fact:solver.f90#procedures" in ids
    draft = pre_pass(cf, cf.hunks[1])
    assert build_bundle(cf, cf.hunks[1], op, draft=draft).sources[-1].id == "draft:solver.f90#2"
    schema = merge_schema(bundle.labels)
    assert schema["properties"]["strategy"]["enum"] == ["ours", "theirs", "both", "custom"]
    assert schema["properties"]["citations"]["items"]["enum"] == bundle.labels


def test_check_proposal():
    hunk = _hunk(["x"], ["y"], ["z"])
    bundle = build_bundle(_file("a.f90", hunk), hunk, Operation("merge", "", "", "o", "t"), git=lambda *a: "")

    def answer(**fields):
        data = {"strategy": "custom", "merged_text": "w\n", "rationale": "r", "confidence": "high", "risks": []}
        return json.dumps({**data, "citations": ["S1"], **fields})

    assert check_proposal(answer(), hunk, bundle).lines == ["w"]
    assert check_proposal(answer(strategy="both", merged_text="ignored"), hunk, bundle).lines == ["y", "z"]
    uncited = check_proposal(answer(citations=[]), hunk, bundle)
    assert uncited.confidence == "low" and uncited.note == "the proposal cites no source"
    assert check_proposal(answer(merged_text="<<<<<<< ours\nx"), hunk, bundle) is None
    assert check_proposal(answer(strategy="mine"), hunk, bundle) is None
    assert check_proposal("not json", hunk, bundle) is None


# ── verification ───────────────────────────────────────────────────────────────


def test_verify_compiles_with_the_mode_compiler(conflict):
    cf = load_conflict("solver.f90")
    includes = [str(conflict / "build" / "mod")]
    assert verify(cf).reason == "no conflict is resolved"
    cf.hunks[0].resolution = pre_pass(cf, cf.hunks[0])
    assert verify(cf, includes=includes).ok is True  # the other hunks stand in as ours
    cf.hunks[2].resolution = Resolution("model", "custom", ["  q(i) = q(i) +* dt"])
    check = verify(cf, includes=includes)
    assert check.ok is False and list(check.by_hunk) == [2]
    missing = verify(cf, includes=[])
    assert missing.ok is None and "module(s) kinds not built" in missing.reason


def test_resolve_file_retries_a_proposal_that_does_not_compile(conflict):
    def reply(text):
        data = {"strategy": "custom", "merged_text": text, "rationale": "both", "confidence": "high", "risks": []}
        return json.dumps({**data, "citations": ["S2", "S3"]})

    answers = iter(
        [
            reply("!$acc parallel loop firstprivate(n, dt)\n!$omp OMPLOOP firstprivate(n, dt)"),  # the draft refined
            reply("  q(i) = (q(i) + dt) *** 0.5_rk"),  # does not compile
            reply("  q(i) = (q(i) + dt) * 0.5_rk"),  # the retry
        ]
    )
    provider = FakeProvider(lambda messages: next(answers))
    cf = load_conflict("solver.f90")
    check = resolve_file(cf, operation(), provider, includes=[str(conflict / "build" / "mod")])
    assert check.ok is True and len(provider.calls) == 3
    assert "Compiler errors of the previous proposal" in provider.calls[2].messages[1]["content"]
    assert [h.resolution.source for h in cf.hunks] == ["pre-pass", "model", "model"]
    assert cf.hunks[1].resolution.lines[1] == "!$omp OMPLOOP firstprivate(n, dt)"
    assert all(h.resolution.verified for h in cf.hunks)


def test_a_proposal_that_never_compiles_is_low_confidence(conflict):
    """The model rates its proposal "high"; once the compiler rejects it (and the retries too) it is "low"."""
    bad = json.dumps(
        {
            "strategy": "custom",
            "merged_text": "  q(i) = (q(i) + dt) *** 0.5_rk",
            "rationale": "both",
            "confidence": "high",
            "risks": [],
            "citations": ["S2", "S3"],
        }
    )
    draft = json.dumps({**json.loads(bad), "merged_text": "!$acc parallel loop firstprivate(n, dt)\n!$omp OMPLOOP"})
    answers = iter([draft, bad, bad, bad])
    cf = load_conflict("solver.f90")
    check = resolve_file(
        cf, operation(), FakeProvider(lambda m: next(answers)), includes=[str(conflict / "build" / "mod")]
    )
    assert check.ok is False
    failing = [h.resolution for h in cf.hunks if h.resolution.verified is False]
    assert failing and all(r.confidence == "low" and r.note.startswith("does not compile") for r in failing)


# ── CLI ────────────────────────────────────────────────────────────────────────


def _run(args, capsys) -> tuple[int, str]:
    try:
        run_fobis(fake_args=["merge-assist", *args])
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    return code, capsys.readouterr().out


def test_cli_report_and_context(conflict, capsys):
    code, out = _run(["--no-model"], capsys)
    assert code == 0 and "merge: ours = main (HEAD); theirs = amd" in out
    assert "proposal [pre-pass, custom, confidence high, compiles]: use statements" in out
    assert "conflict 3 of 3" in out and "no proposal: resolve it by hand" in out
    assert "Changed by both sides (test them after the merge): solver.f90: step" in out
    assert "Nothing was staged." in out
    _, out = _run(["--context"], capsys)
    assert "=== solver.f90: conflict 2 ===" in out and "=== solver.f90: conflict 3 ===" in out
    assert "=== solver.f90: conflict 1 ===" not in out  # resolved by a high-confidence rule


def test_cli_apply_yes_and_never_staged(conflict, capsys):
    code, out = _run(["--no-model", "--apply", "--yes"], capsys)
    assert code == 0 and "solver.f90: 1 conflict(s) resolved" in out
    text = (conflict / "solver.f90").read_text()
    assert "use kinds, only: rk, ik\nuse iso_fortran_env, only: output_unit" in text
    assert text.count("<<<<<<<") == 1  # git coalesced conflicts 2 and 3 into one block: left as it is
    assert _git(conflict, "status", "--porcelain").startswith("UU solver.f90")


def test_cli_apply_interactive(conflict, capsys, monkeypatch, tmp_path):
    editor = tmp_path / "editor.py"
    editor.write_text(
        f"#!{sys.executable}\nimport sys\nopen(sys.argv[1], 'w').write('  q(i) = (q(i) + dt) * 0.5_rk\\n')\n"
    )
    editor.chmod(0o755)
    monkeypatch.setenv("EDITOR", str(editor))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    answers = iter(["a", "t", "e"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    code, out = _run(["--no-model", "--apply"], capsys)
    assert code == 0 and "solver.f90: 3 conflict(s) resolved" in out
    text = (conflict / "solver.f90").read_text()
    assert "<<<<<<<" not in text and "!$omp OMPLOOP firstprivate(n)" in text and "(q(i) + dt) * 0.5_rk" in text
    assert _git(conflict, "status", "--porcelain").startswith("UU solver.f90")  # still unmerged: the user adds


def test_cli_apply_needs_a_terminal_or_yes(conflict, capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    code, _ = _run(["--no-model", "--apply"], capsys)
    assert code == 1


def test_cli_no_conflict(tmp_path, monkeypatch, capsys):
    _git(tmp_path, "init", "-q")
    monkeypatch.chdir(tmp_path)
    assert _run(["--no-model"], capsys) == (0, "No conflicted file.\n")


# ── replay ─────────────────────────────────────────────────────────────────────


def test_replay_measures_the_pre_pass(conflict):
    resolved = SOLVER.replace("use kinds, only: rk", "use kinds, only: rk, ik\nuse iso_fortran_env, only: output_unit")
    resolved = resolved.replace(ACC, "!$acc parallel loop firstprivate(n, dt)\n!$omp OMPLOOP firstprivate(n, dt)")
    resolved = resolved.replace("  q(i) = q(i) * dt", "  q(i) = (q(i) + dt) * 0.5_rk")
    (conflict / "solver.f90").write_text(resolved)
    _git(conflict, "commit", "-q", "-am", "Merge branch amd")
    stats = replay(str(conflict))
    data = stats.as_dict()
    assert data == {
        "merges": 1,
        "conflicted_merges": 1,
        "hunks": 3,
        "resolved_high_confidence": 1,  # the use union, as the human resolved it
        "agree_with_human": 1,
        "drafts_for_the_model": 1,  # the adjacent edits ...
        "drafts_equal_to_human": 0,  # ... lack the dt the human also added to the !$omp clause
        "disagree": [],
    }
    assert _git(conflict, "worktree", "list").count("\n") == 1  # the temporary worktree is removed
    assert os.path.isdir(conflict)


def test_replay_with_the_model(conflict):
    """The drafts and the unresolved hunks go to the model, as merge-assist sends them; each proposal is compared
    with the committed resolution (improved draft, solved hunk, unusable answer)."""
    resolved = SOLVER.replace("use kinds, only: rk", "use kinds, only: rk, ik\nuse iso_fortran_env, only: output_unit")
    resolved = resolved.replace(ACC, "!$acc parallel loop firstprivate(n, dt)\n!$omp OMPLOOP firstprivate(n, dt)")
    resolved = resolved.replace("  q(i) = q(i) * dt", "  q(i) = (q(i) + dt) * 0.5_rk")
    (conflict / "solver.f90").write_text(resolved)
    _git(conflict, "commit", "-q", "-am", "Merge branch amd")

    def reply(text):
        data = {"strategy": "custom", "merged_text": text, "rationale": "r", "confidence": "high", "risks": []}
        return json.dumps({**data, "citations": ["S2", "S3"]})

    human = [reply("!$acc parallel loop firstprivate(n, dt)\n!$omp OMPLOOP firstprivate(n, dt)")]
    data = replay(str(conflict), provider=FakeProvider([*human, reply("  q(i) = (q(i) + dt) * 0.5_rk")])).as_dict()
    model = data["model"]
    assert (model["asked"], model["equal_to_human"], model["drafts_improved"], model["unresolved_solved"]) == (
        2,
        2,
        1,
        1,
    )
    assert [h["kind"] for h in model["hunks"]] == ["draft", "unresolved"] and model["drafts_spoiled"] == 0
    data = replay(str(conflict), provider=FakeProvider(["not json", reply("  q(i) = q(i) * dt")])).as_dict()
    assert (data["model"]["unusable"], data["model"]["equal_to_human"]) == (1, 0)


def test_apply_to_a_block_git_coalesced_from_two_hunks():
    stages = (
        "<<<<<<< ours\nA1\n||||||| base\na\n=======\nA2\n>>>>>>> theirs\nmid\n"
        "<<<<<<< ours\nB1\n||||||| base\nb\n=======\nB2\n>>>>>>> theirs\n"
    )
    cf = parse_merged("x.f90", stages)
    cf.hunks[0].resolution = Resolution("pre-pass", "custom", ["R0"])
    worktree = "<<<<<<< HEAD\nA1\nmid\nB1\n=======\nA2\nmid\nB2\n>>>>>>> amd\n"  # one block for both hunks
    text, applied = apply_to_worktree(worktree, cf, {0})
    assert applied == {0}
    assert text == "R0\nmid\n<<<<<<< ours\nB1\n||||||| base\nb\n=======\nB2\n>>>>>>> theirs\n"
