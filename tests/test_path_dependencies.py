"""Local path dependencies (issue #206 step 5): ``name = path=DIR [:: use=fobos] [:: mode=X] [:: dev]``."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import pytest

from fobis.Ecosystem import Ecosystem, _cells, stage_dependent
from fobis.Fetcher import Fetcher
from tests.test_ecosystem import git, git_env, make_project  # noqa: F401

needs_gfortran = pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran not on PATH")

UTILS = """module utils
implicit none
contains
integer function twice(i)
integer, intent(in) :: i
twice = 2*i
end function
end module
"""
CORE = """module core
implicit none
contains
integer function triple(i)
integer, intent(in) :: i
triple = 3*i
end function
end module
"""
CORE_FOBOS = """[modes]
modes = lib

[lib]
compiler = gnu
src = ./src/
build_dir = ./build/
mod_dir = ./mod/
obj_dir = ./obj/
mklib = static
target = core.f90
output = libcore.a
"""
APP = """program app
use utils
use core
implicit none
print '(2I4)', twice(2), triple(2)
end program
"""


def fobis(cwd, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "fobis", *args], cwd=cwd, capture_output=True, text=True)


def app_fobos(deps: str) -> str:
    head = "[default]\ncompiler = gnu\nsrc = ./src/\nbuild_dir = ./build/\ntarget = app.f90\noutput = app\n\n"
    return head + "[dependencies]\n" + deps + "\n"


@pytest.fixture
def siblings(tmp_path):
    """utils/ (sources, no fobos), core/ (a fobos library), app/ using both through path dependencies."""
    (tmp_path / "utils" / "src").mkdir(parents=True)
    (tmp_path / "utils" / "src" / "utils.f90").write_text(UTILS)
    (tmp_path / "core" / "src").mkdir(parents=True)
    (tmp_path / "core" / "src" / "core.f90").write_text(CORE)
    (tmp_path / "core" / "fobos").write_text(CORE_FOBOS)
    (tmp_path / "app" / "src").mkdir(parents=True)
    (tmp_path / "app" / "src" / "app.f90").write_text(APP)
    (tmp_path / "app" / "fobos").write_text(app_fobos("utils = path=../utils\ncore  = path=../core :: use=fobos"))
    return tmp_path


def run_app(app) -> str:
    return subprocess.run([str(app / "build" / "app")], capture_output=True, text=True, check=True).stdout.strip()


# ---------------------------------------------------------------------------
# Declaring
# ---------------------------------------------------------------------------


def test_parse_path_spec():
    fetcher = Fetcher(".fobis_deps")
    assert fetcher.parse_dep_spec("path=../core :: use=fobos :: mode=lib") == {
        "path": "../core",
        "use": "fobos",
        "mode": "lib",
    }
    assert fetcher.parse_dep_spec("path=libs/x :: dev") == {"path": "libs/x", "dev": "true"}


@pytest.mark.parametrize("spec", ["path=../c :: tag=v1", "path=../c :: semver=^1", "path=../c :: rev=a :: branch=b"])
def test_a_path_takes_no_pin(spec):
    with pytest.raises(ValueError, match="cannot take"):
        Fetcher(".fobis_deps").parse_dep_spec(spec)


def test_empty_path_refused():
    with pytest.raises(ValueError, match="needs a directory"):
        Fetcher(".fobis_deps").parse_dep_spec("path= :: use=fobos")


def test_resolve_path_is_relative_to_the_fobos():
    assert Fetcher.resolve_path("../core", "fobos") == os.path.normpath("../core")
    assert Fetcher.resolve_path("../core", "projects/app/fobos") == os.path.normpath("projects/core")
    assert Fetcher.resolve_path("/opt/core", "projects/app/fobos") == "/opt/core"


def test_path_excludes(tmp_path):
    dep = tmp_path / "dep"
    dep.mkdir()
    (dep / "fobos").write_text(
        "[a]\nbuild_dir = ./build/\n[b]\nbuild_dir = ./\n[c]\nbuild_dir = $root/x\n[dependencies]\ndeps_dir = vendor\n"
    )
    excluded = Fetcher.path_excludes(str(dep))
    assert excluded == [str(dep / ".git"), str(dep / ".fobis"), str(dep / "vendor"), str(dep / "build")]


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------


@needs_gfortran
def test_sources_and_fobos_modes_build_without_fetch(siblings):
    app = siblings / "app"
    result = fobis(app, "build")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Compiling ../utils/src/utils.f90" in result.stdout  # compiled with the project
    assert (siblings / "core" / "build" / "libcore.a").is_file()  # built by its own fobos
    assert run_app(app) == "4   6"
    assert not (app / ".fobis_deps").exists()  # nothing fetched, nothing written


@needs_gfortran
def test_a_change_in_the_sibling_rebuilds(siblings):
    app = siblings / "app"
    assert fobis(app, "build").returncode == 0
    for path, old, new in (("utils/src/utils.f90", "2*i", "20*i"), ("core/src/core.f90", "3*i", "30*i")):
        source = siblings / path
        source.write_text(source.read_text().replace(old, new))
        stamp = os.stat(source).st_mtime + 5
        os.utime(source, (stamp, stamp))
    result = fobis(app, "build")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Compiling ../utils/src/utils.f90" in result.stdout
    assert run_app(app) == "40  60"


@needs_gfortran
def test_the_siblings_own_deps_and_scratch_are_not_scanned(siblings):
    utils = siblings / "utils"
    for hidden in (".fobis_deps/x", ".fobis/scratch", ".git"):  # each holds a second copy of module utils
        (utils / hidden).mkdir(parents=True)
        (utils / hidden / "copy.f90").write_text(UTILS)
    result = fobis(siblings / "app", "build")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "copy.f90" not in result.stdout


@needs_gfortran
def test_a_sibling_sharing_the_projects_name_prefix_is_scanned(tmp_path):
    """``core-utils`` next to the project ``core``: not covered by the project's ./ source path."""
    (tmp_path / "core-utils").mkdir()
    (tmp_path / "core-utils" / "utils.f90").write_text(UTILS)
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "app.f90").write_text("program app\nuse utils\nprint '(I4)', twice(4)\nend program\n")
    fobos = "[default]\ncompiler = gnu\nsrc = ./\nbuild_dir = ./build/\ntarget = app.f90\noutput = app\n\n"
    (tmp_path / "core" / "fobos").write_text(fobos + "[dependencies]\nutils = path=../core-utils\n")
    result = fobis(tmp_path / "core", "build")
    assert result.returncode == 0, result.stdout + result.stderr
    assert run_app(tmp_path / "core") == "8"


