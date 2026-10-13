"""Tests for shadow modes and ``fobis matrix`` (phase V3 of PLAN-verification.md): the flag table and transform,
real gfortran shadow builds (a release build silently wrong, its checks shadow located; the user's build directory
untouched), ``test``/``introspect`` with ``--shadow``, an explicit ``--target`` winning over the mode's target and a
test outside the sources reported as not built (both found while building V3), the runner with a shadow, the setup
environment, the matrix on a fake runner (skipped, unsupported, build failure, test failures rechecked, references,
disagreements, compiler filter, text) and ``fobis matrix`` for real."""

from __future__ import annotations

import json
import os
import subprocess
from argparse import Namespace

import pytest

from fobis.fobis import run_fobis
from fobis.verification import LocalRunner
from fobis.verification.case import CaseError, parse_case, parse_setup
from fobis.verification.matrix import Matrix, render_text, sanitizer_problem, setup_environment
from fobis.verification.shadow import SHADOW_ROOT, ShadowError, apply, build_dir, flags_for, transform

OVERRUN = """\
program overrun
implicit none
type :: pair
  real :: a(4)
  real :: guard
end type pair
type(pair), target :: p
p%guard = 42.0
call fill(p%a, size(p%a) + 1)
if (p%guard /= 42.0) error stop 'guard overwritten'
print *, 'guard = ', p%guard
contains
subroutine fill(x, m)
integer, intent(in) :: m
real, intent(out) :: x(4)
integer :: k
do k = 1, m
  x(k) = 0.0
end do
end subroutine fill
end program overrun
"""
UNINIT = """\
program test_uninit
implicit none
call work()
contains
subroutine work()
real :: s
integer :: i
do i = 1, 3
  s = s + real(i)
end do
print *, s
end subroutine work
end program test_uninit
"""
SERIES = """\
program series
use iso_fortran_env, only: real64
implicit none
integer, parameter :: n = 200000
real(real64) :: x(n), s
integer :: i
do i = 1, n
  x(i) = 1.0_real64 / real(i, real64)**2
end do
s = 0.0_real64
do i = 1, n
  s = s + x(i)
end do
print '(a,es24.17)', 'zeta2 = ', s
print '(a,i0)', 'n = ', n
end program series
"""


# ── the flag table ─────────────────────────────────────────────────────────────


def test_transform():
    assert transform("-c -O3 -ffast-math -march=native -fopenmp", "-O0 -g", (r"-O\S*", "-ffast-math")) == (
        "-c -march=native -fopenmp -O0 -g"
    )
    # a flag with a separate value goes with it; a unit already present is not added twice
    assert transform("-c -fp-model fast=2 -warn all -O2", "-warn errors -warn all", ("-fp-model", r"-O\S*")) == (
        "-c -warn all -warn errors"
    )
    assert transform(None, "-std=f2018", ()) == "-std=f2018"


def test_flags_for():
    gnu = flags_for("checks", "gnu")
    assert "-fcheck=all" in gnu.compile and "-ffpe-trap=invalid,zero,overflow" in gnu.compile
    assert flags_for("checks", "opencoarrays-gnu") == gnu
    assert flags_for("strict", "pgi") == flags_for("strict", "nvfortran")
    assert flags_for("sanitize", "intel_nextgen").link == "-fsanitize=address"
    assert flags_for("none", "lfortran").compile == ""  # none: the mode's own flags, any compiler
    with pytest.raises(ShadowError, match="unknown shadow 'fast'"):
        flags_for("fast", "gnu")
    with pytest.raises(ShadowError, match="no shadow flags for compiler 'lfortran'"):
        flags_for("checks", "lfortran")
    with pytest.raises(ShadowError, match="nvfortran has no sanitizer"):
        flags_for("sanitize", "nvfortran")
    with pytest.raises(ShadowError, match="ifort ignores -fsanitize=address"):  # ifx has it, ifort does not
        flags_for("sanitize", "intel")
    assert flags_for("checks", "intel") == flags_for("checks", "intel_nextgen")


def test_apply():
    cliargs = Namespace(compiler="gnu", cflags="-O3 -ffast-math", lflags="-O3", build_dir="build/")
    apply(cliargs, "sanitize", "rel")
    assert cliargs.cflags == "-c -ffast-math -O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined"
    assert cliargs.lflags == "-fsanitize=address,undefined"
    assert cliargs.build_dir == build_dir("rel", "sanitize") == os.path.join(SHADOW_ROOT, "rel-sanitize")
    test_args = Namespace(compiler="gnu", build_dir="build/")  # test/run: only the build directory
    apply(test_args, "checks", None)
    assert test_args.build_dir == os.path.join(SHADOW_ROOT, "default-checks")
    with pytest.raises(ShadowError):
        apply(Namespace(build_dir="b"), "nope", None)


