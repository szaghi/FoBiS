"""Tests for ``fobis testgen``: local declarations standing for dummy arguments, the cases (procedures, generics,
type-bound procedures), the skeleton built for real with gfortran in a scratch copy (a case that does not compile
is dropped), the acceptance checks, the generation loop on a FakeProvider (errors, a failing check and a vacuous
test sent back) and the CLI (skeleton, context, apply, json, model)."""

from __future__ import annotations

import json
import os
import subprocess

import pytest

from fobis.ai.testgen import (
    Sandbox,
    build_bundle,
    checked_skeleton,
    coverage,
    find_module,
    generate,
    local_declaration,
    parse_program,
    plan_cases,
    skeleton,
    type_bindings,
    wrap,
)
from fobis.analysis.units import Decl
from fobis.fobis import run_fobis
from fobis.llm import FakeProvider

KINDS = "module kinds\nimplicit none\ninteger, parameter :: rk = kind(1.d0)\nend module kinds\n"
SHAPES = """\
module shapes
use kinds, only: rk
implicit none
private
public :: area, scale_all, shift, label, circle, counter, hidden_user
type :: hidden_t
  integer :: i = 0
end type hidden_t
type :: circle
  real(rk) :: r = 0.0_rk
contains
  procedure, pass(self) :: diameter
  procedure, nopass :: unit_radius
  generic :: resize => resize_by, resize_to
  procedure, private :: resize_by
  procedure, private :: resize_to
end type circle
type :: counter
  integer :: n = 0
contains
  private
  procedure, public :: bump
  procedure :: reset
end type counter
interface shift
  module procedure shift_r, shift_v
end interface shift
contains
pure function area(r) result(a)
real(rk), intent(in) :: r
real(rk) :: a
a = 3.0_rk * r**2
end function area
subroutine scale_all(x, s)
real(rk), intent(inout) :: x(:)
real(rk), intent(in) :: s
x = x * s
end subroutine scale_all
subroutine shift_r(x, d)
real(rk), intent(inout) :: x
real(rk), intent(in) :: d
x = x + d
end subroutine shift_r
subroutine shift_v(x, d)
real(rk), intent(inout) :: x(:)
real(rk), intent(in) :: d
x = x + d
end subroutine shift_v
function label(name, n) result(text)
character(*), intent(in) :: name
integer, intent(in) :: n
character(len=:), allocatable :: text
text = name
end function label
subroutine hidden_user(h)
type(hidden_t), intent(inout) :: h
h%i = 1
end subroutine hidden_user
pure function diameter(self) result(d)
class(circle), intent(in) :: self
real(rk) :: d
d = 2 * self%r
end function diameter
pure function unit_radius() result(r)
real(rk) :: r
r = 1.0_rk
end function unit_radius
subroutine resize_by(self, factor)
class(circle), intent(inout) :: self
real(rk), intent(in) :: factor
self%r = self%r * factor
end subroutine resize_by
subroutine resize_to(self, n)
class(circle), intent(inout) :: self
integer, intent(in) :: n
self%r = n
end subroutine resize_to
subroutine bump(self)
class(counter), intent(inout) :: self
self%n = self%n + 1
end subroutine bump
subroutine reset(self)
class(counter), intent(inout) :: self
self%n = 0
end subroutine reset
end module shapes
"""
GOOD_AREA = """\
program test_shapes
  use shapes
  use kinds, only: rk
  implicit none
  integer :: failures = 0
  call test_area()
  if (failures > 0) error stop 1
contains
  subroutine test_area()
    real(rk) :: r, res
    r = 2.0_rk
    res = area(r=r)
    if (abs(res - {expected}) > 1.0e-12_rk) then
      print *, 'area', res
      failures = failures + 1
    end if
  end subroutine test_area
end program test_shapes
"""


