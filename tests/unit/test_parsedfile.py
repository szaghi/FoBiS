"""Unit tests for fobis.ParsedFile — uses tmp_path, no compiler needed."""

import pytest

from fobis.ParsedFile import ParsedFile


def _write(tmp_path, filename, content):
    """Write *content* to *filename* inside *tmp_path* and return the path."""
    p = tmp_path / filename
    p.write_text(content, encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------------------
# Basic attribute initialisation
# ---------------------------------------------------------------------------


def test_init_basename(tmp_path):
    f = _write(tmp_path, "foo.f90", "")
    pf = ParsedFile(name=f)
    assert pf.basename == "foo"


def test_init_extension(tmp_path):
    f = _write(tmp_path, "bar.F90", "")
    pf = ParsedFile(name=f)
    assert pf.extension == ".F90"


def test_init_flags_default_false(tmp_path):
    f = _write(tmp_path, "x.f90", "")
    pf = ParsedFile(name=f)
    assert not pf.program
    assert not pf.module
    assert not pf.submodule
    assert not pf.include


# ---------------------------------------------------------------------------
# program detection
# ---------------------------------------------------------------------------


def test_parse_detects_program(tmp_path):
    src = "program main\n  implicit none\nend program main\n"
    f = _write(tmp_path, "main.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    assert pf.program


def test_parse_detects_program_uppercase(tmp_path):
    src = "PROGRAM MAIN\nEND PROGRAM MAIN\n"
    f = _write(tmp_path, "main.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    assert pf.program


def test_parse_detects_program_with_leading_spaces(tmp_path):
    src = "   program foo\nend program foo\n"
    f = _write(tmp_path, "foo.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    assert pf.program


# ---------------------------------------------------------------------------
# module detection
# ---------------------------------------------------------------------------


def test_parse_detects_module(tmp_path):
    src = "module mymod\nimplicit none\nend module mymod\n"
    f = _write(tmp_path, "mymod.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    assert pf.module
    assert "mymod" in pf.module_names


def test_parse_module_name_case_insensitive(tmp_path):
    src = "MODULE MyMod\nEND MODULE MyMod\n"
    f = _write(tmp_path, "mymod.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    assert pf.module
    assert "MyMod" in pf.module_names


def test_parse_multiple_modules(tmp_path):
    src = "module mod_a\nend module mod_a\nmodule mod_b\nend module mod_b\n"
    f = _write(tmp_path, "mods.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    assert "mod_a" in pf.module_names
    assert "mod_b" in pf.module_names


# ---------------------------------------------------------------------------
# use statement extraction
# ---------------------------------------------------------------------------


def test_parse_use_extracts_dependency(tmp_path):
    src = "module user\n  use other_mod\nend module user\n"
    f = _write(tmp_path, "user.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    dep_names = [d.name for d in pf.dependencies]
    assert "other_mod" in dep_names


def test_parse_use_with_colon_syntax(tmp_path):
    src = "module user\n  use, intrinsic :: iso_fortran_env\n  use mymod\nend module user\n"
    f = _write(tmp_path, "user.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    dep_names = [d.name for d in pf.dependencies]
    # iso_fortran_env is intrinsic — must be filtered out
    assert not any("iso_fortran_env" in n.lower() for n in dep_names)
    assert "mymod" in dep_names


def test_parse_use_with_double_colon(tmp_path):
    src = "program p\n  use :: some_module\nend program p\n"
    f = _write(tmp_path, "p.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    dep_names = [d.name for d in pf.dependencies]
    assert "some_module" in dep_names


def test_parse_use_only_extracts_module_name(tmp_path):
    src = "program p\n  use mymod, only: sub1, sub2\nend program p\n"
    f = _write(tmp_path, "p.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    dep_names = [d.name for d in pf.dependencies]
    assert "mymod" in dep_names


# ---------------------------------------------------------------------------
# Intrinsic module filtering
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "intrinsic",
    [
        "iso_fortran_env",
        "ISO_FORTRAN_ENV",
        "iso_c_binding",
        "IEEE_EXCEPTIONS",
        "ieee_arithmetic",
        "ieee_features",
    ],
)
def test_parse_filters_intrinsic_modules(tmp_path, intrinsic):
    src = f"module m\n  use {intrinsic}\nend module m\n"
    f = _write(tmp_path, "m.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    dep_names = [d.name.lower() for d in pf.dependencies]
    assert intrinsic.lower() not in dep_names


def test_parse_filters_mpi_module(tmp_path):
    src = "module m\n  use mpi\nend module m\n"
    f = _write(tmp_path, "m.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    dep_names = [d.name.lower() for d in pf.dependencies]
    assert "mpi" not in dep_names


def test_parse_filters_omp_lib(tmp_path):
    src = "module m\n  use omp_lib\nend module m\n"
    f = _write(tmp_path, "m.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    dep_names = [d.name.lower() for d in pf.dependencies]
    assert "omp_lib" not in dep_names


# ---------------------------------------------------------------------------
# submodule syntax
# ---------------------------------------------------------------------------


def test_parse_submodule_detected(tmp_path):
    src = "submodule (parent) child\nend submodule child\n"
    f = _write(tmp_path, "child.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    assert pf.submodule
    assert "child" in pf.submodule_names


def test_parse_submodule_adds_parent_dependency(tmp_path):
    src = "submodule (parent) child\nend submodule child\n"
    f = _write(tmp_path, "child.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    dep_names = [d.name for d in pf.dependencies]
    assert "parent" in dep_names


# ---------------------------------------------------------------------------
# include statement extraction
# ---------------------------------------------------------------------------


def test_parse_include_dependency(tmp_path):
    src = 'program p\n  include "my_include.h"\nend program p\n'
    f = _write(tmp_path, "p.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    dep_names = [d.name for d in pf.dependencies]
    assert "my_include.h" in dep_names


def test_parse_include_single_quotes(tmp_path):
    src = "program p\n  include 'defs.inc'\nend program p\n"
    f = _write(tmp_path, "p.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    dep_names = [d.name for d in pf.dependencies]
    assert "defs.inc" in dep_names


# ---------------------------------------------------------------------------
# nomodlib detection
# ---------------------------------------------------------------------------


def test_parse_nomodlib_for_plain_f90(tmp_path):
    """A .f90 file that contains no program/module/submodule → nomodlib."""
    src = "subroutine foo()\nend subroutine foo\n"
    f = _write(tmp_path, "util.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    assert pf.nomodlib


def test_parse_not_nomodlib_when_module_present(tmp_path):
    src = "module mymod\nend module mymod\n"
    f = _write(tmp_path, "mymod.f90", src)
    pf = ParsedFile(name=f)
    pf.parse()
    assert not pf.nomodlib