# ── real shadow builds ─────────────────────────────────────────────────────────


@pytest.fixture
def project(tmp_path, monkeypatch):
    repo = tmp_path / "proj"
    (repo / "src").mkdir(parents=True)
    (repo / "test").mkdir()
    (repo / "src" / "overrun.f90").write_text(OVERRUN)
    (repo / "src" / "series.f90").write_text(SERIES)
    (repo / "test" / "test_uninit.f90").write_text(UNINIT)
    (repo / "fobos").write_text(
        "[modes]\nmodes = rel\n\n[rel]\ncompiler = gnu\nsrc = ./src/ ./test/\nbuild_dir = ./build/\n"
        "target = overrun.f90\ncflags = -c -O2\n\n"
        "[case:series]\ntarget = src/series.f90\nquantities = stdout\n"
    )
    monkeypatch.chdir(repo)
    return repo


def _run(args, capsys):
    try:
        run_fobis(fake_args=args)
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_shadow_build_finds_what_the_release_hides(project, capsys):
    assert _run(["build"], capsys)[0] == 0
    release = subprocess.run(["./build/overrun"], capture_output=True, text=True)
    assert release.returncode != 0 and "guard overwritten" in release.stderr  # the symptom, far from the cause
    code, out, _ = _run(["build", "--shadow", "checks"], capsys)
    assert code == 0 and "-c -O0 -g -fcheck=all" in out
    program = os.path.join(SHADOW_ROOT, "rel-checks", "overrun")
    checked = subprocess.run([program], capture_output=True, text=True)
    assert "Index '5' of dimension 1 of array 'x' above upper bound of 4" in checked.stderr
    assert "At line 18 of file src/overrun.f90" in checked.stderr
    assert sorted(os.listdir("build")) == ["mod", "obj", "overrun"]  # the user's build directory: only its own
    code, out, _ = _run(["introspect", "--compiler", "--buildoptions", "--shadow", "strict"], capsys)
    data = json.loads(out)
    assert "-std=f2018" in data["compiler"]["cflags"] and data["buildoptions"]["shadow"] == "strict"
    assert data["buildoptions"]["build_dir"] == os.path.join(SHADOW_ROOT, "rel-strict")
    code, out, _ = _run(["build", "--shadow", "fast"], capsys)
    assert code == 2 and "unknown shadow 'fast'" in out


def test_test_with_a_shadow(project, capsys):
    # the mode declares target = overrun.f90: before V3 every test program was built as the mode's target
    code, out, _ = _run(["test", "--json"], capsys)
    result = json.loads(out)["results"][0]
    assert code == 0 and result["name"] == "test_uninit" and "6.0" in result["stdout"]
    code, out, _ = _run(["test", "--shadow", "checks", "--json"], capsys)
    result = json.loads(out)["results"][0]
    assert code == 1 and result["status"] == "failed" and result["crash"]["kind"] == "fpe"
    assert result["notes"][0]["summary"] == "floating-point exception at test/test_uninit.f90:9"
    assert os.path.isfile(os.path.join(SHADOW_ROOT, "rel-checks", "test", "test_uninit"))


def test_test_outside_the_sources_is_not_run_stale(project, capsys):
    _run(["test", "--json"], capsys)  # builds build/test/test_uninit
    (project / "fobos").write_text((project / "fobos").read_text().replace("./src/ ./test/", "./src/"))
    code, out, _ = _run(["test", "--json"], capsys)
    result = json.loads(out)["results"][0]
    assert code == 1 and result["status"] == "build-failed"
    assert result["errors"] == ["test/test_uninit.f90 was not built: is it among the mode's sources (src)?"]


def test_runner_with_a_shadow(project):
    runner = LocalRunner(".", shadow="checks")
    result = runner.run(parse_case("series", {"target": "src/series.f90", "quantities": "stdout"}))
    assert result.ok and result.provenance["shadow"] == "checks"
    assert "-fcheck=all" in result.provenance["compiler"]["cflags"]
    assert os.path.basename(result.command[0]) == "series-default-checks"


# ── setup environments ─────────────────────────────────────────────────────────


def test_setup():
    assert parse_setup("nvfortran: module load nvhpc/26\n  rel: source x.sh; export A=1\n") == {
        "nvfortran": "module load nvhpc/26",
        "rel": "source x.sh; export A=1",
    }
    with pytest.raises(CaseError, match="is not 'mode-or-compiler: commands'"):
        parse_setup("module load gcc")
    env = setup_environment("echo noise; export FOBIS_SETUP_TEST='a b'", base={"PATH": os.environ["PATH"]})
    assert env["FOBIS_SETUP_TEST"] == "a b"
    with pytest.raises(RuntimeError, match=r"failed \(exit 3\): oops"):
        setup_environment("echo oops >&2; exit 3")