@needs_gfortran
def test_a_test_only_path_dependency_is_left_out_of_a_build(siblings):
    app = siblings / "app"
    deps = "utils = path=../utils\ncore = path=../core :: use=fobos\nkit = path=../kit :: dev"
    (app / "fobos").write_text(app_fobos(deps))
    (siblings / "kit").mkdir()
    (siblings / "kit" / "kit.f90").write_text("module kit\nend module\n")
    result = fobis(app, "build")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "kit.f90" not in result.stdout
    check = json.loads(fobis(app, "check", "--json").stdout)  # check scans the tests: it loads them
    assert {"name": "kit", "path": "../kit", "use": "sources", "dev": True} in check["path_dependencies"]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("command", ["build", "fetch", "check"])
def test_missing_directory_exit_1(siblings, command):
    app = siblings / "app"
    (app / "fobos").write_text(app_fobos("utils = path=../nowhere"))
    result = fobis(app, command)
    assert result.returncode == 1
    assert "path dependency 'utils': directory ../nowhere not found" in result.stdout + result.stderr


@pytest.mark.parametrize("command", ["build", "fetch"])
def test_path_with_tag_exit_2(siblings, command):
    app = siblings / "app"
    (app / "fobos").write_text(app_fobos("utils = path=../utils :: tag=v1.0.0"))
    result = fobis(app, command)
    assert result.returncode == 2
    assert "[dependencies] utils: the path dependency ../utils cannot take tag" in result.stdout + result.stderr


# ---------------------------------------------------------------------------
# Fetch and the lock
# ---------------------------------------------------------------------------


def read_lock(app) -> dict[str, dict[str, str]]:
    return Fetcher(str(app / ".fobis_deps")).load_lock()


@needs_gfortran
def test_fetch_locks_git_and_plain_directories(siblings, git_env):  # noqa: F811
    core = siblings / "core"
    git(core, "init", "-q")
    (core / ".gitignore").write_text("build/\n")
    git(core, "add", "-A")
    git(core, "commit", "-q", "-m", "init")
    app = siblings / "app"
    result = fobis(app, "fetch")
    assert result.returncode == 0, result.stdout + result.stderr
    lock = read_lock(app)
    assert lock["core"] == {"path": "../core", "commit": git(core, "rev-parse", "HEAD"), "dirty": "false"}
    assert set(lock["utils"]) == {"path", "sha256"} and len(lock["utils"]["sha256"]) == 64
    assert (core / "build" / "libcore.a").is_file()  # fetch builds a use=fobos one, as for a clone
    config = (app / ".fobis_deps" / ".deps_config.ini").read_text()
    assert "core" not in config and "utils" not in config  # builds read path dependencies from the fobos

    (core / "build" / "extra.o").write_text("")  # an ignored output: not a change
    (core / "notes.txt").write_text("x")  # an untracked non-source: not a change
    assert Fetcher.path_state(str(core))["dirty"] == "false"
    (core / "src" / "new.f90").write_text("module new\nend module\n")  # an untracked source: a change
    assert Fetcher.path_state(str(core))["dirty"] == "true"


