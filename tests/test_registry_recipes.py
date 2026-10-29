"""CMake, make and recipe backends (#209 R6, R7): recipe validation, a CMake Fortran library and a make-only package
built with the consumer's compiler (a wrapper compiler records its calls: the compiler really passed), explicit recipe
steps, a recipe found in an index copied into the project by ``fobis add``, and a FoBiS project consuming a CMake
dependency through ``fetch`` + ``build`` (the R6 exit criterion)."""

from __future__ import annotations

import configparser
import json
import os
import shutil
import subprocess

import pytest

from fobis.fobis import run_fobis
from fobis.registry.recipe import RecipeError, parse_recipe
from fobis.UserConfig import UserConfig
from tests.registry_helpers import cli, isolate, remote

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or shutil.which("gfortran") is None, reason="git and gfortran"
)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    isolate(monkeypatch, tmp_path)


@pytest.fixture
def wrapper(tmp_path):
    """A Fortran compiler wrapper that records every call, then runs gfortran."""
    log = tmp_path / "fc-calls.log"
    fc = tmp_path / "bin" / "recording-fc"
    fc.parent.mkdir(parents=True, exist_ok=True)
    fc.write_text(f'#!/bin/sh\necho "$@" >> {log}\nexec gfortran "$@"\n')
    fc.chmod(0o755)
    return fc, log


VEC = (
    "module vec\nimplicit none\ncontains\npure real function dot2(a, b)\nreal, intent(in) :: a(2), b(2)\n"
    "dot2 = a(1)*b(1) + a(2)*b(2)\nend function dot2\nend module vec\n"
)
CMAKE_LIB = {
    "CMakeLists.txt": "cmake_minimum_required(VERSION 3.16)\nproject(vec Fortran)\nadd_library(vec STATIC src/vec.f90)\n"
    "install(TARGETS vec ARCHIVE DESTINATION lib)\n",
    "src/vec.f90": VEC,
}
MAKE_LIB = {
    "Makefile": "FC ?= gfortran\nall: libvec.a\nlibvec.a: vec.o\n\tar rcs $@ $^\nvec.o: vec.f90\n\t$(FC) $(FFLAGS) -c $<\n",
    "vec.f90": VEC,
}
CONSUMER = "program main\nuse vec\nprint '(F4.1)', dot2([1.0, 2.0], [3.0, 4.0])\nend program main\n"


def test_recipe_validation():
    assert parse_recipe('backend = "cmake"\ncmake-args = ["-DX=1"]\n').cmake_args == ["-DX=1"]
    with pytest.raises(RecipeError, match="backend must be one of"):
        parse_recipe('backend = "scons"\n')
    with pytest.raises(RecipeError, match="needs steps"):
        parse_recipe('backend = "recipe"\n')
    with pytest.raises(RecipeError, match="unknown placeholder"):
        parse_recipe('backend = "recipe"\nsteps = ["make {compiler}"]\n')
    with pytest.raises(RecipeError, match="unknown key"):
        parse_recipe('backend = "cmake"\nflags = ["-O2"]\n')


@pytest.mark.skipif(shutil.which("cmake") is None, reason="cmake")
def test_cmake_library_built_with_the_consumers_compiler(tmp_path, wrapper):
    fc, log = wrapper
    url = remote(tmp_path, "vec", CMAKE_LIB, tags=("v0.1.0",))
    code, out = cli("pkg", "install", url, "--fc", str(fc), "--json")
    assert code == 0, out
    receipt = json.loads(out)
    assert receipt["backend"] == "cmake" and receipt["modules"] == ["vec"]
    assert "vec.f90" in log.read_text()  # CMake compiled with the wrapper, not with its own choice
    prefix = receipt["prefix"]
    assert os.path.isfile(os.path.join(prefix, "lib", "libvec.a"))
    assert os.path.isfile(os.path.join(prefix, "include", "vec.mod"))  # harvested: CMake installs no module file
    main = tmp_path / "main.f90"
    main.write_text(CONSUMER)
    subprocess.run(
        ["gfortran", str(main), f"-I{prefix}/include", f"{prefix}/lib/libvec.a", "-o", str(tmp_path / "m")], check=True
    )
    assert subprocess.run([str(tmp_path / "m")], capture_output=True, text=True).stdout.strip() == "11.0"


def test_make_only_package_without_install_rule(tmp_path, wrapper):
    """The R7 exit criterion: a make-only package built by autodetection (no install rule: harvested)."""
    fc, log = wrapper
    url = remote(tmp_path, "vecmake", MAKE_LIB, tags=("v1.0.0",))
    code, out = cli("pkg", "install", url, "--fc", str(fc), "--json")
    assert code == 0, out
    receipt = json.loads(out)
    assert receipt["backend"] == "make" and receipt["modules"] == ["vec"] and "vec.f90" in log.read_text()
    assert os.path.isfile(os.path.join(receipt["prefix"], "lib", "libvec.a"))


