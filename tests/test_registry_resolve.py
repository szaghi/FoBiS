"""Resolution, module collisions and provider hints (#209 R5): Minimal Version Selection on synthetic graphs (diamond,
project pins win, impossible ranges, branch conflicts, requirements of a superseded version dropped), ``fetch`` with
``[dependencies] transitive = true`` on real git remotes (diamond resolved as MVS predicts: the R5 exit criterion),
off by default, a planted module collision reported before compiling, and ``check`` naming the package that provides
a missing module from the cached indexes."""

from __future__ import annotations

import configparser
import json
import shutil

import pytest

from fobis.fobis import run_fobis
from fobis.registry.resolve import Requirement, ResolutionError, select
from fobis.UserConfig import UserConfig
from tests.registry_helpers import fobis_package, isolate, module_source, remote

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git")


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    isolate(monkeypatch, tmp_path)


# ── MVS on synthetic graphs ──────────────────────────────────────────────────

TAGS = {
    "u/a": ["v1.0.0", "v1.1.0", "v1.2.0", "v2.0.0"],
    "u/b": ["v1.0.0"],
    "u/c": ["v1.0.0"],
    "u/d": ["v1.0.0", "v1.3.0", "v1.4.0", "v1.9.0", "v2.0.0"],
}


def _graph(edges):
    """edges: {(name, tag): [Requirement, ...]} -> requirements_of."""

    def requirements_of(selection):
        return [Requirement(**r.__dict__) for r in edges.get((selection.name, selection.tag), [])]

    return requirements_of


def test_diamond_takes_the_highest_minimum():
    edges = {
        ("b", "v1.0.0"): [Requirement("d", "u/d", "^1.3")],
        ("c", "v1.0.0"): [Requirement("d", "u/d", "^1.4")],
    }
    chosen = select([Requirement("b", "u/b", "^1.0"), Requirement("c", "u/c", "^1.0")], TAGS.get, _graph(edges))
    assert chosen["u/d"].tag == "v1.4.0"  # not v1.9.0: the minimum, the same answer tomorrow
    assert chosen["u/d"].required_by == ["b", "c"] and not chosen["u/d"].root


def test_incompatible_ranges_conflict():
    edges = {
        ("b", "v1.0.0"): [Requirement("d", "u/d", "^1.3")],
        ("c", "v1.0.0"): [Requirement("d", "u/d", "^2.0")],
    }
    with pytest.raises(ResolutionError, match=r"d: c needs at least v2.0.0, but b requires \^1.3"):
        select([Requirement("b", "u/b", "^1.0"), Requirement("c", "u/c", "^1.0")], TAGS.get, _graph(edges))


def test_project_pin_wins_with_a_warning():
    edges = {("b", "v1.0.0"): [Requirement("d", "u/d", "^1.9")]}
    warnings = []
    chosen = select(
        [Requirement("b", "u/b", "^1.0"), Requirement("d", "u/d", tag="v1.3.0")], TAGS.get, _graph(edges),
        warn=warnings.append,
    )  # fmt: skip
    assert chosen["u/d"].tag == "v1.3.0" and "b requires d ^1.9" in warnings[0]


def test_requirements_of_a_superseded_version_are_dropped():
    # a@1.0 needs d ^1.9; a is raised to 1.2 by c, whose a@1.2 needs only d ^1.3: d stays at 1.3
    edges = {
        ("a", "v1.0.0"): [Requirement("d", "u/d", "^1.9")],
        ("a", "v1.2.0"): [Requirement("d", "u/d", "^1.3")],
        ("c", "v1.0.0"): [Requirement("a", "u/a", "^1.2")],
    }
    chosen = select([Requirement("a", "u/a", "^1.0"), Requirement("c", "u/c", "^1.0")], TAGS.get, _graph(edges))
    assert chosen["u/a"].tag == "v1.2.0" and chosen["u/d"].tag == "v1.3.0"


def test_branch_conflicts_and_missing_versions():
    edges = {
        ("b", "v1.0.0"): [Requirement("d", "u/d", ref="main")],
        ("c", "v1.0.0"): [Requirement("d", "u/d", ref="dev")],
    }
    with pytest.raises(ResolutionError, match="different branches/commits"):
        select([Requirement("b", "u/b", "^1.0"), Requirement("c", "u/c", "^1.0")], TAGS.get, _graph(edges))
    with pytest.raises(ResolutionError, match="no version satisfies"):
        select([Requirement("a", "u/a", "^3.0")], TAGS.get, _graph({}))


# ── fetch with transitive = true ─────────────────────────────────────────────


def _run(args, capsys):
    try:
        run_fobis(fake_args=args)
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def _with_deps(files, deps: dict[str, str]):
    files = dict(files)
    files["fobos"] += "\n[dependencies]\n" + "".join(f"{k} = {v}\n" for k, v in deps.items())
    return files