def test_frozen_warns_on_a_changed_path_dependency_and_keeps_the_lock(siblings):
    app = siblings / "app"
    assert fobis(app, "fetch", "--no-build").returncode == 0
    before = (app / ".fobis_deps" / "fobos.lock").read_text()
    utils = siblings / "utils" / "src" / "utils.f90"
    utils.write_text(utils.read_text() + "! edited\n")
    result = fobis(app, "fetch", "--frozen", "--no-build")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "path dependency 'utils' is at content" in result.stdout + result.stderr
    assert (app / ".fobis_deps" / "fobos.lock").read_text() == before
    result = fobis(app, "fetch", "--no-build")  # not frozen: recorded again, no warning
    assert "Warning" not in result.stdout + result.stderr
    assert (app / ".fobis_deps" / "fobos.lock").read_text() != before


def test_fetch_json(siblings):
    result = fobis(siblings / "app", "fetch", "--json", "--no-build")
    doc = json.loads(result.stdout)
    assert doc["status"] == "ok"
    assert [(d["name"], d["path"], d["local"]) for d in doc["dependencies"]] == [
        ("utils", "../utils", True),
        ("core", "../core", True),
    ]


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


def test_tree_shows_the_path(siblings):
    app = siblings / "app"
    tree = json.loads(fobis(app, "tree", "--json").stdout)
    assert [(d["name"], d.get("path"), d["fetched"], d["has_fobos"]) for d in tree["dependencies"]] == [
        ("utils", "../utils", True, False),
        ("core", "../core", True, True),
    ]
    (app / "fobos").write_text(app_fobos("utils = path=../gone"))
    assert "[directory ../gone not found]" in fobis(app, "tree").stdout


def test_check_lists_them_and_resolves_fobos_mode_modules(siblings):
    app = siblings / "app"
    result = fobis(app, "check")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Path dependency core: ../core (use=fobos)" in result.stdout
    assert "unreachable" not in result.stdout + result.stderr  # core's module is provided by its sources
    doc = json.loads(fobis(app, "check", "--json").stdout)
    assert doc["status"] == "ok" and doc["unresolved"] == []
    assert [d["name"] for d in doc["path_dependencies"]] == ["utils", "core"]


def test_introspect_dependencies(siblings):
    doc = json.loads(fobis(siblings / "app", "introspect", "--dependencies").stdout)
    assert doc["dependencies"]["core"]["path"] == "../core"
    assert doc["dependencies"]["core"]["use"] == "fobos"


def test_fpm_export_writes_a_path_dependency(siblings):
    result = fobis(siblings / "app", "fpm", "export", "--print")
    assert 'utils = { path = "../utils" }' in result.stdout


# ---------------------------------------------------------------------------
# Ecosystem
# ---------------------------------------------------------------------------


def test_ecosystem_links_pins_and_stages_a_path_dependency(git_env, tmp_path):  # noqa: F811
    root = git_env
    make_project(root, "core")
    app = make_project(root, "app", {"mycore": "path=../core :: use=fobos"})
    eco = Ecosystem([str(root / "core"), str(app)])
    assert eco.projects["app"].deps == ["core"]  # matched by its directory, not by its key
    assert eco.projects["app"].path_deps == {"mycore": str(root / "core")}

    status = next(s for s in eco.collect(fetch=False, ci=False) if s.name == "app")
    assert [(p.dep, p.state, p.path) for p in status.pins] == [("core", "path", "../core")]
    assert status.state != "stale"
    assert _cells(status)[-1][0] == "core at ../core"

    (root / "core" / "new.f90").write_text("module new\nend module\n")  # uncommitted: staged too
    work = tmp_path / "stage"
    work.mkdir()
    stage = stage_dependent(eco, "app", "core", str(work))
    assert (work / "core" / "new.f90").is_file()  # next to the staged app, where path=../core finds it
    assert os.path.normpath(os.path.join(stage, "../core")) == str(work / "core")
