"""Tests for ``fobis gate`` (phase V9 of PLAN-verification.md): the ``[gate]`` declaration, the first failing fact
of every stage's JSON document, the stage loop (build failure skips the dependent stages, advisory stages, fail-fast,
a command without JSON is an error), and the command for real with gfortran on a git project (applicability and
skip reasons, a result change caught by verify and diff-run, ``--base`` with uncommitted changes reviewed)."""

from __future__ import annotations

import json
import subprocess

import pytest

from fobis.fobis import run_fobis
from fobis.verification import gate as g

GIT = ["git", "-c", "user.name=T", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]


class FakeFobos:
    def __init__(self, text):
        import configparser

        self.fobos = configparser.RawConfigParser()
        self.fobos.optionxform = str
        self.fobos.read_string(text)


def test_config():
    config = g.load_config(
        FakeFobos(
            "[gate]\nstages = build test verify\nskip = test\nadvisory = verify\nbase = main\nmatrix_modes = a, b\n"
        )
    )
    assert config.stages == ["build", "verify"] and config.advisory == {"verify"} and config.base == "main"
    assert config.matrix_modes == ["a", "b"] and config.matrix_shadows == ["none", "checks"]
    assert g.load_config(FakeFobos("[modes]\nmodes = a\n")).stages == list(g.STAGES)
    with pytest.raises(g.GateError, match="unknown key"):
        g.load_config(FakeFobos("[gate]\nstage = build\n"))
    with pytest.raises(g.GateError, match="unknown gate stage"):
        g.load_config(FakeFobos("[gate]\nstages = build lint\n"))


def test_facts():
    build = {
        "status": "error",
        "diagnoses": [{"summary": "module m is not available when p.f90 is compiled"}],
        "diagnostics": [{"file": "p.f90", "line": 2, "message": "Cannot open module file"}],
    }
    assert g.build_facts(build) == [
        "module m is not available when p.f90 is compiled",
        "p.f90:2: Cannot open module file",
    ]
    assert g.build_facts({"status": "ok"}) == [] and g.build_facts({"status": "error"}) == ["the build failed"]
    review = {"findings": [{"path": "a.f90", "line": 3, "rule": "STY001", "severity": "info", "message": "x"}] * 2}
    review["findings"].append({"path": "a.f90", "line": 9, "rule": "COR101", "severity": "warning", "message": "y"})
    assert g.review_facts(review) == ["a.f90:9: COR101 y"]
    test = {
        "results": [
            {"name": "t_ok", "status": "passed"},
            {"name": "t_b", "status": "failed", "notes": [{"summary": "index 4 of a is above 3 at t.f90:5"}]},
            {"name": "t_c", "status": "failed", "crash": {"message": "SIGSEGV", "file": "c.f90", "line": 7}},
        ]
    }
    assert g.test_facts(test) == ["t_b: failed: index 4 of a is above 3 at t.f90:5", "t_c: failed: SIGSEGV c.f90:7"]
    quantity = {
        "name": "x",
        "status": "fail",
        "count": 4,
        "out_of_tolerance": 1,
        "tolerance": "exact",
        "max_rel": 0.1,
        "worst": {"index": "[2]", "value": 1.1, "reference": 1.0},
    }
    verify = {"cases": [{"case": "a", "status": "pass"}, {"case": "b", "status": "fail", "quantities": [quantity]}]}
    verify["cases"].append({"case": "c", "status": "no-reference"})
    assert g.verify_facts(verify) == [
        "b: fail: x fail (1/4 out of exact, max rel 0.1), worst at [2]: 1.1 vs 1.0",
        "c: no reference (fobis verify c --update, once right)",
    ]
    run_failed = {"case": "d", "status": "new-failed", "run": {"status": "failed", "stderr": "boom\nERROR STOP 3"}}
    diff = {
        "cases": [{"case": "a", "status": "equivalent"}, run_failed],
        "changed": [{"path": "m.f90", "procedures": ["m::s"]}],
    }
    assert g.diff_run_facts(diff) == ["d: new-failed: run failed: ERROR STOP 3", "changed: m.f90 (m::s)"]
    regression = {
        "procedure": "axpy",
        "category": "vectorized loop",
        "old": 1,
        "new": 0,
        "lines": ["k.f90:9"],
        "regression": True,
    }
    slower = {"verdict": "slower", "speedup": 0.5, "interval": [0.4, 0.6], "against": "HEAD"}
    bench = {"cases": [{"case": "k", "status": "ok", "comparison": slower, "feedback": [regression]}]}
    assert g.bench_facts(bench) == [
        "k: slower than HEAD, speedup 0.500 [0.400, 0.600]; axpy: vectorized loop 1 -> 0 at k.f90:9"
    ]
    assess = {"case": "s", "status": "fail", "budgets": [{"budget": "q: digits >= 10", "actual": 7.5, "ok": False}]}
    assert g.assess_facts(assess) == ["s: budget q: digits >= 10 not met (actual 7.5)"]
    cell = {
        "mode": "gnu",
        "shadow": "checks",
        "status": "fail",
        "tests": {"failures": [{"name": "t", "problem": "bounds"}]},
    }
    disagreement = {"case": "c", "quantity": "q", "cell": "nvf/none", "baseline": "gnu/none", "max_rel": 1e-3}
    assert g.matrix_facts({"cells": [cell], "disagreements": [disagreement]}) == [
        "gnu/checks: test t: bounds",
        "c.q: nvf/none disagrees with gnu/none (max rel 0.001)",
    ]