def test_recipe_steps_shipped_in_the_repository(tmp_path):
    files = {
        "vec.f90": VEC,
        "fortran-recipe.toml": 'backend = "recipe"\nsteps = [\n  "mkdir -p {prefix}/lib {prefix}/include",\n'
        '  "{fc} {fflags} -c vec.f90 -J{prefix}/include -o {build}/vec.o",\n'
        '  "ar rcs {prefix}/lib/libvec.a {build}/vec.o",\n]\n',
    }
    url = remote(tmp_path, "vecsteps", files)
    code, out = cli("pkg", "install", url, "--cflags", "-O1", "--json")
    assert code == 0, out
    receipt = json.loads(out)
    assert receipt["backend"] == "recipe" and receipt["modules"] == ["vec"] and receipt["toolchain"]["cflags"] == "-O1"


def test_add_copies_the_index_recipe_into_the_project(tmp_path, monkeypatch):
    url = remote(tmp_path, "vecmake", MAKE_LIB, tags=("v1.0.0",))
    index = tmp_path / "idx"
    (index / "recipes").mkdir(parents=True)
    (index / "recipes" / "vecmake.toml").write_text('backend = "make"\nmake-args = ["all"]\n')
    (index / "index.toml").write_text(
        f'name = "lab"\n[package.vecmake]\nsource = "{url}"\nrecipe = "recipes/vecmake.toml"\nprovides = ["vec"]\n'
    )
    UserConfig().set_indexes([("lab", str(index))])
    project = tmp_path / "proj"
    project.mkdir()
    (project / "fobos").write_text("[modes]\nmodes = gnu\n\n[gnu]\ncompiler = gnu\n")
    monkeypatch.chdir(project)
    code, out = cli("add", "vecmake")
    assert code == 0, out
    assert (project / "recipes" / "vecmake.toml").read_text() == 'backend = "make"\nmake-args = ["all"]\n'
    config = configparser.RawConfigParser()
    config.read(project / "fobos")
    assert config.get("dependencies", "vecmake").endswith(":: recipe=recipes/vecmake.toml")
    code, out = cli("info", "vecmake")
    assert "recipe    : recipes/vecmake.toml (make)" in out


@pytest.mark.skipif(shutil.which("cmake") is None, reason="cmake")
def test_fobis_project_consumes_a_cmake_dependency(tmp_path, monkeypatch, capsys, wrapper):
    """The R6 exit criterion: fetch builds the CMake library with the project's compiler, build links it."""
    fc, log = wrapper
    url = remote(tmp_path, "vec", CMAKE_LIB, tags=("v0.1.0",))
    project = tmp_path / "proj"
    (project / "src").mkdir(parents=True)
    (project / "src" / "main.f90").write_text(CONSUMER)
    (project / "fobos").write_text(
        f"[modes]\nmodes = gnu\n\n[gnu]\ncompiler = gnu\nfc = {fc}\nsrc = ./src/\nbuild_dir = ./build/\n"
        f"target = src/main.f90\n\n[dependencies]\nvec = {url}\n"
    )
    monkeypatch.chdir(project)
    for args in (["fetch"], ["build"]):
        try:
            run_fobis(fake_args=args)
        except SystemExit as exc:
            assert not exc.code, capsys.readouterr().out
    assert "vec.f90" in log.read_text()
    assert (project / ".fobis_deps" / ".prefix" / "vec" / "lib" / "libvec.a").is_file()
    run = subprocess.run([str(project / "build" / "main")], capture_output=True, text=True)
    assert run.stdout.strip() == "11.0"


def test_layout_in_a_subdirectory_and_a_broken_pc(tmp_path):
    """Found on json-fortran 9.3.1: CMake installs into <prefix>/jsonfortran-gnu-9.3.1/lib with a .pc whose libdir
    and includedir are empty; FoBiS finds the library and modules there and writes a working .pc."""
    from fobis.registry.backends import collect, pc_is_valid

    lib = tmp_path / "prefix" / "pkg-gnu-1.0" / "lib"
    (lib / "pkgconfig").mkdir(parents=True)
    (lib / "libvec.a").write_text("!<arch>\n")
    (lib / "vec.mod").write_text("x")
    broken = lib / "pkgconfig" / "vec-pkg.pc"
    broken.write_text("libdir=\nincludedir=\n\nName: vec\nLibs: -L${libdir} -lvec\nCflags: -I${includedir}\n")
    assert not pc_is_valid(str(broken))
    artifacts = collect(str(tmp_path / "prefix"), "vec", "1.0")
    assert artifacts.libraries == [str(lib / "libvec.a")] and artifacts.modules == ["vec"]
    ours = tmp_path / "prefix" / "lib" / "pkgconfig" / "vec.pc"
    assert artifacts.pc_files == [str(ours)] and pc_is_valid(str(ours))
    assert "libdir=${prefix}/pkg-gnu-1.0/lib" in ours.read_text()
