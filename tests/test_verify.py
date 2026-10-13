"""Tests for ``fobis verify`` (phase V2 of PLAN-verification.md): tolerances, element-wise comparison (worst point
with its Fortran or C index, norms, non-finite values), references, the verification of a case (run failed, no
reference, pass and fail with the provenance changes, repeated runs), the runner's rebuild guard (no record,
changed compiler or flags, objects touched by another build) and the CLI on a real project (update, pass, an
injected bug located, non-determinism refused as a reference)."""

from __future__ import annotations

import contextlib
import json
import math
import os
import subprocess

import pytest

from fobis.fobis import run_fobis
from fobis.verification import LocalRunner, Quantity, RunResult
from fobis.verification.case import CaseError, parse_case
from fobis.verification.verify import (
    Reference,
    Tolerance,
    VerifyError,
    compare,
    index_text,
    load_reference,
    save_reference,
    verify,
)

SIM = """\
program sim
use iso_fortran_env, only: real64
implicit none
integer :: i, u
real(real64) :: x(2, 3)
x = reshape([(1.0_real64 / i, i = 1, 6)], [2, 3])
print '(a,es23.16)', 'total = ', sum(x)
open(newunit=u, file='x.bin', form='unformatted', status='replace')
write(u) x
close(u)
end program sim
"""
NOISY = """\
program noisy
implicit none
real(8) :: r
call random_number(r)
print *, 'r = ', r
end program noisy
"""


# ── tolerances and comparison ──────────────────────────────────────────────────


def test_tolerance():
    assert Tolerance.parse("") == Tolerance() and Tolerance.parse("exact").exact
    t = Tolerance.parse("abs 1e-10 rel 1e-8")
    assert t.equal(1.0 + 5e-9, 1.0) and not t.equal(1.0 + 5e-8, 1.0) and t.equal(1e-11, 0.0)
    ulp = Tolerance.parse("ulp 2")
    assert ulp.equal(1.0 + 2 * math.ulp(1.0), 1.0) and not ulp.equal(1.0 + 3 * math.ulp(1.0), 1.0)
    exact = Tolerance()
    assert exact.equal(math.nan, math.nan) and not exact.equal(math.nan, 1.0) and exact.equal(math.inf, math.inf)
    assert not exact.equal(math.inf, -math.inf) and not exact.equal(1.0 + math.ulp(1.0), 1.0)
    assert t.text() == "abs 1e-10 rel 1e-08" and exact.text() == "exact"
    for bad, message in (("rel", "pairs"), ("abs x", "needs a number"), ("abs -1", "negative"), ("tol 1", "not abs")):
        with pytest.raises(VerifyError, match=message):
            Tolerance.parse(bad)


def test_index_text():
    assert index_text(0, None, "C") == "[0]" and index_text(4, [6], "F") == "(5)"
    assert index_text(5, [2, 3], "F") == "(2,3)" and index_text(1, [2, 3], "F") == "(2,1)"
    assert index_text(5, [2, 3], "C") == "[1][2]" and index_text(1, [2, 3], "C") == "[0][1]"


def test_compare():
    ref = Quantity("x", [1.0, 2.0, 3.0, 4.0], [2, 2], "F")
    same = compare(Quantity("x", [1.0, 2.0, 3.0, 4.0], [2, 2], "F"), ref, Tolerance())
    assert same.status == "pass" and same.max_abs == 0.0 and same.worst is None
    changed = compare(Quantity("x", [1.0, 2.0, 3.5, 4.0], [2, 2], "F"), ref, Tolerance())
    assert (changed.status, changed.out_of_tolerance, changed.max_abs) == ("fail", 1, 0.5)
    assert changed.worst == {"index": "(1,2)", "value": 3.5, "reference": 3.0} and changed.max_rel == 0.5 / 3
    loose = compare(Quantity("x", [1.0, 2.0, 3.5, 4.0], [2, 2], "F"), ref, Tolerance(rel=0.2))
    assert loose.status == "pass" and loose.max_abs == 0.5  # within tolerance, the error still reported
    nan = compare(Quantity("x", [1.0, math.nan, 3.0, 4.0], [2, 2], "F"), ref, Tolerance(abs=1.0))
    assert nan.status == "fail" and nan.nonfinite == ["(2,1): nan (reference 2.0)"]
    both_nan = compare(Quantity("y", [math.nan]), Quantity("y", [math.nan]), Tolerance())
    assert both_nan.status == "pass"
    shape = compare(Quantity("x", [1.0, 2.0]), ref, Tolerance())
    assert shape.status == "shape" and shape.note == "2 value(s) vs 4 shape [2, 2] in the reference"


