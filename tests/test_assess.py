"""Tests for ``fobis assess`` (phase V4 of PLAN-verification.md): the statistics against analytic answers (orders
with constant and varying ratios, Richardson, GCI, convergence types, chi-square quantiles, significant digits,
correlation, elasticity), the ``[assess:CASE]`` declaration and its errors, editing a member's inputs (namelist,
key = value, regex, argument, environment), each family's analysis on synthetic runs, budgets, and real gfortran
assessments of programs whose answers are known (trapezoid quadrature: order 2; a model with known elasticities;
a single-precision sum against its promoted build), the build variants and the CLI."""

from __future__ import annotations

import json
import math
import os
from argparse import Namespace

import pytest

from fobis.fobis import run_fobis
from fobis.verification import LocalRunner, Quantity, RunResult, stats
from fobis.verification.assess import (
    AssessError,
    Assessment,
    Budget,
    FamilyResult,
    Member,
    analyse,
    check_budgets,
    current_value,
    parse_parameter,
    parse_spec,
    with_values,
)
from fobis.verification.case import parse_case
from fobis.verification.runner import BuildVariant
from fobis.verification.shadow import VARIANT_ROOT, apply_variant

# ── statistics ─────────────────────────────────────────────────────────────────


def test_observed_order():
    h = [0.4, 0.2, 0.1]
    order = stats.observed_order(h, [1 + 0.3 * x**2 for x in h])
    assert order.order == pytest.approx(2.0) and order.convergence == "monotonic"
    assert order.extrapolated == pytest.approx(1.0) and order.error == pytest.approx(0.003)
    assert order.gci == pytest.approx(1.25 * (0.3 * 0.04 - 0.3 * 0.01) / (1 + 0.003) / 3)
    varying = [0.3, 0.2, 0.1]  # ratios 1.5 and 2: Celik's iteration
    assert stats.observed_order(varying, [2 + 0.5 * x**1.5 for x in varying]).order == pytest.approx(1.5)
    oscillating = stats.observed_order(h, [1 + 0.3 * (-1) ** i * x**2 for i, x in enumerate(h)])
    assert oscillating.convergence == "oscillatory" and oscillating.order == pytest.approx(2.0)
    assert stats.observed_order(h, [1.0, 2.0, 4.0]).convergence == "divergent"
    assert stats.observed_order(h, [1.0, 1.0, 1.0]).convergence == "exact"
    assert stats.observed_order(h, [1.0, 2.0, 2.0]).convergence == "stalled"
    four = [0.8, 0.4, 0.2, 0.1]
    found = stats.orders(four, [1 + x**2 for x in four])
    assert len(found) == 2 and stats.asymptotic(found) is True
    assert stats.asymptotic(stats.orders(four, [1 + 0.01 * x + x**4 for x in four])) is False  # order 4 -> 1
    assert stats.asymptotic(found[:1]) is None