def _git(repo, *args) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A git project with a fobos (sources in src/, build in build/) holding the shapes module."""
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text("[user]\n\tname = T\n\temail = t@t\n[commit]\n\tgpgsign = false\n[color]\n\tui = always\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    repo = tmp_path / "proj"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "kinds.f90").write_text(KINDS)
    (repo / "src" / "shapes.f90").write_text(SHAPES)
    (repo / "fobos").write_text("[default]\ncompiler = gnu\nsrc = ./src/\nbuild_dir = ./build/\n")
    (repo / ".gitignore").write_text("build/\n")
    _git(repo, "init", "-q", "-b", "master")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "feat: shapes")
    monkeypatch.chdir(repo)
    return repo


def _target():
    return find_module("shapes", ["src/kinds.f90", "src/shapes.f90"])


# ── declarations ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("decl", "expected"),
    [
        (Decl("x", "real(rk)", {"intent": "in"}), "real(rk) :: v"),
        (Decl("x", "real(rk)", {"intent": "inout"}, dims=":,:"), "real(rk), allocatable :: v(:,:)"),
        (Decl("x", "real(rk)", {"intent": "in"}, dims="n"), "real(rk), allocatable :: v(:)"),
        (Decl("x", "integer", {"intent": "out"}, dims="3"), "integer :: v(3)"),
        (Decl("x", "character(*)", {"intent": "in"}), "character(len=:), allocatable :: v"),
        (Decl("x", "character(len=*,kind=ck)", {"intent": "in"}), "character(len=:, kind=ck), allocatable :: v"),
        (Decl("x", "character(*)", {"intent": "in"}, dims="1:2"), "character(len=:), allocatable :: v(:)"),
        (
            Decl("x", "character(*)", {"allocatable": "", "intent": "out"}, dims=":"),
            "character(len=256), allocatable :: v(:)",
        ),
        (Decl("x", "character(len=len(s))", {"allocatable": ""}, dims=":"), "character(len=256), allocatable :: v(:)"),
        (Decl("x", "character(len=10)", {"intent": "in"}), "character(len=10) :: v"),
        (Decl("x", "class(circle)", {"intent": "in"}), "type(circle) :: v"),
        (Decl("x", "class(circle)", {"pointer": "", "intent": "in"}), "class(circle), pointer :: v"),
        (Decl("x", "type(node)", {"pointer": "", "intent": "in"}, dims=":"), "type(node), pointer :: v(:)"),
    ],
)
def test_local_declaration(decl, expected):
    assert local_declaration(decl, "v") == (expected, "")


@pytest.mark.parametrize(
    ("decl", "reason"),
    [
        (None, "v is implicitly typed"),
        (Decl("f", "procedure(func)", {"intent": "in"}), "f is a procedure argument"),
        (Decl("x", "class(*)", {"intent": "in"}), "x is unlimited polymorphic"),
        (Decl("x", "real", {"intent": "in"}, dims=".."), "x is assumed-rank"),
    ],
)
def test_no_local_declaration(decl, reason):
    assert local_declaration(decl, "v") == (None, reason)


def test_wrap_long_statements_outside_strings():
    statement = "call obj%name(" + ", ".join(f"arg{i}=value{i}" for i in range(12)) + ", tag='a, b')"
    lines = wrap(statement, width=60)
    assert len(lines) > 1 and all(line.endswith("&") for line in lines[:-1]) and lines[-1].endswith("tag='a, b')")
    assert " ".join(line.rstrip("&") for line in lines).split() == statement.split()
    assert wrap("call f(a=a)") == ["call f(a=a)"]


# ── cases ──────────────────────────────────────────────────────────────────────


def test_type_bindings():
    body = (
        "type :: t\ninteger :: i\ncontains\nprivate\nprocedure, public :: a => a_impl\nprocedure, nopass :: b\n"
        "procedure(i), deferred :: c\ngeneric, public :: g => b, d\nprocedure, pass(this) :: d\nfinal :: f\nend type t"
    )
    bindings, generics = type_bindings(body)
    assert {n: (b.specific, b.passed, b.public) for n, b in bindings.items()} == {
        "a": ("a_impl", None, True),
        "b": ("b", "", False),
        "d": ("d", "this", False),
    }
    assert generics == {"g": (["b", "d"], True)}


def test_plan_cases(project):
    cases = {c.label: c for c in plan_cases(_target())}
    assert sorted(cases) == [
        "area",
        "circle%diameter",
        "circle%resize (resize_by)",
        "circle%resize (resize_to)",
        "circle%unit_radius",
        "counter%bump",
        "hidden_user",
        "label",
        "scale_all",
        "shift (shift_r)",
        "shift (shift_v)",
    ]
    assert cases["circle%resize (resize_by)"].lines[1:] == [
        "  type(circle) :: self",
        "  real(rk) :: factor",
        "  ! TODO: give the inputs values, then check the outputs against expected values",
        "  call self%resize(factor=factor)",
        "end subroutine test_circle_resize_by",
    ]
    assert "  res = obj_%unit_radius()" in cases["circle%unit_radius"].lines
    assert "  character(len=:), allocatable :: res" in cases["label"].lines
    assert "  call shift(x=x, d=d)" in cases["shift (shift_v)"].lines
    chosen = plan_cases(_target(), ["shift", "circle%diameter"])
    assert [c.label for c in chosen if not c.skipped] == ["shift (shift_r)", "shift (shift_v)", "circle%diameter"]
    limited = plan_cases(_target(), limit=2)
    assert [c.skipped for c in limited].count("over the limit of 2 (--max, --procedure)") == len(limited) - 2


def test_skeleton_built_for_real_drops_what_does_not_compile(project):
    target = _target()
    with Sandbox(".", "src") as sandbox:
        skel, attempt = checked_skeleton(target, plan_cases(target), sandbox)
    assert attempt.ok, attempt.output
    hidden = next(c for c in skel.cases if c.name == "hidden_user")
    assert hidden.skipped.startswith("the generated call does not compile:") and "hidden_t" in hidden.skipped
    assert len(skel.active) == 10 and "! not tested: hidden_user: the generated call" in skel.text
    assert not os.path.exists("build") and not os.path.exists("src/test_shapes.f90")  # the user's tree untouched


# ── acceptance and generation ──────────────────────────────────────────────────


def test_coverage():
    program = GOOD_AREA.format(expected="12.0_rk")
    found = coverage(program, "shapes", {"area", "scale_all"})
    assert (found.uses_module, found.called, found.checks, found.problems) == (True, ["area"], 1, [])
    vacuous = coverage(program.replace("failures = failures + 1", "print *, 'x'"), "shapes", {"area"})
    assert vacuous.problems == [
        "the program checks nothing: no 'error stop', non-zero 'stop' or failure counter increment inside a test "
        "procedure"
    ]
    assert coverage("program p\nend program p\n", "shapes", {"area"}).problems[:2] == [
        "the program does not use the module under test",
        "the program calls none of the module's public procedures",
    ]


def test_parse_program():
    answer = json.dumps({"fortran_source_code": "program p\nend program p", "notes": "n"})
    assert parse_program(answer) == ("program p\nend program p\n", "n")
    assert parse_program(json.dumps({"program": "program p\nend program p"}))[0] == "program p\nend program p\n"
    fenced = json.dumps({"fortran_source_code": "```fortran\nprogram p\nend program p\n```", "notes": ""})
    assert parse_program(fenced)[0] == "program p\nend program p\n"
    assert parse_program("Here:\n```fortran\nprogram q\nend program q\n```")[0] == "program q\nend program q\n"
    assert parse_program("no program") == (None, "")


def _answer(program: str) -> str:
    return json.dumps({"fortran_source_code": program, "notes": "area(2) = 3 * 2**2"})


def test_generate_sends_errors_and_failures_back(project):
    target = _target()
    good = GOOD_AREA.format(expected="12.0_rk")
    replies = [
        _answer(good.replace("res = area(r=r)", "res = area(q=r)")),  # does not compile
        _answer(GOOD_AREA.format(expected="13.0_rk")),  # wrong expectation: the check fails
        _answer(good.replace("failures = failures + 1", "continue")),  # checks nothing
        _answer(good),
    ]
    provider = FakeProvider(replies)
    with Sandbox(".", "src") as sandbox:
        skel, _ = checked_skeleton(target, plan_cases(target, ["area"]), sandbox)
        result = generate(target, skel, sandbox, provider, build_bundle(target, skel), retries=3)
    assert result.program == good and result.attempts == 4
    assert result.coverage.called == ["area"] and result.coverage.checks == 1
    feedback = [call.messages[-1]["content"] for call in provider.calls[1:]]
    assert feedback[0].startswith("The program does not compile:\nline 12: Keyword argument")
    assert feedback[1].startswith("The program stopped with exit status 1.") and "area" in feedback[1]
    assert feedback[2].startswith("The program builds and runs but is not a test yet:\n- the program checks nothing")
    assert [m["role"] for m in provider.calls[3].messages] == ["system", "user", *["assistant", "user"] * 3]
    assert provider.calls[0].schema["required"] == ["fortran_source_code", "notes"]


def test_generate_gives_up(project):
    target = _target()
    provider = FakeProvider([_answer(GOOD_AREA.format(expected="13.0_rk"))] * 2)
    with Sandbox(".", "src") as sandbox:
        skel, _ = checked_skeleton(target, plan_cases(target, ["area"]), sandbox)
        result = generate(target, skel, sandbox, provider, build_bundle(target, skel), retries=1)
    assert result.program is None and result.attempts == 2
    assert result.reason == "it stopped with exit status 1" and "13.0" in result.last


def test_generate_rejects_an_answer_that_is_not_a_program(project):
    """Found with coder-0.5b: the `program` field held only the program's name. FoBiS builds such a file as a
    library and hides its errors, so it is refused before any build, with a precise instruction."""
    target = _target()
    good = GOOD_AREA.format(expected="12.0_rk")
    provider = FakeProvider([_answer("test_shapes"), _answer(good)])
    with Sandbox(".", "src") as sandbox:
        skel, _ = checked_skeleton(target, plan_cases(target, ["area"]), sandbox)
        result = generate(target, skel, sandbox, provider, build_bundle(target, skel), retries=1)
    assert result.program == good and result.attempts == 2
    assert (
        provider.calls[1]
        .messages[-1]["content"]
        .startswith(
            "The `fortran_source_code` field must hold the WHOLE Fortran program, from `program test_shapes` to `end program"
        )
    )


def test_bundle(project):
    target = _target()
    skel = skeleton(target, plan_cases(target, ["area", "circle%diameter"]))
    bundle = build_bundle(target, skel, ("test/old.f90", "program old\nend program old"))
    assert [s.id for s in bundle.sources] == [
        "api:shapes",
        "code:src/shapes.f90:29",
        "code:src/shapes.f90:59",
        "test:test/old.f90",
    ]
    api = bundle.sources[0].text
    assert "procedure area:" in api and "type circle:" in api and "scale_all" not in api
    assert "   29 | pure function area(r) result(a)" in bundle.sources[1].text


# ── CLI ────────────────────────────────────────────────────────────────────────


def _run(args, capsys) -> tuple[int, str]:
    try:
        run_fobis(fake_args=["testgen", *args])
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def test_cli_skeleton_and_apply(project, capsys):
    code, out = _run(["shapes", "--skeleton", "-p", "area"], capsys)
    assert code == 0 and "  test area" in out and "res = area(r=r)" in out and "--apply writes it to test/" in out
    assert not os.path.exists("test")
    code, out = _run(["shapes", "--skeleton", "-p", "area", "--apply"], capsys)
    assert code == 0 and "Written to test/test_shapes.f90" in out
    assert "res = area(r=r)" in (project / "test" / "test_shapes.f90").read_text()
    code, out = _run(["shapes", "--skeleton", "--apply"], capsys)
    assert code == 1 and "test/test_shapes.f90 exists: not overwritten" in out


def test_cli_errors_context_and_json(project, capsys):
    code, out = _run(["nothere"], capsys)
    assert code == 2 and "module 'nothere' not found" in out
    code, out = _run(["kinds"], capsys)
    assert code == 2 and "has no public procedure to test" in out
    code, out = _run(["shapes", "--context", "-p", "area"], capsys)
    assert code == 0 and "=== system prompt ===" in out and "## Skeleton to complete" in out
    run_fobis(fake_args=["testgen", "shapes", "--skeleton", "-p", "label", "--format", "json"])
    captured = capsys.readouterr()
    data = json.loads(captured.out)  # stdout holds the JSON only, the progress goes to stderr
    assert (
        "building the skeleton" in captured.err
        and data["tested"] == ["label"]
        and data["accepted"]
        and data["written"] is None
    )


def test_cli_model(project, capsys, monkeypatch, tmp_path):
    good = GOOD_AREA.format(expected="12.0_rk")
    provider = FakeProvider([_answer(good)])
    monkeypatch.setattr("fobis.llm.get_provider", lambda cfg, on_status=None: provider)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    code, out = _run(["shapes", "-p", "area", "--apply", "--output", "test/area_test.f90"], capsys)
    assert code == 0 and "Accepted after 1 attempt(s): builds, runs (exit 0), calls area; 1 check(s)." in out
    assert (project / "test" / "area_test.f90").read_text() == good
    provider = FakeProvider([_answer(GOOD_AREA.format(expected="13.0_rk"))] * 2)
    monkeypatch.setattr("fobis.llm.get_provider", lambda cfg, on_status=None: provider)
    code, out = _run(["shapes", "-p", "area", "--retries", "1"], capsys)
    assert code == 1 and "No program accepted after 2 attempt(s): it stopped with exit status 1" in out
    assert "Last attempt (rejected, not written)" in out
