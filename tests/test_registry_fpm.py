"""fpm packages are built by fpm, never compiled by FoBiS: a fetched fpm dependency (its own fpm dependency comes with
it, a broken example or program does not stop its library, the project builds no program of it), the module
collision between what fpm brings and what the fobos fetches, ``pkg install`` (library, then applications as a second
step), and fpm missing."""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

from fobis.fobis import run_fobis
from fobis.registry import backends
from fobis.registry.toolchain import detect
from tests.registry_helpers import cli, isolate, remote

needs_fpm = pytest.mark.skipif(
    shutil.which("fpm") is None or shutil.which("gfortran") is None or shutil.which("git") is None,
    reason="fpm, gfortran and git",
)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    isolate(monkeypatch, tmp_path)


KINDSX = {
    "fpm.toml": 'name = "kindsx"\nversion = "1.0.0"\n',
    "src/kindsx.f90": "module kindsx\nimplicit none\ninteger, parameter :: rk = kind(1.d0)\nend module kindsx\n",
}


def vecs_package(kindsx_url: str, app: str = "print *, 'vecs app'") -> dict[str, str]:
    """An fpm library using another fpm package, with a demo that does not compile and an application."""
    return {
        "fpm.toml": f'name = "vecs"\nversion = "0.3.0"\n\n[dependencies]\nkindsx = {{ git = "{kindsx_url}" }}\n',
        "src/vecs.f90": "module vecs\nuse kindsx, only : rk\nimplicit none\ncontains\n"
        "pure real(rk) function norm2d(x, y)\nreal(rk), intent(in) :: x, y\nnorm2d = sqrt(x*x + y*y)\n"
        "end function norm2d\nend module vecs\n",
        "example/demo.f90": "program demo\ndo i = 1, 3\nend do\nend program demo\n",  # implicit i: fpm refuses it
        "app/vecs_app.f90": f"program vecs_app\n{app}\nend program vecs_app\n",
    }


CONSUMER = "program main\nuse vecs\nprint '(F4.1)', norm2d(3.0_8, 4.0_8)\nend program main\n"


def project(tmp_path, deps: str):
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.f90").write_text(CONSUMER)
    # no target: FoBiS builds every program it finds, so a dependency compiled as sources would bring its programs
    (root / "fobos").write_text(
        f"[modes]\nmodes = gnu\n\n[gnu]\ncompiler = gnu\nsrc = ./src/\nbuild_dir = ./build/\n\n[dependencies]\n{deps}"
    )
    return root


def fobis(*args, capsys):
    try:
        run_fobis(fake_args=list(args))
    except SystemExit as exc:
        return exc.code or 0, capsys.readouterr().out
    return 0, capsys.readouterr().out


@needs_fpm
def test_fpm_dependency_is_built_by_fpm(tmp_path, monkeypatch, capsys):
    kindsx = remote(tmp_path, "kindsx", KINDSX)
    vecs = remote(tmp_path, "vecs", vecs_package(kindsx), tags=("v0.3.0",))
    root = project(tmp_path, f"vecs = {vecs} :: semver=^0.3.0\n")
    monkeypatch.chdir(root)
    code, out = fobis("fetch", capsys=capsys)
    assert code == 0, out
    assert "Building vecs with fpm" in out
    prefix = root / ".fobis_deps" / ".prefix" / "vecs"
    # its own fpm dependency came with it (in its archive and its module files); fpm never saw the broken demo
    assert sorted(os.listdir(prefix / "include")) == ["kindsx.mod", "vecs.mod"]
    archive = subprocess.run(["ar", "t", str(prefix / "lib" / "libvecs.a")], capture_output=True, text=True).stdout
    assert "kindsx" in archive
    code, out = fobis("build", capsys=capsys)
    assert code == 0, out
    build = root / "build"
    programs = sorted(f.name for f in build.iterdir() if f.is_file() and os.access(f, os.X_OK))
    assert programs == ["main"]  # neither the dependency's demo nor its application
    run = subprocess.run([str(root / "build" / "main")], capture_output=True, text=True)
    assert run.stdout.strip() == "5.0"


@needs_fpm
def test_a_module_brought_by_fpm_and_by_the_fobos_collides(tmp_path, monkeypatch, capsys):
    kindsx = remote(tmp_path, "kindsx", KINDSX)
    vecs = remote(tmp_path, "vecs", vecs_package(kindsx), tags=("v0.3.0",))
    root = project(tmp_path, f"vecs = {vecs}\nkindsx = {kindsx}\n")
    monkeypatch.chdir(root)
    code, out = fobis("fetch", capsys=capsys)
    assert code == 1
    assert "module kindsx is defined by" in out and "vecs" in out


@needs_fpm
def test_pkg_install_builds_the_library_then_the_applications(tmp_path):
    kindsx = remote(tmp_path, "kindsx", KINDSX)
    vecs = remote(tmp_path, "vecs", vecs_package(kindsx), tags=("v0.3.0",))
    code, out = cli("pkg", "install", vecs, "--no-shims")
    assert code == 0, out
    prefix = next((tmp_path / "pkgs").glob("*/vecs/0.3.0"))
    assert (prefix / "lib" / "libvecs.a").is_file()
    assert os.listdir(prefix / "bin") == ["vecs_app"]  # the application, never the demo


@needs_fpm
def test_an_application_that_does_not_compile_leaves_the_library_installed(tmp_path):
    kindsx = remote(tmp_path, "kindsx", KINDSX)
    vecs = remote(tmp_path, "vecs", vecs_package(kindsx, app="call missing()"), tags=("v0.3.0",))
    code, out = cli("pkg", "install", vecs, "--no-shims")
    assert code == 0, out
    assert "warning: the applications of vecs were not installed" in out
    prefix = next((tmp_path / "pkgs").glob("*/vecs/0.3.0"))
    assert (prefix / "lib" / "libvecs.a").is_file() and not (prefix / "bin").exists()


def test_fpm_missing_is_an_error(tmp_path, monkeypatch):
    which = shutil.which
    monkeypatch.setattr(backends.shutil, "which", lambda name, *a, **k: None if name == "fpm" else which(name, *a, **k))
    src = tmp_path / "vecs"
    (src / "src").mkdir(parents=True)
    (src / "fpm.toml").write_text('name = "vecs"\n')
    with pytest.raises(backends.BackendError, match="fpm package and fpm is not on PATH"):
        backends.install_fpm(str(src), detect("gnu"), str(tmp_path / "prefix"))