# ── sanitizer reports ──────────────────────────────────────────────────────────

SANITIZER_LOGS = os.path.join(os.path.dirname(__file__), "matrix")


@pytest.mark.parametrize(
    ("log", "problem"),
    [
        ("leak", "memory leak (LeakSanitizer): 40 byte(s) leaked in 1 allocation(s), allocated at leak.f90:4"),
        ("heap", "AddressSanitizer: heap-buffer-overflow at heap.f90:16"),
        ("bounds", "AddressSanitizer: stack-buffer-overflow at bounds.f90:8"),
    ],
)
def test_sanitizer_problem(log, problem):
    """GENUINE gfortran 16 -fsanitize=address,undefined reports of the programs next to them (tests/matrix/)."""
    with open(os.path.join(SANITIZER_LOGS, f"gnu-sanitize-{log}.txt")) as handle:
        assert sanitizer_problem(handle.read()) == problem
    assert sanitizer_problem("x.f90:3:5: runtime error: signed integer overflow") == (
        "undefined behaviour at x.f90:3: signed integer overflow"
    )
    assert sanitizer_problem("Segmentation fault") == ""


# ── the matrix on a fake runner ────────────────────────────────────────────────


class Fake:
    """Answers the nested fobis commands of a matrix; records them with the environment they got."""

    def __init__(self, compilers, builds=None, tests=None, cases=None):
        self.compilers, self.builds, self.tests, self.cases = compilers, builds or {}, tests or {}, cases or {}
        self.calls = []

    def __call__(self, args, env):
        self.calls.append((args, (env or {}).get("MARK")))
        mode = args[args.index("--mode") + 1]
        shadow = args[args.index("--shadow") + 1] if "--shadow" in args else ""
        if args[0] == "introspect":
            name, binary = self.compilers[mode]
            return 0, json.dumps({"compiler": {"name": name, "binary": binary}}), ""
        if args[0] == "build":
            report = self.builds.get((mode, shadow), {"status": "ok"})
            return (0 if report["status"] == "ok" else 1), json.dumps(report), ""
        if args[0] == "test":
            key = (mode, shadow, args[args.index("--filter") + 1] if "--filter" in args else "")
            return 0, json.dumps({"results": self.tests.get(key, [{"name": "t1", "status": "passed"}])}), ""
        return 0, json.dumps({"results": self.cases.get((mode, shadow), [])}), ""


def _quantities(value):
    return {"zeta2": {"values": [value]}, "n": {"values": [200000.0]}}


