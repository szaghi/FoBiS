"""Tests for the structured output for agents and scripts (phase G): ``build --json`` with the parsed diagnostics
and the deterministic diagnoses of a failure, ``check --json``, ``tree --json`` (each dependency with its OWN
version), ``test --json`` (passed, crashed with its facts, build failed with its diagnoses), ``merge-assist
--format json``, ``commit --show-facts --json`` and ``ask --show-context --json``. Real gfortran builds and real git
repositories."""

from __future__ import annotations

import json
import subprocess

import pytest
from typer.testing import CliRunner

from fobis.cli import app
from fobis.fobis import run_fobis

MODULE = "module m\nimplicit none\ncontains\npure integer function twice(i)\ninteger, intent(in) :: i\ntwice = 2*i\n"
MODULE += "end function twice\nend module m\n"


def _git(repo, *args) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def gitenv(tmp_path, monkeypatch):
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text("[user]\n\tname = T\n\temail = t@t\n[commit]\n\tgpgsign = false\n[color]\n\tui = always\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))


@pytest.fixture
def project(tmp_path, monkeypatch):
    """Sources in src/, tests in test/ (all scanned), a debug mode with bounds checking."""
    (tmp_path / "src").mkdir()
    (tmp_path / "test").mkdir()
    (tmp_path / "src" / "m.f90").write_text(MODULE)
    (tmp_path / "test" / "t_ok.f90").write_text(
        "program t_ok\nuse m\nif (twice(2) /= 4) error stop 1\nend program t_ok\n"
    )
    (tmp_path / "test" / "t_bounds.f90").write_text(
        "program t_bounds\nuse m\ninteger :: a(3), i\ni = twice(2)\na(i) = 1\nprint *, a\nend program t_bounds\n"
    )
    (tmp_path / "fobos").write_text(
        "[default]\ncompiler = gnu\nsrc = ./\nbuild_dir = ./build/\ncflags = -c -g -O0 -fcheck=all -fbacktrace\n"
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _json(args, capsys) -> tuple[int, dict]:
    try:
        run_fobis(fake_args=args)
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    out = capsys.readouterr().out
    return code, json.loads(out)


def test_build_json_diagnoses_a_failure(project, capsys):
    (project / "src" / "p.f90").write_text("program p\nuse missing_mod\nimplicit none\nend program p\n")
    code, data = _json(["build", "--json", "--target", "src/p.f90"], capsys)
    assert code == 1 and data["status"] == "error"
    (diagnostic,) = [d for d in data["diagnostics"] if d["severity"] == "fatal"]
    assert (diagnostic["tool"], diagnostic["file"], diagnostic["line"]) == ("gnu", "./src/p.f90", 2)
    (diagnosis,) = data["diagnoses"]
    assert diagnosis["kind"] == "missing-module" and diagnosis["advice"]
    code, data = _json(["build", "--json", "--target", "src/m.f90"], capsys)
    assert code == 0 and data["status"] == "ok" and "diagnoses" not in data


def test_check_json(project, capsys):
    code, data = _json(["check", "--json"], capsys)
    assert code == 0 and data == {"status": "ok", "files": 3, "unresolved": [], "warnings": []}
    (project / "test" / "t_bad.f90").write_text("program t_bad\nuse nothere\nend program t_bad\n")
    code, data = _json(["check", "--json"], capsys)
    assert code == 1 and data["unresolved"] == [{"file": "./test/t_bad.f90", "dependency": "nothere", "type": "module"}]


def test_build_json_errors_are_errors_only(project, capsys):
    """A post_build rule's log and its command's output are not errors; the compiler's message is listed once."""
    (project / "fobos").write_text(
        (project / "fobos").read_text() + "post_build = hello\n\n[rule-hello]\nrule = echo hello from a rule\n"
    )
    code, data = _json(["build", "--json", "--target", "src/m.f90"], capsys)
    assert code == 0 and data["errors"] == []
    (project / "src" / "p.f90").write_text("program p\nuse missing_mod\nimplicit none\nend program p\n")
    code, data = _json(["build", "--json", "--target", "src/p.f90"], capsys)
    assert code == 1 and sum("Cannot open module file" in e for e in data["errors"]) == 1


def test_check_json_sees_the_fetched_dependencies(project, capsys):
    """The modules of a fetched dependency (use=sources) are resolved, as by build."""
    deps = project / ".fobis_deps"
    (deps / "dep").mkdir(parents=True)
    (deps / "dep" / "d.f90").write_text("module d\nend module d\n")
    (deps / ".deps_config.ini").write_text("[deps]\nsrc = .fobis_deps/dep\n")
    (project / "src" / "m.f90").write_text(MODULE.replace("implicit none", "use d\nimplicit none", 1))
    (project / "fobos").write_text((project / "fobos").read_text().replace("src = ./", "src = ./src/ ./test/"))
    code, data = _json(["check", "--json"], capsys)
    assert code == 0 and data["unresolved"] == []


def test_test_json(project, capsys):
    (project / "test" / "t_bad.f90").write_text("program t_bad\nuse nothere\nend program t_bad\n")
    code, data = _json(["test", "--json"], capsys)
    results = {r["name"]: r for r in data["results"]}
    assert code == 1 and (data["passed"], data["failed"]) == (1, 2)
    assert results["t_ok"]["status"] == "passed"
    bounds = results["t_bounds"]
    assert bounds["status"] == "failed" and bounds["crash"]["kind"] == "bounds"
    assert bounds["notes"][0]["summary"] == "index 4 of array a is above its upper bound 3 at ./test/t_bounds.f90:5"
    assert results["t_bad"]["status"] == "build-failed" and results["t_bad"]["diagnoses"][0]["kind"] == "missing-module"
    code, data = _json(["test", "--json", "--list"], capsys)
    assert code == 0 and sorted(t["name"] for t in data["tests"]) == ["t_bad", "t_bounds", "t_ok"]


def test_tree_json_gives_each_dependency_its_own_version(tmp_path, gitenv, monkeypatch, capsys):
    """Regression: the version of a dependency was the ROOT's tag (git describe ran in the cwd)."""
    root, deps = tmp_path / "app", tmp_path / "app" / "deps"
    for path, fobos, tag in (
        (root, "[project]\nname = app\n[dependencies]\ndeps_dir = deps\nlib = https://x/lib\n", "v9.0.0"),
        (deps / "lib", "[project]\nname = lib\n", "v1.2.3"),
    ):
        path.mkdir(parents=True)
        (path / "fobos").write_text(fobos)
        (path / ".gitignore").write_text("deps/\n")
        _git(path, "init", "-q", "-b", "master")
        _git(path, "add", ".")
        _git(path, "commit", "-qm", "feat: x")
        _git(path, "tag", tag)
    monkeypatch.chdir(root)
    _, data = _json(["tree", "--json"], capsys)
    assert (data["name"], data["version"]) == ("app", "v9.0.0")
    assert [(d["name"], d["version"], d["fetched"]) for d in data["dependencies"]] == [("lib", "v1.2.3", True)]


def test_merge_assist_and_commit_facts_json(tmp_path, gitenv, monkeypatch, capsys):
    (tmp_path / "m.f90").write_text("module m\ninteger :: a = 1\nend module m\n")
    _git(tmp_path, "init", "-q", "-b", "master")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "feat(m): add m")
    monkeypatch.chdir(tmp_path)
    code, data = _json(["merge-assist", "--format", "json"], capsys)
    assert data == {"operation": None, "files": [], "both_sides_touched": []}
    code, data = _json(["commit", "--show-facts", "--json"], capsys)
    assert code == 1 and data["staged"] is False
    (tmp_path / "m.f90").write_text("module m\n! the counter\ninteger :: a = 1\nend module m\n")
    _git(tmp_path, "add", ".")
    code, data = _json(["commit", "--show-facts", "--json"], capsys)
    assert code == 0 and data["files"][0]["lines"] == {"comment": 1}
    assert data["hints"][0]["type"] == "docs or style" and data["scopes"][0]["name"] == "m"
    with pytest.raises(SystemExit) as exc:
        run_fobis(fake_args=["merge-assist", "--format", "xml"])
    assert exc.value.code == 2


def test_ask_show_context_json():
    result = CliRunner().invoke(app, ["ask", "acc routine seq", "--show-context", "--json", "-k", "2"])
    data = json.loads(result.output)
    assert data["question"] == "acc routine seq" and [s["label"] for s in data["sources"]] == ["S1", "S2"]
    assert data["sources"][0]["id"].startswith("openacc:") and data["sources"][0]["text"]
