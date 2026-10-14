"""Test-only dependencies (``:: dev`` in ``[dependencies]``): fetched like the others, used by ``fobis test``,
``doctests`` and ``check``, never by another build (even when its sources contain the dependency directory), skipped
by ``fetch --no-dev``, marked by ``tree`` and never shown for a dependency's own dependencies. Real git repositories
served as ``file://`` remotes, real gfortran builds."""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from fobis.fobis import run_fobis

pytestmark = pytest.mark.skipif(shutil.which("gfortran") is None or shutil.which("git") is None, reason="tools")


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _remote(root, name, files) -> str:
    """A git repository with *files*, committed; its file:// URL."""
    repo = root / "remotes" / name
    for path, text in files.items():
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(text)
    _git(repo, "init", "-q", "-b", "master")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init")
    return f"file://{repo}"


TESTKIT = "module testkit\ncontains\nsubroutine check(ok)\nlogical, intent(in) :: ok\nif (.not. ok) error stop 1\nend subroutine check\nend module testkit\n"
MATHLIB = "module mathlib\ncontains\npure integer function twice(i)\ninteger, intent(in) :: i\ntwice = 2 * i\nend function twice\nend module mathlib\n"


@pytest.fixture
def project(tmp_path, monkeypatch):
    testkit = _remote(tmp_path, "testkit", {"src/testkit.f90": TESTKIT})
    mathlib = _remote(tmp_path, "mathlib", {"src/mathlib.f90": MATHLIB})
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "test").mkdir()
    (root / "src" / "mylib.f90").write_text(
        "module mylib\nuse mathlib, only : twice\ncontains\ninteger function four()\nfour = twice(2)\n"
        "end function four\nend module mylib\n"
    )
    (root / "test" / "t_lib.f90").write_text(
        "program t_lib\nuse mylib, only : four\nuse testkit, only : check\ncall check(four() == 4)\nend program t_lib\n"
    )
    (root / "fobos").write_text(
        "[modes]\nmodes = debug lib\n\n"
        "[debug]\ncompiler = gnu\nsrc = ./src/ ./test/\nbuild_dir = ./build/debug/\n\n"
        "[lib]\ncompiler = gnu\nsrc = ./\nbuild_dir = ./build/lib/\ntarget = src/mylib.f90\nmklib = static\n\n"
        f"[dependencies]\nmathlib = {mathlib}\ntestkit = {testkit} :: dev\n"
    )
    monkeypatch.chdir(root)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    return root


def _run(args, capsys) -> tuple[int, str]:
    try:
        run_fobis(fake_args=args)
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def test_tests_use_it_and_the_library_does_not(project, capsys):
    assert _run(["fetch"], capsys)[0] == 0
    assert (project / ".fobis_deps" / "testkit").is_dir()
    code, out = _run(["test", "--mode", "debug", "--quiet"], capsys)
    assert code == 0 and "1 passed" in out
    # the library mode scans the whole project (src = ./), deps directory included: testkit is left out
    code, out = _run(["build", "--mode", "lib"], capsys)
    assert code == 0, out
    objects = sorted(p.name for p in (project / "build" / "lib" / "obj").iterdir() if p.suffix == ".o")
    assert "mathlib.o" in objects and "testkit.o" not in objects
    config = (project / ".fobis_deps" / ".deps_config.ini").read_text()
    assert "dev_src" in config and "testkit" in config.split("dev_src")[1]


def test_a_library_using_a_test_only_module_does_not_build(project, capsys):
    assert _run(["fetch"], capsys)[0] == 0
    (project / "src" / "bad.f90").write_text("module bad\nuse testkit\nend module bad\n")
    code, out = _run(["build", "--mode", "lib", "--target", "src/bad.f90"], capsys)
    assert code == 1 and "testkit" in out


def test_check_sees_the_test_only_modules(project, capsys):
    assert _run(["fetch"], capsys)[0] == 0
    code, out = _run(["check", "--mode", "debug", "--json"], capsys)
    assert code == 0 and json.loads(out[out.index("{") :])["unresolved"] == []


def test_no_dev_skips_it_and_keeps_an_existing_clone_out_of_builds(project, capsys):
    code, out = _run(["fetch", "--no-dev"], capsys)
    assert code == 0 and "skipped (--no-dev)" in out
    assert not (project / ".fobis_deps" / "testkit").exists()
    assert "testkit" not in (project / ".fobis_deps" / "fobos.lock").read_text()
    assert _run(["fetch"], capsys)[0] == 0  # fetched, then a production fetch: the clone stays, test-only
    assert "dev = true" in (project / ".fobis_deps" / "fobos.lock").read_text()
    assert _run(["fetch", "--no-dev"], capsys)[0] == 0
    assert "[testkit]" in (project / ".fobis_deps" / "fobos.lock").read_text()  # its lock entry kept
    assert "dev_src" in (project / ".fobis_deps" / ".deps_config.ini").read_text()
    code, out = _run(["build", "--mode", "lib"], capsys)
    assert code == 0 and "testkit.o" not in [p.name for p in (project / "build" / "lib" / "obj").iterdir()]


def test_tree_marks_it_and_dependents_never_see_it(project, capsys, tmp_path):
    assert _run(["fetch"], capsys)[0] == 0
    code, out = _run(["tree", "--json"], capsys)
    tree = json.loads(out[out.index("{") :])
    marks = {d["name"]: d["dev"] for d in tree["dependencies"]}
    assert code == 0 and marks == {"mathlib": False, "testkit": True}
    code, out = _run(["tree"], capsys)
    assert "testkit" in out and "[test only]" in out
    # a project using this one: this project's test-only dependency is not part of its tree
    _git(project, "init", "-q", "-b", "master")
    _git(project, "add", "fobos", "src", "test")
    _git(project, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init")
    user = tmp_path / "user"
    user.mkdir()
    (user / "fobos").write_text(f"[default]\ncompiler = gnu\n\n[dependencies]\nproj = file://{project}\n")
    shutil.copytree(project / ".fobis_deps" / "testkit", user / ".fobis_deps" / "testkit")  # even when present
    subprocess.run(["git", "clone", "-q", f"file://{project}", str(user / ".fobis_deps" / "proj")], check=True)
    import os

    os.chdir(user)
    code, out = _run(["tree", "--json"], capsys)
    (proj,) = json.loads(out[out.index("{") :])["dependencies"]
    assert [d["name"] for d in proj["dependencies"]] == ["mathlib"]
