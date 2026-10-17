"""``fobis fetch`` fails (exit 1) when a dependency cannot be cloned, checked out at its pin or built, after fetching
the others, and says which; a dependency that was not cloned gets no lock entry and no deps-config entry.
``fetch --json`` runs the same fetch: semver ranges, the lock, the failures. ``fobis install REPO`` installs what the
cloned project's tracked build wrote (its paths are relative to the clone) and exits 1 when nothing was. Real git
repositories served as ``file://`` remotes, real gfortran builds."""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from fobis.Fetcher import Fetcher
from fobis.fobis import run_fobis

pytestmark = pytest.mark.skipif(shutil.which("gfortran") is None or shutil.which("git") is None, reason="tools")

MODULE = "module {name}\ncontains\npure integer function answer()\nanswer = 1\nend function answer\nend module {name}\n"


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _remote(root, name, tags=(), fobos=False, source=None) -> str:
    """A git repository holding one module (and a fobos when asked: True for a static library, or its text), with one
    commit per tag; its file:// URL."""
    repo = root / "remotes" / name
    (repo / "src").mkdir(parents=True)
    (repo / "src" / f"{name}.f90").write_text(source or MODULE.format(name=name))
    if fobos:
        default = "[default]\ncompiler = gnu\nsrc = ./src/\nmklib = static\n"
        (repo / "fobos").write_text(default if fobos is True else fobos)
    _git(repo, "init", "-q", "-b", "master")
    for index, tag in enumerate(tags or ["none"]):
        (repo / "VERSION").write_text(f"{index}\n")
        _git(repo, "add", "-A")
        _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-qm", tag)
        if tags:
            _git(repo, "-c", "tag.gpgsign=false", "tag", tag)
    return f"file://{repo}"


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    monkeypatch.chdir(root)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    return root


def _fobos(root, dependencies: str) -> None:
    (root / "fobos").write_text(f"[default]\ncompiler = gnu\nsrc = ./\n\n[dependencies]\n{dependencies}")


def _run(args, capsys) -> tuple[int, str, str]:
    try:
        run_fobis(fake_args=args)
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _lock(root) -> dict:
    return Fetcher(deps_dir=str(root / ".fobis_deps")).load_lock()


def test_a_clone_that_fails_fails_the_fetch_after_the_others(project, tmp_path, capsys):
    good = _remote(tmp_path, "good")
    _fobos(project, f"bad = file://{tmp_path}/no-such-repo\ngood = {good}\n")
    code, out, err = _run(["fetch"], capsys)
    assert code == 1
    assert "Error: 1 dependency step(s) failed:" in out + err and "bad: clone failed" in out + err
    assert (project / ".fobis_deps" / "good" / "src" / "good.f90").is_file()  # the others are still fetched
    assert set(_lock(project)) == {"good"}  # no entry with an empty commit
    assert "bad" not in (project / ".fobis_deps" / ".deps_config.ini").read_text()


def test_a_pin_that_does_not_exist_fails_the_fetch(project, tmp_path, capsys):
    _fobos(project, f"dep = {_remote(tmp_path, 'dep', tags=['v1.0.0'])} :: tag=v9.9.9\n")
    code, out, err = _run(["fetch"], capsys)
    assert code == 1 and "dep: checkout of v9.9.9 failed" in out + err


def test_a_library_dependency_that_cannot_be_built_fails_the_fetch(project, tmp_path, capsys):
    _fobos(project, f"nofobos = {_remote(tmp_path, 'nofobos')} :: use=fobos\n")
    code, out, err = _run(["fetch"], capsys)
    assert code == 1 and "nofobos: no fobos file to build it with (use=fobos)" in out + err
    assert _run(["fetch", "--no-build"], capsys)[0] == 0  # not built: nothing failed


def test_a_library_dependency_with_a_fobos_builds(project, tmp_path, capsys):
    _fobos(project, f"lib = {_remote(tmp_path, 'lib', fobos=True)} :: use=fobos\n")
    code, out, err = _run(["fetch"], capsys)
    assert code == 0, out + err


def test_json_runs_the_same_fetch(project, tmp_path, capsys):
    url = _remote(tmp_path, "ranged", tags=["v1.0.0", "v1.2.0", "v2.0.0"])
    _fobos(project, f"ranged = {url} :: semver=^1.0\n")
    code, out, _ = _run(["fetch", "--json"], capsys)
    doc = json.loads(out)
    assert code == 0 and doc["status"] == "ok" and doc["failures"] == []
    assert _lock(project)["ranged"]["resolved"] == "v1.2.0"  # the range resolved, and the lock written
    head = subprocess.run(
        ["git", "describe", "--tags"], cwd=project / ".fobis_deps" / "ranged", capture_output=True, text=True
    )
    assert head.stdout.strip() == "v1.2.0"


def test_json_reports_the_failures(project, tmp_path, capsys):
    _fobos(project, f"bad = file://{tmp_path}/no-such-repo\n")
    code, out, _ = _run(["fetch", "--json"], capsys)
    doc = json.loads(out)
    assert code == 1 and doc["status"] == "error" and doc["failures"] == ["bad: clone failed"]
    assert doc["dependencies"] == []


LIBRARY = (
    "[default]\ncompiler = gnu\ncflags = -c\nsrc = ./src/\nbuild_dir = ./build/\ntarget = src/one.f90\n"
    "mklib = static\noutput = libone.a\ntrack_build = True\n"
)


def test_install_from_a_repository_installs_what_its_build_tracked(project, tmp_path, capsys):
    url = _remote(tmp_path, "one", fobos=LIBRARY)
    prefix = tmp_path / "prefix"
    code, out, err = _run(["install", url, "--prefix", str(prefix), "--deps-dir", str(tmp_path / "deps")], capsys)
    assert code == 0, out + err
    assert (prefix / "lib" / "libone.a").is_file() and (prefix / "include" / "one.mod").is_file()


def test_install_from_a_repository_that_does_not_build_fails(project, tmp_path, capsys):
    url = _remote(tmp_path, "one", fobos=LIBRARY, source="module one\nthis is not fortran\nend module one\n")
    code, out, err = _run(["install", url, "--prefix", str(tmp_path / "p"), "--deps-dir", str(tmp_path / "d")], capsys)
    assert code == 1 and "one: build failed" in out + err