def test_run_gate():
    config = g.GateConfig(stages=["build", "review", "test", "verify"], advisory={"review"})
    plan = g.Plan(commands={s: [[s, "--json"]] for s in config.stages}, skipped={})
    finding = {"path": "a.f90", "line": 1, "rule": "COR1", "severity": "error", "message": "x"}
    replies = {
        "build": (1, '{"status": "error", "diagnoses": [{"summary": "module m is missing"}]}', ""),
        "review": (0, json.dumps({"findings": [finding]}), ""),
    }
    calls = []

    def run(args):
        calls.append(args[0])
        return replies[args[0]]

    results = g.run_gate(config, plan, run)
    assert [(r.name, r.status) for r in results] == [
        ("build", "fail"),
        ("review", "fail"),
        ("test", "skipped"),
        ("verify", "skipped"),
    ]
    assert results[2].fact == "not run: the build failed" and calls == ["build", "review"]
    assert results[0].fact == "module m is missing" and g.verdict(results) == "fail"
    assert not results[1].blocking  # advisory
    results = g.run_gate(config, plan, run, fail_fast=True)
    assert results[1].fact == "not run: an earlier stage failed (--fail-fast)"
    no_json = g.run_gate(g.GateConfig(stages=["test"]), g.Plan({"test": [["test"]]}), lambda a: (2, "", "Error: x"))
    assert no_json[0].status == "error" and no_json[0].fact == "fobis test gave no result: Error: x"
    skipped = g.run_gate(g.GateConfig(stages=["matrix"]), g.Plan(skipped={"matrix": "no matrix"}), run)
    assert skipped[0].status == "skipped" and g.verdict(skipped) == "pass"
    text = g.render_text(results, 1.0, "main")
    assert text.startswith("gate: FAIL (base main)") and "build     FAIL" in text


# ── the command, for real ──────────────────────────────────────────────────────

MODULE = (
    "module m\nimplicit none\ncontains\npure function f(x) result(y)\nreal, intent(in) :: x\nreal :: y\n"
    "y = 2 * x\nend function f\nend module m\n"
)
PROGRAM = "program app\nuse m\nimplicit none\nprint '(a,f8.3)', 'value = ', f(1.5)\nend program app\n"
TEST = "program t_f\nuse m\nimplicit none\nif (abs(f(1.0) - 2.0) > 1e-6) error stop 1\nend program t_f\n"


def run_fobis_ok(args):
    try:
        run_fobis(fake_args=args)
    except SystemExit as exc:
        return not exc.code
    return True


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    for path, text in {"src/m.f90": MODULE, "src/app.f90": PROGRAM, "test/t_f.f90": TEST}.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text)
    (root / "fobos").write_text(
        "[modes]\nmodes = gnu\n\n[gnu]\ncompiler = gnu\nsrc = ./src/ ./test/\nbuild_dir = ./build/\ncflags = -c -O1\n\n"
        "[case:app]\ntarget = src/app.f90\nquantities = stdout\n"
    )
    (root / ".gitignore").write_text("build/\n.fobis/\n")
    monkeypatch.chdir(root)
    subprocess.run([*GIT, "init", "-q", "-b", "master"], check=True)
    assert run_fobis_ok(["verify", "--update"])
    for args in (["add", "."], ["commit", "-qm", "feat: app"]):
        subprocess.run([*GIT, *args], check=True, capture_output=True)
    return root


def _gate(capsys, *args):
    try:
        run_fobis(fake_args=["gate", "--json", *args])
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    captured = capsys.readouterr()
    data = json.loads(captured.out) if captured.out.strip().startswith("{") else None
    return code, data, captured.out + captured.err


def test_gate(project, capsys):
    code, data, _ = _gate(capsys)
    stages = {s["stage"]: s for s in data["stages"]}
    assert code == 0 and data["status"] == "pass"
    assert {n: s["status"] for n, s in stages.items()} == {
        "build": "pass",
        "review": "skipped",
        "test": "pass",
        "verify": "pass",
        "diff-run": "skipped",
        "bench": "skipped",
        "assess": "skipped",
        "matrix": "skipped",
    }
    assert "no change against HEAD" in stages["review"]["fact"] and "[bench:NAME]" in stages["bench"]["fact"]
    (project / "src" / "m.f90").write_text(MODULE.replace("y = 2 * x", "y = 2 * x + 0.5"))  # the result changes
    code, data, _ = _gate(capsys, "--skip", "test")
    stages = {s["stage"]: s for s in data["stages"]}
    assert code == 1 and data["status"] == "fail" and "test" not in stages
    assert stages["verify"]["fact"].startswith("app: fail: value fail") and "3.5 vs 3.0" in stages["verify"]["fact"]
    assert stages["diff-run"]["status"] == "fail" and "changed: src/m.f90 (m::f)" in stages["diff-run"]["details"]
    subprocess.run([*GIT, "checkout", "-q", "-b", "topic"], check=True)
    subprocess.run([*GIT, "commit", "-qam", "fix: offset"], check=True)
    (project / "src" / "m.f90").write_text(MODULE.replace("y = 2 * x", "if (x > 0) &\n  y = 2 * x\n"))
    code, data, _ = _gate(capsys, "--base", "master", "--stage", "review,diff-run", "--advisory", "diff-run")
    stages = {s["stage"]: s for s in data["stages"]}
    assert data["base"].startswith("master (merge base ")
    assert stages["review"]["status"] == "fail" and "COR101" in stages["review"]["fact"]  # uncommitted line reviewed
    assert stages["review"]["commands"][0][-3:] == ["--base", stages["diff-run"]["commands"][0][1], "--worktree"]
    for args, message in (
        (["--stage", "lint"], "unknown gate stage"),
        (["--base", "nope"], "'nope' is not a revision"),
    ):
        code, _, out = _gate(capsys, *args)
        assert code == 2 and message in out
