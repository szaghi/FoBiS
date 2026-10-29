"""``fobis add`` (#209 R2): a name resolved once through the indexes and written into the fobos as a URL; ambiguous
names refused, qualified names and modules, pins, comments of the fobos kept; after ``add`` + ``fetch`` the build
needs no index (the R2 exit criterion). Real git repositories as ``file://`` remotes, real gfortran builds."""

from __future__ import annotations

import configparser
import json
import shutil

import pytest

from fobis.fobis import run_fobis
from fobis.registry.fobosedit import has_entry, remove_entry, set_entry
from fobis.UserConfig import UserConfig
from tests.registry_helpers import cli, fobis_package, isolate, remote

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git")


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    isolate(monkeypatch, tmp_path)


# ── the fobos editor ──────────────────────────────────────────────────────────


def test_set_entry_keeps_the_rest_of_the_file(tmp_path):
    fobos = tmp_path / "fobos"
    fobos.write_text(
        "# my project\n[modes]\nmodes = gnu\n\n[gnu]\n; the compiler\ncompiler = gnu\n\n"
        "[dependencies]\n# kinds\npenf = https://x/PENF :: tag=v1\n# trailing note\n\n[rule-x]\nrule = ls\n"
    )
    replaced = set_entry(
        str(fobos), "flap", "https://x/FLAP :: semver=^2.0.0", comment="added by fobis add from index m"
    )
    assert replaced is False
    text = fobos.read_text()
    assert text.startswith("# my project\n[modes]\nmodes = gnu\n\n[gnu]\n; the compiler\n")
    assert (
        "# trailing note\n# added by fobis add from index m\nflap = https://x/FLAP :: semver=^2.0.0\n\n[rule-x]" in text
    )
    assert set_entry(str(fobos), "PENF", "https://x/PENF :: tag=v2") is True
    assert "# kinds\nPENF = https://x/PENF :: tag=v2\n" in fobos.read_text()
    config = configparser.RawConfigParser()
    config.read(fobos)
    assert dict(config.items("dependencies")) == {
        "penf": "https://x/PENF :: tag=v2",
        "flap": "https://x/FLAP :: semver=^2.0.0",
    }
    assert remove_entry(str(fobos), "flap") and not has_entry(str(fobos), "flap")
    assert "added by fobis add" not in fobos.read_text()


def test_set_entry_creates_the_section(tmp_path):
    fobos = tmp_path / "fobos"
    fobos.write_text("[modes]\nmodes = gnu\n\n\n")
    set_entry(str(fobos), "a", "https://x/a")
    assert fobos.read_text() == "[modes]\nmodes = gnu\n\n[dependencies]\na = https://x/a\n"


# ── fobis add ─────────────────────────────────────────────────────────────────


@pytest.fixture
def world(tmp_path, monkeypatch):
    """Two indexes (mine, vendor) sharing the name 'json'; a project using module penf."""
    penf = remote(tmp_path, "PENF", fobis_package("penf", "kinds"), tags=("v1.0.0",), more={"v1.2.3": {"NEWS": "x\n"}})
    json_a = remote(tmp_path, "json-a", fobis_package("jsona"))
    json_b = remote(tmp_path, "json-b", fobis_package("jsonb"))
    untagged = remote(tmp_path, "untagged", fobis_package("untagged"), tags=())
    for name, packages in (
        ("mine", {"penf": (penf, ["penf"]), "json": (json_a, ["jsona"]), "untagged": (untagged, [])}),
        ("vendor", {"json": (json_b, ["jsonb"])}),
    ):
        lines = [f'name = "{name}"']
        for pname, (source, provides) in packages.items():
            lines += [f"[package.{pname}]", f'source = "{source}"', f"provides = {json.dumps(provides)}"]
        (tmp_path / name).mkdir()
        (tmp_path / name / "index.toml").write_text("\n".join(lines) + "\n")
    config = str(tmp_path / "config.ini")
    UserConfig(path=config).set_indexes([("mine", str(tmp_path / "mine")), ("vendor", str(tmp_path / "vendor"))])
    project = tmp_path / "proj"
    (project / "src").mkdir(parents=True)
    (project / "src" / "main.f90").write_text("program main\nuse penf\ncall penf_hello()\nend program main\n")
    (project / "fobos").write_text(
        "[modes]\nmodes = gnu\n\n[gnu]\ncompiler = gnu\nsrc = ./src/\nbuild_dir = ./build/\ntarget = src/main.f90\n"
    )
    monkeypatch.chdir(project)
    return {"config": config, "penf": penf, "json_a": json_a, "json_b": json_b, "project": project, "root": tmp_path}


def _deps(project) -> dict[str, str]:
    config = configparser.RawConfigParser()
    config.read(project / "fobos")
    return dict(config.items("dependencies"))


def test_add_by_name_writes_the_url_and_a_caret_range(world):
    code, out = cli("add", "penf", "--config", world["config"])
    assert code == 0 and "Added penf" in out
    assert _deps(world["project"]) == {"penf": f"{world['penf']} :: semver=^1.2.3"}
    assert "# added by fobis add from index mine" in (world["project"] / "fobos").read_text()
    code, out = cli("add", "penf", "--config", world["config"])
    assert code == 2 and "already has dependency penf" in out


def test_ambiguous_name_is_refused_and_qualified_name_accepted(world):
    code, out = cli("add", "json", "--config", world["config"])
    assert code == 2 and "mine:json" in out and "vendor:json" in out
    assert "dependencies" not in (world["project"] / "fobos").read_text()
    code, out = cli("add", "vendor:json", "--config", world["config"], "--json")
    assert code == 0 and json.loads(out)["source"] == world["json_b"]


def test_add_by_module_url_and_pins(world):
    code, out = cli("add", "--module", "JSONA", "--config", world["config"], "--use", "fobos", "--dev")
    assert code == 0 and _deps(world["project"])["json"] == f"{world['json_a']} :: semver=^1.0.0 :: use=fobos :: dev"
    code, out = cli("add", world["penf"], "--tag", "v1.0.0", "--as", "kinds", "--config", world["config"])
    assert code == 0 and _deps(world["project"])["kinds"] == f"{world['penf']} :: tag=v1.0.0"
    code, out = cli("add", world["penf"], "--tag", "v9", "--as", "k9", "--config", world["config"])
    assert code == 1 and "has no tag v9" in out
    code, out = cli("add", "penf", "--tag", "v1.0.0", "--branch", "x", "--config", world["config"])
    assert code == 2 and "not --tag and --branch" in out
    code, out = cli("add", "untagged", "--config", world["config"])
    assert code == 0 and "no semantic-version tag" in out and _deps(world["project"])["untagged"].endswith("untagged")


def test_add_needs_a_fobos(world, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, out = cli("add", "penf", "--config", world["config"])
    assert code == 2 and "fobis new" in out


@pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran")
def test_build_needs_no_index_after_add(world, capsys):
    """The R2 exit criterion: after add + fetch, every index can disappear and the build still works."""
    assert cli("add", "penf", "--config", world["config"])[0] == 0
    shutil.rmtree(world["root"] / "mine")
    shutil.rmtree(world["root"] / "vendor")
    for args in (["fetch"], ["build"]):
        try:
            run_fobis(fake_args=args)
        except SystemExit as exc:
            assert not exc.code, capsys.readouterr().out
    assert (world["project"] / "build" / "main").is_file()