def test_ensemble_statistics():
    assert stats.chi2_quantile(0.05, 1) == pytest.approx(0.00393, abs=1e-5)  # exact
    assert stats.chi2_quantile(0.05, 2) == pytest.approx(0.1026, abs=1e-4)  # exact
    assert stats.chi2_quantile(0.05, 10) == pytest.approx(3.940, rel=0.01)  # Wilson-Hilferty
    digits, low = stats.significant_digits([1.0, 1.0 + 1e-8, 1.0 - 1e-8])
    assert digits == pytest.approx(8.0) and low < digits
    assert stats.significant_digits([2.0, 2.0]) == (math.inf, math.inf)
    assert stats.significant_digits([1e-3, -1e-3]) == (0.0, 0.0)  # around zero: no relative digit
    assert stats.significant_digits([1.0, math.nan]) == (0.0, 0.0)
    assert stats.digits_against(1.0001, 1.0) == pytest.approx(4.0) and stats.digits_against(3.0, 3.0) == math.inf
    assert stats.correlation([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0) and stats.correlation([1, 1], [1, 2]) is None
    assert stats.elasticity(2.0, 4.0, 1.99, 3.9601, 2.01, 4.0401) == pytest.approx(2.0)
    points = stats.over_points([5.0, 3.0, 9.0, 4.0])
    assert (points.minimum, points.worst, points.median) == (3.0, 1, 4.5)


# ── the declaration ────────────────────────────────────────────────────────────


def test_spec():
    spec = parse_spec(
        "sod",
        {
            "families": "precision, refinement inputs",
            "precision": "kind16: -DRKIND=16\n-freal-8-real-16",
            "threads": "1 2",
            "inputs": "k: namelist in.nml k rel 1e-3\nseed: env SEED uniform 1 9",
            "refine": "n: arg 1 values 10 20 40 inverse",
            "budget": "rho: digits >= 6; err: order >= 1.8\nm: error < 1e-6",
            "samples": "8",
        },
    )
    assert spec.families == ["precision", "refinement", "inputs"] and spec.threads == [1, 2] and spec.samples == 8
    assert spec.precision == {"kind16": "-DRKIND=16", "-freal-8-real-16": "-freal-8-real-16"}
    assert [(p.name, p.kind, p.spec, p.numbers) for p in spec.inputs] == [
        ("k", "namelist", "rel", [1e-3]),
        ("seed", "env", "uniform", [1.0, 9.0]),
    ]
    assert spec.refine.inverse and spec.refine.raw_values == ["10", "20", "40"]
    assert [b.text() for b in spec.budgets] == ["rho: digits >= 6", "err: order >= 1.8", "m: error < 1e-06"]
    assert parse_spec("x", None).families == ["rounding"]
    for items, message in (
        ({"familes": "x"}, "unknown key"),
        ({"families": "speed"}, "unknown family speed"),
        ({"inputs": "k: file in.nml k rel 1"}, "is not 'NAME: namelist"),
        ({"inputs": "k: arg n rel 1"}, "argument's position"),
        ({"inputs": "k: regex a.txt x=\\S+ rel 1"}, "needs a group"),
        ({"inputs": "k: env"}, "takes 1 argument"),
        ({"inputs": "k: env K gauss 1 2"}, "'rel EPS', 'uniform A B'"),
        ({"refine": "n: arg 1 values 10 20"}, "at least 3"),
        ({"refine": "n: arg 1 values 10 20 40"}, "add 'inverse'"),
        ({"refine": "n: arg 1 steps 1 2 3"}, "'values V1"),
        ({"budget": "rho >= 6"}, "is not 'quantity:"),
        ({"threads": "two"}, "invalid literal"),
    ):
        with pytest.raises(AssessError, match=message):
            parse_spec("x", items)


def test_editing_inputs(tmp_path):
    (tmp_path / "in").mkdir()
    (tmp_path / "in" / "run.nml").write_text("&p\n  k = 3.0d0, dt=0.5 ! step\n/\n")
    (tmp_path / "in" / "cfg.txt").write_text("cells: 100\nname = sod\n")
    case = parse_case("c", {"target": "a.f90", "inputs": "in", "args": "x 40", "env": "SEED=3"})
    params = {
        "k": parse_parameter("k: namelist in/run.nml k rel 0.1"),
        "dt": parse_parameter("dt: namelist in/run.nml DT rel 0.1"),
        "cells": parse_parameter("cells: keyvalue in/cfg.txt cells rel 0.1"),
        "n": parse_parameter("n: arg 2 rel 0.1"),
        "seed": parse_parameter("seed: env SEED rel 0.1"),
        "re": parse_parameter("re: regex in/cfg.txt 'cells:\\s*(\\d+)' rel 0.1"),
    }
    assert {n: current_value(p, case, str(tmp_path)) for n, p in params.items()} == {
        "k": 3.0,
        "dt": 0.5,
        "cells": 100.0,
        "n": 40.0,
        "seed": 3.0,
        "re": 100.0,
    }
    edited, prepare = with_values(
        case, [(params["k"], "3.3"), (params["dt"], "0.25"), (params["n"], "80"), (params["seed"], "4")]
    )
    assert edited.args == ["x", "80"] and edited.env == {"SEED": "4"} and case.args == ["x", "40"]
    rundir = tmp_path / "run"
    (rundir / "in").mkdir(parents=True)
    (rundir / "in" / "run.nml").write_text((tmp_path / "in" / "run.nml").read_text())
    prepare(str(rundir))
    assert (rundir / "in" / "run.nml").read_text() == "&p\n  k = 3.3, dt=0.25 ! step\n/\n"
    assert (tmp_path / "in" / "run.nml").read_text().startswith("&p\n  k = 3.0d0")  # the project is untouched
    outside = parse_parameter("x: namelist other.nml x rel 0.1")
    with pytest.raises(AssessError, match="not among the case's inputs"):
        current_value(outside, case, str(tmp_path))
    with pytest.raises(AssessError, match="'x' is not a number"):
        current_value(parse_parameter("x: arg 1 rel 0.1"), case, str(tmp_path))


# ── analysis on synthetic runs ─────────────────────────────────────────────────


def _member(label, values, family="rounding", **fields):
    member = Member(label, family, **fields)
    quantities = [Quantity(name, list(v) if isinstance(v, list) else [v]) for name, v in values.items()]
    member.result = RunResult("c", label, "ok", 0, quantities=quantities)
    return member


def test_analysis():
    base = _member("base", {"x": 1.0, "a": [1.0, 2.0, 3.0]})
    rounding = [
        _member("O0", {"x": 1.0 + 1e-9, "a": [1.0, 2.0, 3.0]}),
        _member("fast", {"x": 1.0 + 1e-6, "a": [1.0, 2.0, 3.1]}),
    ]
    result = analyse("rounding", base, rounding, parse_spec("c", None))
    x, a = result.quantities["x"], result.quantities["a"]
    assert x["outlier"]["member"] == "fast" and 5.5 < x["digits"] < 6.5 and x["members"] == 3
    assert a["worst"] == "[2]" and a["digits_median"] == "inf"
    failed = _member("broken", {})
    failed.result.status, failed.result.stderr = "failed", "Segmentation fault\n"
    assert analyse("rounding", base, [failed], parse_spec("c", None)).failed == [
        {"member": "broken", "status": "failed", "detail": "Segmentation fault"}
    ]
    promoted = _member("precision-promoted", {"x": 1.001, "a": [1.0, 2.0, 3.0]})
    precision = analyse("precision", base, [promoted], None)
    assert (
        precision.quantities["x"]["digits"] == pytest.approx(3.0, rel=1e-3)
        and precision.quantities["a"]["digits"] == "inf"
    )
    parallel = [
        _member("t1-1", {"s": 2.0}, "parallel", group="threads=1"),
        _member("t1-2", {"s": 2.0}, "parallel", group="threads=1"),
        _member("t4-1", {"s": 2.0001}, "parallel", group="threads=4"),
        _member("t4-2", {"s": 2.0003}, "parallel", group="threads=4"),
    ]
    data = analyse("parallel", _member("base", {"s": 2.0}), parallel, None).quantities["s"]
    assert data["nondeterministic"] == [
        {"configuration": "threads=4", "runs": 2, "max_rel": pytest.approx(1e-4, rel=1e-3)}
    ]
    assert data["bitwise_identical"] is False
    spec = parse_spec("c", {"inputs": "k: env K rel 0.01\nd: env D rel 0.01"})
    oat = [
        _member("k-low", {"q": 0.99**2}, "inputs", params={"k": 0.99, "d": 1.0}, group="k"),
        _member("k-high", {"q": 1.01**2}, "inputs", params={"k": 1.01, "d": 1.0}, group="k"),
        _member("d-low", {"q": 1.0}, "inputs", params={"k": 1.0, "d": 0.99}, group="d"),
        _member("d-high", {"q": 1.0}, "inputs", params={"k": 1.0, "d": 1.01}, group="d"),
    ]
    data = analyse("inputs", _member("base", {"q": 1.0}), oat, spec).quantities["q"]
    assert data["elasticity"] == {"k": 2.0, "d": 0.0} and data["ranking"] == ["k", "d"]
    refine = [_member(f"n{n}", {"e": 1 / n**2}, "refinement", params={"h": 1 / n}) for n in (10, 20, 40, 80)]
    data = analyse("refinement", _member("base", {"e": 0.01}), refine, None).quantities["e"]
    assert data["order"] == pytest.approx(2.0) and data["asymptotic"] is True and data["convergence"] == "monotonic"
    echo = [_member(f"n{n}", {"n": n}, "refinement", params={"h": 1 / n}) for n in (10, 20, 40, 80)]
    data = analyse("refinement", _member("base", {"n": 10}), echo, None).quantities["n"]
    assert data == {"note": "the refined parameter itself (its values are the ladder's): not assessed"}
    last_bit = [_member("O3", {"x": 1.0 + 2 * 2.0**-52}), _member("fma", {"x": 1.0})]  # round-off: no outlier
    assert "outlier" not in analyse("rounding", _member("base", {"x": 1.0}), last_bit, None).quantities["x"]


def test_budgets():
    assessment = Assessment("c", "gnu")
    assessment.families = [
        FamilyResult("rounding", quantities={"x": {"digits": 7.2}}),
        FamilyResult("precision", quantities={"x": {"digits": 5.1}}),
        FamilyResult("refinement", quantities={"e": {"order": 1.95, "error": 2e-7}}),
    ]
    checks = check_budgets(
        assessment,
        [
            Budget("x", "digits", ">=", 6),
            Budget("e", "order", ">=", 1.9),
            Budget("e", "error", "<", 1e-6),
            Budget("y", "digits", ">=", 1),
        ],
    )
    assert [(c.actual, c.ok) for c in checks] == [(5.1, False), (1.95, True), (2e-7, True), (None, False)]
    only = Assessment("c", "gnu", families=[FamilyResult("rounding", quantities={})])
    skipped = check_budgets(only, [Budget("e", "order", ">=", 2)])[0]
    assert skipped.ok and skipped.note.startswith("skipped")


def test_build_variant():
    cliargs = Namespace(cflags="-O3", lflags="", build_dir="build/")
    apply_variant(cliargs, "rounding-O0", "-O0", "", "gnu")
    assert cliargs.cflags == "-c -O3 -O0" and cliargs.build_dir == os.path.join(VARIANT_ROOT, "gnu-rounding-O0")
    assert BuildVariant("v", "-O0", "-lm").args() == [
        "--variant",
        "v",
        "--variant-cflags",
        "-O0",
        "--variant-lflags",
        "-lm",
    ]


# ── real assessments ───────────────────────────────────────────────────────────

QUADRATURE = """\
program quadrature
use iso_fortran_env, only: real64
implicit none
integer :: n, i
character(32) :: arg
real(real64) :: h, s
call get_command_argument(1, arg)
read(arg, *) n
h = 1.0_real64 / n
s = 0.5_real64 * (exp(0.0_real64) + exp(1.0_real64))
do i = 1, n - 1
  s = s + exp(i * h)
end do
print '(a,es24.17)', 'integral = ', s * h
end program quadrature
"""
MODEL = """\
program model
use iso_fortran_env, only: real64
implicit none
real(real64) :: k = 0, dt = 0
integer :: u
namelist /params/ k, dt
open(newunit=u, file='input/model.nml', status='old')
read(u, nml=params)
close(u)
print '(a,es24.17)', 'q = ', k**2 * exp(-dt)
end program model
"""
NAIVE = """\
program naive
implicit none
real :: s
integer :: i
s = 0.0
do i = 1, 1000000
  s = s + 0.1
end do
print '(a,es15.8)', 'total = ', s
end program naive
"""


@pytest.fixture
def project(tmp_path, monkeypatch):
    repo = tmp_path / "proj"
    (repo / "src").mkdir(parents=True)
    (repo / "input").mkdir()
    (repo / "src" / "quadrature.f90").write_text(QUADRATURE)
    (repo / "src" / "model.f90").write_text(MODEL)
    (repo / "src" / "naive.f90").write_text(NAIVE)
    (repo / "input" / "model.nml").write_text("&params\n  k = 3.0,\n  dt = 0.5\n/\n")
    (repo / "fobos").write_text(
        "[modes]\nmodes = gnu\n\n[gnu]\ncompiler = gnu\nsrc = ./src/\nbuild_dir = ./build/\ncflags = -c -O2\n\n"
        "[case:quad]\ntarget = src/quadrature.f90\nargs = 8\nquantities = stdout\n\n"
        "[assess:quad]\nfamilies = refinement\nrefine = n: arg 1 values 8 16 32 64 inverse\n"
        "budget = integral: order >= 1.9\n\n"
        "[case:model]\ntarget = src/model.f90\ninputs = input/model.nml\nquantities = stdout\n\n"
        "[assess:model]\nfamilies = inputs parallel\nthreads = 1\nrepeats = 2\ninputs =\n"
        "    k: namelist input/model.nml k rel 1e-3\n    dt: namelist input/model.nml dt rel 1e-3\n\n"
        "[case:naive]\ntarget = src/naive.f90\nquantities = stdout\n\n"
        "[assess:naive]\nfamilies = precision\nbudget = total: digits >= 6; total: order >= 1\n"
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


def test_assess_refinement(project, capsys):
    code, out, err = _run(["assess", "quad"], capsys)
    assert code == 0 and "assess: run 5 member(s)" in err
    assert "integral: observed order 2.000 (triples: 2.000, 2.000), monotonic, asymptotic" in out
    assert "integral: order >= 1.9: 2 ok" in out
    code, out, _ = _run(["assess", "quad", "--json"], capsys)
    data = json.loads(out)
    refinement = data["families"][0]["quantities"]["integral"]
    assert data["status"] == "ok" and data["builds"] == 1 and data["runs"] == 5
    assert refinement["extrapolated"] == pytest.approx(math.e - 1, rel=1e-8)
    assert [level["h"] for level in refinement["levels"]] == [1 / 8, 1 / 16, 1 / 32, 1 / 64]


def test_assess_inputs_and_parallel(project, capsys):
    code, out, _ = _run(["assess", "model", "--json", "--jobs", "3"], capsys)
    data = json.loads(out)
    inputs, parallel = data["families"]
    elasticity = inputs["quantities"]["q"]["elasticity"]
    assert code == 0 and elasticity == {"k": pytest.approx(2.0), "dt": pytest.approx(-0.5)}
    assert parallel["quantities"]["q"] == {}  # one configuration, identical repeats
    assert (project / "input" / "model.nml").read_text() == "&params\n  k = 3.0,\n  dt = 0.5\n/\n"
    rundir = project / ".fobis" / "runs" / "model" / "assess-inputs-k-high" / "input" / "model.nml"
    assert "k = 3.003" in rundir.read_text()


def test_assess_precision_and_budgets(project, capsys):
    code, out, _ = _run(["assess", "naive"], capsys)
    assert code == 1  # a single-precision sum of a million 0.1: two digits survive
    assert "total: 2.0 digit(s) agree with precision-promoted: 100958.344 vs 100000" in out
    assert "total: digits >= 6: 2.0 FAILED" in out and "total: order >= 1: - skipped" in out
    runner = LocalRunner(".", variant=BuildVariant("precision-promoted", "-freal-4-real-8"))
    assert runner.introspect("gnu")["compiler"]["cflags"].endswith("-O2 -freal-4-real-8")
    for args, message in (
        (["assess", "nothere"], "unknown case 'nothere'"),
        (["assess", "quad", "--families", "speed"], "unknown family speed"),
        (["assess", "quad", "--families", "inputs"], "inputs: declare the parameters"),
    ):
        code, out, _ = _run(args, capsys)
        assert code == 2 and message in out