@pytest.fixture
def diamond(tmp_path, monkeypatch):
    """project -> b, c; b -> d ^1.3, c -> d ^1.4; d has 1.3.0, 1.4.0, 1.9.0."""
    d = remote(
        tmp_path, "d", fobis_package("dmod"), tags=("v1.3.0",), more={"v1.4.0": {"N": "4\n"}, "v1.9.0": {"N": "9\n"}}
    )
    b = remote(tmp_path, "b", _with_deps(fobis_package("bmod"), {"d": f"{d} :: semver=^1.3"}))
    c = remote(tmp_path, "c", _with_deps(fobis_package("cmod"), {"dee": f"{d}.git :: semver=^1.4"}))
    project = tmp_path / "proj"
    (project / "src").mkdir(parents=True)
    (project / "src" / "main.f90").write_text(
        "program main\nuse bmod\nuse cmod\nuse dmod\ncall bmod_hello()\ncall cmod_hello()\ncall dmod_hello()\n"
        "end program main\n"
    )
    (project / "fobos").write_text(
        "[modes]\nmodes = gnu\n\n[gnu]\ncompiler = gnu\nsrc = ./src/\nbuild_dir = ./build/\ntarget = src/main.f90\n\n"
        f"[dependencies]\ntransitive = true\nb = {b} :: semver=^1.0\nc = {c} :: semver=^1.0\n"
    )
    monkeypatch.chdir(project)
    return project


def _lock(project):
    config = configparser.RawConfigParser()
    config.read(project / ".fobis_deps" / "fobos.lock")
    return {s: dict(config.items(s)) for s in config.sections()}


@pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran")
def test_fetch_resolves_the_diamond_by_mvs(diamond, capsys):
    """The R5 exit criterion: d at 1.4.0 (the highest minimum), fetched once, built with the project."""
    code, out = _run(["fetch"], capsys)
    assert code == 0, out
    lock = _lock(diamond)
    assert lock["d"]["resolved"] == "v1.4.0" and lock["d"]["required_by"] == "b c"
    assert "transitive" not in lock and not (diamond / ".fobis_deps" / "dee").exists()
    code, out = _run(["build"], capsys)
    assert code == 0, out


def test_transitive_is_off_by_default(diamond, capsys):
    fobos = diamond / "fobos"
    fobos.write_text(fobos.read_text().replace("transitive = true\n", ""))
    assert _run(["fetch", "--no-build"], capsys)[0] == 0
    assert set(_lock(diamond)) == {"b", "c"}


def test_module_collision_reported_before_compiling(tmp_path, monkeypatch, capsys):
    one = remote(tmp_path, "one", fobis_package("one", modules=["one", "utils"]))
    two = remote(tmp_path, "two", fobis_package("two", modules=["two", "utils"]))
    project = tmp_path / "proj"
    project.mkdir()
    (project / "fobos").write_text(
        f"[modes]\nmodes = gnu\n\n[gnu]\ncompiler = gnu\n\n[dependencies]\none = {one}\ntwo = {two}\n"
    )
    monkeypatch.chdir(project)
    code, out = _run(["fetch", "--no-build"], capsys)
    assert code == 1 and "module utils is defined by one and two" in out


def test_check_names_the_provider_of_a_missing_module(tmp_path, monkeypatch, capsys):
    index = tmp_path / "idx"
    index.mkdir()
    (index / "index.toml").write_text('name = "lab"\n[package.penf]\nsource = "https://h/PENF"\nprovides = ["penf"]\n')
    UserConfig().set_indexes([("lab", str(index))])
    project = tmp_path / "proj"
    (project / "src").mkdir(parents=True)
    (project / "src" / "main.f90").write_text("program main\nuse penf\nend program main\n")
    (project / "src" / "other.f90").write_text(module_source("other"))
    (project / "fobos").write_text("[modes]\nmodes = gnu\n\n[gnu]\ncompiler = gnu\nsrc = ./src/\n")
    monkeypatch.chdir(project)
    code, out = _run(["check"], capsys)
    assert code == 1 and "penf: provided by lab:penf (https://h/PENF): fobis add lab:penf" in out
    code, out = _run(["check", "--json"], capsys)
    assert json.loads(out[out.index("{") :])["providers"] == {
        "penf": [{"package": "lab:penf", "source": "https://h/PENF"}]
    }


@pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran")
def test_build_diagnosis_names_the_provider(tmp_path, monkeypatch, capsys):
    index = tmp_path / "idx"
    index.mkdir()
    (index / "index.toml").write_text('name = "lab"\n[package.penf]\nsource = "https://h/PENF"\nprovides = ["penf"]\n')
    UserConfig().set_indexes([("lab", str(index))])
    project = tmp_path / "proj"
    (project / "src").mkdir(parents=True)
    (project / "src" / "main.f90").write_text("program main\nuse penf\nend program main\n")
    (project / "fobos").write_text("[modes]\nmodes = gnu\n\n[gnu]\ncompiler = gnu\nsrc = ./src/\nbuild_dir = ./b/\n")
    monkeypatch.chdir(project)
    _, out = _run(["build", "--json"], capsys)
    diagnoses = json.loads(out[out.index("{") :])["diagnoses"]
    missing = next(d for d in diagnoses if d["kind"] == "missing-module")
    assert "penf is provided by lab:penf (https://h/PENF), listed in your package indexes." in missing["facts"]
    assert "run `fobis add lab:penf`, then `fobis fetch`" in missing["advice"]
