"""Tests for fobis.PkgConfig — automatic pkg-config file generation (issue #179)."""

from __future__ import annotations

import os
import tempfile

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
        gen.write(spec, lib_name="mylib", prefix="/usr/local",
                  lib_dir="lib", include_dir="include", output_path=output_path)
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
        gen.write(spec, lib_name="mylib", prefix="/usr",
                  lib_dir="lib", include_dir="include", output_path=output_path)
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
            f.write(
                "[project]\n"
                "name = myfortranlib\n"
                "version = 2.0.0\n\n"
                "[default]\n"
                "compiler = Gnu\n"
                "pkgconfig = false\n"
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
        assert spec is None
