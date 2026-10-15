"""``fobis new`` (issue #206 step 8): a project and a library built and tested for real with gfortran, the author from
git, no overwrite (exit 2, files untouched), invalid names, git initialised but nothing committed (and not inside an
existing repository), --json, and the templates read from a zip archive (the standalone fobis.pyz)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import zipfile

import pytest

from fobis import new
from fobis.fobis import run_fobis

pytestmark = pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran")


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A directory to create projects in, with a git identity of its own."""
    config = tmp_path / "gitconfig"
    config.write_text("[user]\n\tname = Ada Lovelace\n\temail = ada@example.org\n[init]\n\tdefaultBranch = main\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    return work


def _run(args, capsys):
    try:
        run_fobis(fake_args=args)
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    captured = capsys.readouterr()
    return code, captured.out, captured.out + captured.err  # run_fobis captures the command's stderr into out


def test_a_new_project_builds_and_tests(home, capsys, monkeypatch):
    code, out, _ = _run(["new", "demo"], capsys)
    assert code == 0 and "Created project demo in demo/ (git: initialised)" in out
    assert "Next: cd demo && fobis build && fobis test" in out
    project = home / "demo"
    files = sorted(str(p.relative_to(project)) for p in project.rglob("*") if p.is_file() and ".git" not in p.parts)
    assert files == [".gitignore", "app/main.f90", "fobos", "src/demo.f90", "test/test_demo.f90"]
    fobos = (project / "fobos").read_text()
    assert "name    = demo\n" in fobos and "authors = Ada Lovelace <ada@example.org>\n" in fobos
    assert "/build/\n/.fobis_deps/\n/.fobis/\n" in (project / ".gitignore").read_text()
    log = subprocess.run(["git", "log"], cwd=project, capture_output=True, text=True, check=False)
    assert log.returncode != 0  # a repository with no commit
    monkeypatch.chdir(project)
    assert _run(["build"], capsys)[0] == 0
    run = subprocess.run(["build/debug/demo"], capture_output=True, text=True, check=True)
    assert run.stdout.strip() == "mean of 1, 2, 3, 4:  2.5"
    code, out, _ = _run(["test", "--json"], capsys)
    assert code == 0 and json.loads(out)["passed"] == 1
    assert _run(["build", "--mode", "release"], capsys)[0] == 0 and (project / "build/release/demo").is_file()
    status = subprocess.run(["git", "status", "--short"], cwd=project, capture_output=True, text=True, check=True)
    assert "build" not in status.stdout  # ignored


def test_a_new_library(home, capsys, monkeypatch):
    code, out, _ = _run(["new", "kit", "--lib", "--no-git"], capsys)
    assert code == 0 and "Created library kit in kit/ (git: not initialised (--no-git))" in out
    project = home / "kit"
    assert not (project / "app").exists() and not (project / ".git").exists()
    monkeypatch.chdir(project)
    code, out, _ = _run(["test", "--json"], capsys)
    assert code == 0 and json.loads(out)["passed"] == 1
    for mode, library in (("release", "build/release/libkit.a"), ("shared", "build/shared/libkit.so")):
        assert _run(["build", "--mode", mode], capsys)[0] == 0 and (project / library).is_file()


def test_existing_files_are_never_overwritten(home, capsys, monkeypatch):
    target = home / "busy"
    (target / "src").mkdir(parents=True)
    (target / "fobos").write_text("keep\n")
    (target / "src" / "busy.f90").write_text("keep too\n")
    (target / "notes.txt").write_text("unrelated\n")
    monkeypatch.chdir(target)
    code, _, err = _run(["new", "."], capsys)
    assert code == 2 and "2 file(s) exist, nothing written" in err and "  fobos" in err and "  src/busy.f90" in err
    assert (target / "fobos").read_text() == "keep\n" and not (target / "app").exists()
    code, out, _ = _run(["new", ".", "--json"], capsys)
    assert code == 2 and json.loads(out)["conflicts"] == ["fobos", "src/busy.f90"]
    (target / "fobos").unlink()
    (target / "src" / "busy.f90").unlink()
    code, out, _ = _run(["new", ".", "--json"], capsys)
    document = json.loads(out)
    assert code == 0 and document["name"] == "busy" and "fobos" in document["files"]
    assert (target / "notes.txt").read_text() == "unrelated\n"


def test_names(home, capsys):
    code, _, err = _run(["new", "my-lib"], capsys)
    assert code == 2 and "'my-lib' is not a Fortran name" in err and "--name my_lib" in err
    assert not (home / "my-lib").exists()
    assert _run(["new", "9lives"], capsys)[0] == 2
    code, _, _ = _run(["new", "my-lib", "--name", "my_lib", "--compiler", "intel_nextgen", "--no-git"], capsys)
    assert code == 0 and "compiler      = intel_nextgen\n" in (home / "my-lib" / "fobos").read_text()
    assert (home / "my-lib" / "src" / "my_lib.f90").is_file()


def test_inside_a_repository_git_is_left_alone(home, capsys):
    subprocess.run(["git", "init", "-q"], cwd=home, check=True)
    code, out, _ = _run(["new", "inner"], capsys)
    assert code == 0 and "git: inside an existing repository: not initialised" in out
    assert not (home / "inner" / ".git").exists()


def test_templates_load_from_a_zip_archive(tmp_path, monkeypatch):
    """The standalone fobis.pyz is a zip: the templates are package resources, not files."""
    archive = tmp_path / "templates.zip"
    root = new.templates_root()
    with zipfile.ZipFile(archive, "w") as zf:
        for name in ("fobos", "fobos-lib", "gitignore", "module.f90", "main.f90", "test.f90"):
            zf.writestr(f"new/{name}", (root / name).read_text(encoding="utf-8"))
    monkeypatch.setattr(new, "templates_root", lambda: zipfile.Path(archive) / "new")
    contents = new.plan(str(tmp_path / "zipped"))
    assert "module zipped" in contents["src/zipped.f90"] and "output        = zipped" in contents["fobos"]
    assert os.path.basename(new.FILES["test.f90"]) == "test_{name}.f90"