def test_matrix(tmp_path):
    crash = {"name": "t1", "status": "failed", "exit_code": 2, "notes": [{"summary": "guard overwritten"}]}
    located = {"name": "t1", "status": "failed", "crash": {"kind": "bounds"}, "notes": [{"summary": "index 5 of x"}]}
    fake = Fake(
        {"rel": ("gnu", "sh"), "nv": ("nvfortran", "sh"), "nag": ("nag", "no-such-compiler-xyz")},
        builds={("nv", "strict"): {"status": "error", "diagnoses": [{"summary": "missing module m"}]}},
        tests={
            ("rel", "none", ""): [crash],
            ("rel", "strict", ""): [crash],
            ("rel", "sanitize", ""): [
                {
                    "name": "t2",
                    "status": "failed",
                    "stderr": "SUMMARY: AddressSanitizer: 8 byte(s) leaked in 1 allocation(s).",
                }
            ],
            ("rel", "checks", "t1"): [located],
        },
        cases={
            ("rel", "none"): [{"case": "s", "status": "ok", "quantities": _quantities(1.6449)}],
            ("rel", "checks"): [{"case": "s", "status": "ok", "quantities": _quantities(1.6449 + 1e-14)}],
            ("nv", "none"): [{"case": "s", "status": "failed", "exit_code": 139, "stderr": "Segmentation fault"}],
        },
    )
    references = tmp_path / "refs"
    references.mkdir()
    (references / "s.json").write_text(json.dumps({"case": "s", "quantities": _quantities(1.6449)}))
    cases = {"s": parse_case("s", {"target": "a.f90", "tolerance": "n: exact"})}
    lines = []
    matrix = Matrix(
        ["rel", "nv", "nag"],
        ["none", "checks", "sanitize", "strict"],
        fake,
        setup={"nvfortran": "module load nvhpc"},
        cases=cases,
        references_dir=str(references),
        has_tests=True,
        verify=True,
        recheck=True,
        progress=lines.append,
        environment=lambda command: {"PATH": os.environ["PATH"], "MARK": command},
        version=lambda command, env: f"{command} 1.0",
    )
    result = matrix.run()
    cells = {c.name: c for c in result.cells}
    assert {n: c.status for n, c in cells.items()} == {
        "rel/none": "fail",
        "rel/checks": "fail",  # its value differs from the reference (exact tolerance)
        "rel/sanitize": "fail",  # a leak, not rechecked: runtime checks cannot locate it
        "rel/strict": "fail",
        "nv/none": "fail",
        "nv/checks": "ok",
        "nv/sanitize": "unsupported",
        "nv/strict": "fail",
        "nag/none": "skipped",
        "nag/checks": "skipped",
        "nag/sanitize": "skipped",
        "nag/strict": "skipped",
    }
    assert cells["rel/none"].recheck == [
        {"test": "t1", "status": "failed", "problem": "index 5 of x", "crash": {"kind": "bounds"}}
    ]
    assert cells["rel/checks"].cases[0]["verify"] == {"status": "fail", "failed": ["zeta2"]}
    assert cells["nv/strict"].build == {"status": "error", "problem": "missing module m"}
    assert cells["nv/none"].cases[0]["problem"] == "failed (exit 139): Segmentation fault"
    assert cells["nv/none"].setup == "module load nvhpc" and cells["nv/none"].version == "sh 1.0"
    assert "no-such-compiler-xyz not found" in cells["nag/none"].reason
    nested = [(args, mark) for args, mark in fake.calls if args[0] != "introspect" and "nv" in args]
    assert nested and all(mark == "module load nvhpc" for _, mark in nested)
    rechecks = [args for args, _ in fake.calls if "--filter" in args]
    assert rechecks == [["test", "--mode", "rel", "--shadow", "checks", "--filter", "t1", "--json"]]  # once per mode
    builds = [args for args, _ in fake.calls if args[0] == "build"]
    assert all("--force-compile" in args for args in builds)  # never the stale objects of another environment
    assert [(d.case, d.quantity, d.cell, d.baseline) for d in result.disagreements] == [
        ("s", "zeta2", "rel/checks", "rel/none")
    ]
    assert not result.ok and result.to_dict()["counts"] == {"fail": 6, "ok": 1, "unsupported": 1, "skipped": 4}
    assert lines[0] == "rel/none (gnu)"
    text = render_text(result, ["none", "checks", "sanitize", "strict"])
    assert text.splitlines()[:4] == [
        "mode  none      checks    sanitize  strict",
        "rel   FAIL      FAIL      FAIL      FAIL",
        "nv    FAIL      ok        n/a       FAIL",
        "nag   skipped   skipped   skipped   skipped",
    ]
    assert "  test t1: guard overwritten" in text
    assert "  test t2: memory leak (LeakSanitizer): 8 byte(s) leaked in 1 allocation(s)" in text
    assert cells["rel/sanitize"].recheck == []
    assert "  recheck of test t1 with --shadow checks: failed: index 5 of x" in text
    assert "  case s: differs from its reference (zeta2)" in text
    assert "  s.zeta2: rel/checks vs rel/none: fail at exact (max abs 9.99e-15, max rel 6.07e-15, worst at [0]" in text
    only_nv = Matrix(["rel", "nv"], ["none"], fake, compilers=["nvfortran"], version=lambda c, e: "")
    assert [c.mode for c in only_nv.run().cells] == ["nv"]


# ── fobis matrix for real ──────────────────────────────────────────────────────


def test_matrix_cli(project, capsys):
    code, out, err = _run(["matrix", "--shadows", "none,checks,strict", "--verify", "--json"], capsys)
    data = json.loads(out)
    cells = {f"{c['mode']}/{c['shadow']}": c for c in data["cells"]}
    assert code == 1 and data["status"] == "fail" and "matrix: rel/checks (gnu)" in err
    assert cells["rel/none"]["status"] == "ok" and cells["rel/none"]["version"].startswith("GNU Fortran")
    assert cells["rel/checks"]["tests"]["failures"][0]["problem"] == (
        "floating-point exception at test/test_uninit.f90:9"
    )
    assert cells["rel/strict"]["status"] == "ok"
    assert cells["rel/strict"]["cases"] == [{"case": "series", "status": "ok"}]
    assert not os.path.exists("build")  # the matrix never builds in the user's build directory
    assert sorted(os.listdir(SHADOW_ROOT)) == ["rel-checks", "rel-none", "rel-strict"]
    for args, message in (
        (["matrix", "--modes", "dbg"], "unknown mode 'dbg'"),
        (["matrix", "--shadows", "fast"], "unknown shadow 'fast'"),
    ):
        code, out, _ = _run(args, capsys)
        assert code == 2 and message in out