def _result(quantities, status="ok", provenance=None, case="c") -> RunResult:
    return RunResult(case, "default", status, exit_code=0, quantities=quantities, provenance=provenance or {})


def test_references_round_trip(tmp_path):
    path = str(tmp_path / "refs" / "c.json")
    assert load_reference(path) is None
    result = _result([Quantity("x", [1.0, math.nan, -math.inf], [3], "F")], provenance={"mode": "gnu"})
    save_reference(path, result)
    loaded = load_reference(path)
    assert loaded.case == "c" and loaded.provenance == {"mode": "gnu"} and loaded.created
    x = loaded.quantities["x"]
    assert x.values[0] == 1.0 and math.isnan(x.values[1]) and x.values[2] == -math.inf
    assert (x.shape, x.order) == ([3], "F")
    (tmp_path / "bad.json").write_text("[1, 2]")
    with pytest.raises(VerifyError, match="not a FoBiS reference"):
        load_reference(str(tmp_path / "bad.json"))


def test_verify_outcomes():
    reference = Reference("c", {"a": Quantity("a", [1.0]), "gone": Quantity("gone", [2.0])}, {"mode": "gnu"})
    failed = verify([_result([], status="timeout")], reference, {})
    assert failed.status == "run-failed" and failed.note == "the run is timeout"
    assert verify([_result([Quantity("a", [1.0])])], None, {}).status == "no-reference"
    result = _result([Quantity("a", [1.0]), Quantity("extra", [5.0])], provenance={"mode": "dbg"})
    outcome = verify([result], reference, {})
    statuses = {c.name: c.status for c in outcome.comparisons}
    assert outcome.status == "fail" and statuses == {"a": "pass", "gone": "missing", "extra": "new"}
    assert outcome.provenance_changes == ["mode: 'gnu' -> 'dbg'"]
    near = _result([Quantity("a", [1.0 + 1e-12])], provenance={"mode": "dbg"})
    passing = verify([near], Reference("c", {"a": Quantity("a", [1.0])}, {"mode": "gnu"}), {"*": "rel 1e-9"})
    assert passing.status == "pass" and passing.provenance_changes == ["mode: 'gnu' -> 'dbg'"]
    runs = [_result([Quantity("a", [1.0])]), _result([Quantity("a", [1.0])]), _result([Quantity("a", [1.5])])]
    repeated = verify(runs, Reference("c", {"a": Quantity("a", [1.0])}, {}), {})
    assert repeated.status == "nondeterministic" and [c.name for c in repeated.repeat] == ["a"]


def test_case_tolerance_declaration():
    case = parse_case("c", {"target": "a.f90", "tolerance": "rho: abs 1e-10 rel 1e-8; *: ulp 4\niters: exact"})
    assert case.tolerance == {"rho": "abs 1e-10 rel 1e-8", "*": "ulp 4", "iters": "exact"}
    with pytest.raises(CaseError, match="tolerance of rho: 'tol' is not abs"):
        parse_case("c", {"target": "a.f90", "tolerance": "rho: tol 1"})
    with pytest.raises(CaseError, match="is not 'quantity: spec'"):
        parse_case("c", {"target": "a.f90", "tolerance": "rel 1e-8"})


