"""Tests for fobis.PkgConfig — automatic pkg-config file generation (issue #179)."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

import pytest

from fobis.PkgConfig import PkgConfigGenerator, PkgConfigSpec

# ── PkgConfigGenerator.generate() ───────────────────────────────────────────


def test_generate_minimal():
    gen = PkgConfigGenerator()
    spec = PkgConfigSpec(name="mylib", version="1.0.0", description="A test library")
    output = gen.generate(spec, lib_name="mylib", prefix="/usr/local")
    assert "Name: mylib" in output
    assert "Version: 1.0.0" in output
    assert "Description: A test library" in output
    assert "Libs:" in output
    assert "Cflags:" in output


def test_generate_with_requires():
    gen = PkgConfigGenerator()
    spec = PkgConfigSpec(
        name="mylib",
        version="1.0.0",
        description="A library",
        requires="blas >= 3.8",
    )
    output = gen.generate(spec, lib_name="mylib", prefix="/usr/local")
    assert "Requires: blas >= 3.8" in output


def test_generate_no_url_omits_url_line():
    gen = PkgConfigGenerator()
    spec = PkgConfigSpec(name="mylib", version="1.0.0", description="A library", url="")
    output = gen.generate(spec, lib_name="mylib", prefix="/usr/local")
    assert "URL:" not in output


def test_generate_with_url():
    gen = PkgConfigGenerator()
    spec = PkgConfigSpec(
        name="mylib",
        version="1.0.0",
        description="A library",
        url="https://github.com/user/mylib",
    )
    output = gen.generate(spec, lib_name="mylib", prefix="/usr/local")
    assert "URL: https://github.com/user/mylib" in output


def test_generate_uses_prefix_variables():
    gen = PkgConfigGenerator()
    spec = PkgConfigSpec(name="mylib", version="1.0.0", description="")
    output = gen.generate(spec, lib_name="mylib", prefix="/usr/local")
    # libdir and includedir must use ${prefix}, not an absolute path
    assert "${prefix}" in output
    assert "libdir=${prefix}/lib" in output
    assert "includedir=${prefix}/include" in output


def test_generate_version_strips_v_prefix():
    gen = PkgConfigGenerator()
    spec = PkgConfigSpec(name="mylib", version="v2.1.0", description="")
    output = gen.generate(spec, lib_name="mylib", prefix="/usr")
    assert "Version: 2.1.0" in output
    assert "Version: v2.1.0" not in output


def test_generate_strips_lib_prefix_from_lib_name():
    gen = PkgConfigGenerator()
    spec = PkgConfigSpec(name="mylib", version="1.0.0", description="")
    output = gen.generate(spec, lib_name="libmylib", prefix="/usr")
    # Should use -lmylib, not -llibmylib
    assert "-lmylib" in output


def test_generate_requires_private():
    gen = PkgConfigGenerator()
    spec = PkgConfigSpec(
        name="mylib",
        version="1.0.0",
        description="",
        requires_priv="hdf5 >= 1.10",
    )
    output = gen.generate(spec, lib_name="mylib", prefix="/usr")
    assert "Requires.private: hdf5 >= 1.10" in output


# ── PkgConfigGenerator.write() ───────────────────────────────────────────────


def test_write_creates_file():
    gen = PkgConfigGenerator()
    spec = PkgConfigSpec(name="mylib", version="1.0.0", description="A test lib")
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "pkgconfig", "mylib.pc")
        gen.write(
            spec, lib_name="mylib", prefix="/usr/local", lib_dir="lib", include_dir="include", output_path=output_path
        )
        assert os.path.isfile(output_path)
        with open(output_path) as fh:
            content = fh.read()
        assert "Name: mylib" in content
        assert "Version: 1.0.0" in content


def test_write_creates_parent_dirs():
    gen = PkgConfigGenerator()
    spec = PkgConfigSpec(name="mylib", version="1.0.0", description="")
    with tempfile.TemporaryDirectory() as tmpdir:
        # Nested directory that doesn't exist yet
        output_path = os.path.join(tmpdir, "a", "b", "c", "mylib.pc")
        gen.write(spec, lib_name="mylib", prefix="/usr", lib_dir="lib", include_dir="include", output_path=output_path)
        assert os.path.isfile(output_path)


# ── Fobos.get_pkgconfig_spec() integration ──────────────────────────────────


def test_get_pkgconfig_spec_from_fobos():
    with tempfile.TemporaryDirectory() as root:
        fobos_path = os.path.join(root, "fobos")
        with open(fobos_path, "w") as f:
            f.write(
                "[project]\n"
                "name = myfortranlib\n"
                "version = 2.0.0\n"
                "authors = Stefano Zaghi\n\n"
                "[default]\n"
                "compiler = Gnu\n"
                "pkgconfig = true\n"
                "build_dir = ./\n"
            )
        import argparse

        from fobis.Fobos import Fobos

        cliargs = argparse.Namespace(
            fobos=fobos_path,
            fobos_case_insensitive=False,
            mode=None,
            which="build",
        )
        fobos = Fobos(cliargs=cliargs)
        spec = fobos.get_pkgconfig_spec()
        assert spec is not None
        assert spec.name == "myfortranlib"


def test_get_pkgconfig_spec_none_when_disabled():
    with tempfile.TemporaryDirectory() as root:
        fobos_path = os.path.join(root, "fobos")
        with open(fobos_path, "w") as f:
            f.write("[project]\nname = myfortranlib\nversion = 2.0.0\n\n[default]\ncompiler = Gnu\npkgconfig = false\n")
        import argparse

        from fobis.Fobos import Fobos

        cliargs = argparse.Namespace(
            fobos=fobos_path,
            fobos_case_insensitive=False,
            mode=None,
            which="build",
        )
        fobos = Fobos(cliargs=cliargs)
        spec = fobos.get_pkgconfig_spec()
        assert spec is None


# ── the .pc files of a real build and install ────────────────────────────────

GREET = "module greet\ncontains\nsubroutine hello()\nprint '(A)', 'hello'\nend subroutine hello\nend module greet\n"
USER = "program user\nuse greet, only : hello\ncall hello\nend program user\n"


def _pkg_config(pc_dir, name) -> list[str]:
    env = {**os.environ, "PKG_CONFIG_PATH": str(pc_dir)}
    run = subprocess.run(["pkg-config", "--cflags", "--libs", name], capture_output=True, text=True, env=env)
    assert run.returncode == 0, run.stderr
    return run.stdout.split()


def _link_and_run(root, flags) -> str:
    """Compile and link a program using the library through the pkg-config flags alone, run it."""
    (root / "user.f90").write_text(USER)
    subprocess.run(["gfortran", "user.f90", *flags, "-o", "user"], cwd=root, check=True)
    return subprocess.run([str(root / "user")], capture_output=True, text=True, check=True).stdout.strip()


@pytest.mark.skipif(shutil.which("gfortran") is None or shutil.which("pkg-config") is None, reason="tools")
def test_build_and_install_write_pc_files(tmp_path, monkeypatch):
    """The pkgconfig keys wrote nothing: the generator was never called."""
    from fobis.fobis import run_fobis

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "greet.f90").write_text(GREET)
    (tmp_path / "fobos").write_text(
        "[project]\nname = greet\nversion = v1.2.3\nsummary = Greetings\n\n"
        "[default]\ncompiler = gnu\ncflags = -c\nsrc = ./src/\nbuild_dir = ./build/\nmod_dir = ./mod/\n"
        "target = src/greet.f90\nmklib = static\ntrack_build = True\npkgconfig = True\npkgconfig_req_priv = zlib\n"
    )
    monkeypatch.chdir(tmp_path)
    run_fobis(fake_args=["build", "--quiet"])
    pc = (tmp_path / "build" / "greet.pc").read_text()
    assert "Version: 1.2.3" in pc and "Description: Greetings" in pc and "Requires.private: zlib" in pc
    flags = _pkg_config(tmp_path / "build", "greet")
    # no output key: the library is build/greet.a, which -l cannot find: linked by its path
    assert flags == [f"-I{tmp_path / 'build' / 'mod'}", str(tmp_path / "build" / "greet.a")]
    assert _link_and_run(tmp_path, flags) == "hello"

    prefix = tmp_path / "prefix"
    run_fobis(fake_args=["install", "--prefix", str(prefix)])
    assert (prefix / "lib" / "greet.a").is_file()  # no output key: named after the file, the track records the .a
    flags = _pkg_config(prefix / "lib" / "pkgconfig", "greet")
    assert flags == [f"-I{prefix / 'include'}", str(prefix / "lib" / "greet.a")]
    assert _link_and_run(tmp_path, flags) == "hello"


@pytest.mark.skipif(shutil.which("gfortran") is None or shutil.which("pkg-config") is None, reason="tools")
def test_a_lib_named_library_is_linked_with_l(tmp_path, monkeypatch):
    from fobis.fobis import run_fobis

    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "greet.f90").write_text(GREET)
    (tmp_path / "fobos").write_text(
        "[default]\ncompiler = gnu\ncflags = -c\nsrc = ./src/\nbuild_dir = ./build/\ntarget = src/greet.f90\n"
        "mklib = static\noutput = libgreet.a\npkgconfig = True\n"
    )
    monkeypatch.chdir(tmp_path)
    run_fobis(fake_args=["build", "--quiet"])  # no [project] name: the .pc is named after the library
    flags = _pkg_config(tmp_path / "build", "greet")
    assert flags[1:] == [f"-L{tmp_path / 'build'}", "-lgreet"]
    assert _link_and_run(tmp_path, flags) == "hello"