# ── a real project ─────────────────────────────────────────────────────────────


@pytest.fixture
def project(tmp_path, monkeypatch):
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text("[user]\n\tname = T\n\temail = t@t\n[commit]\n\tgpgsign = false\n[color]\n\tui = always\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    repo = tmp_path / "proj"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "sim.f90").write_text(SIM)
    (repo / "src" / "noisy.f90").write_text(NOISY)
    (repo / "fobos").write_text(
        "[modes]\nmodes = gnu\n\n[gnu]\ncompiler = gnu\nsrc = ./src/\nbuild_dir = ./build/\ncflags = -c -O0\n\n"
        "[case:sim]\ntarget = src/sim.f90\nquantities =\n    stdout\n    x : binary x.bin real64 [2,3]\n\n"
        "[case:noisy]\ntarget = src/noisy.f90\nquantities = stdout\n"
    )
    (repo / ".gitignore").write_text("build/\n.fobis/\n")
    subprocess.run(["git", "init", "-q", "-b", "master"], cwd=repo, check=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "feat: sim"], cwd=repo, check=True, capture_output=True)
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


def test_rebuild_guard(project, capsys):
    runner = LocalRunner(".")
    case = parse_case("sim", {"target": "src/sim.f90", "quantities": "stdout"})
    _, first = runner.build(case, None)
    assert first["rebuilt_because"] == "no record of how the objects were built"
    _, second = runner.build(case, None)
    assert "rebuilt_because" not in second
    with contextlib.suppress(SystemExit):  # another build in between
        run_fobis(fake_args=["build", "--force-compile", "--target", "src/sim.f90"])
    _, third = runner.build(case, None)
    assert third["rebuilt_because"] == "another build changed the objects since"
    record = os.path.join(runner.runs_dir, "bin", "sim-default.signature.json")
    with open(record) as handle:
        data = json.load(handle)
    data["signature"]["version"] = "GNU Fortran 1.0"  # as if another compiler had built the objects
    with open(record, "w") as handle:
        json.dump(data, handle)
    _, fourth = runner.build(case, None)
    assert fourth["rebuilt_because"] == "the compiler or its flags changed (version)"
    capsys.readouterr()


def test_cli(project, capsys):
    code, out, _ = _run(["verify", "sim"], capsys)
    assert code == 1 and "sim: NO-REFERENCE" in out
    code, out, _ = _run(["verify", "sim", "--update"], capsys)
    assert code == 0 and "sim: UPDATED (reference written to verification/references/sim.json)" in out
    code, out, _ = _run(["verify", "sim"], capsys)
    assert code == 0 and "sim: PASS" in out and "x: equal (6 value(s), exact)" in out
    (project / "src" / "sim.f90").write_text(SIM.replace("print '(a", "x(2,3) = -x(2,3)\nprint '(a"))
    code, out, _ = _run(["verify", "sim"], capsys)
    assert code == 1 and "sim: FAIL" in out
    assert "x: 1/6 out of tolerance (exact)" in out and "worst at (2,3): -0.16666666666666666 vs reference" in out
    assert "git.dirty: False -> True" in out
    code, out, _ = _run(["verify", "sim", "--json"], capsys)
    data = json.loads(out)["cases"][0]
    x = next(q for q in data["quantities"] if q["name"] == "x")
    assert data["status"] == "fail" and x["worst"]["index"] == "(2,3)" and x["out_of_tolerance"] == 1
    code, out, _ = _run(["verify", "noisy", "--update", "--repeat", "3"], capsys)
    assert code == 1 and "noisy: NONDETERMINISTIC (not updated: the repeated runs differ)" in out
    assert not os.path.exists("verification/references/noisy.json")
    code, _, _ = _run(["verify", "nothere"], capsys)
    assert code == 2
