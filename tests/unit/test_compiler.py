"""Unit tests for fobis.Compiler — pure Python, no subprocess."""

import argparse

import pytest

from fobis.Compiler import Compiler


def _ns(**kwargs) -> argparse.Namespace:
    """Build a minimal cliargs namespace for Compiler construction."""
    defaults = dict(
        compiler="gnu",
        fc=None,
        cflags=None,
        lflags=None,
        preproc=None,
        modsw=None,
        mpi=False,
        openmp=False,
        openmp_offload=False,
        coarray=False,
        coverage=False,
        profile=False,
        mklib=None,
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# ---------------------------------------------------------------------------
# Default flag assembly per compiler
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "vendor,expected_fcs",
    [
        ("gnu", "gfortran"),
        ("intel", "ifort"),
        ("intel_nextgen", "ifx"),
        ("g95", "g95"),
        ("opencoarrays-gnu", "caf"),
        ("pgi", "pgfortran"),
        ("ibm", "xlf2008_r"),
        ("nag", "nagfor"),
        ("nvfortran", "nvfortran"),
        ("amd", "amdflang"),
    ],
)
def test_default_fcs(vendor, expected_fcs):
    c = Compiler(_ns(compiler=vendor))
    assert c.fcs == expected_fcs


@pytest.mark.parametrize(
    "vendor,expected_modsw",
    [
        ("gnu", "-J "),
        ("intel", "-module "),
        ("intel_nextgen", "-module "),
        ("g95", "-fmod="),
        ("pgi", "-module "),
        ("ibm", "-qmoddir="),
        ("nag", "-mdir "),
        ("nvfortran", "-module "),
        ("amd", "-module-dir "),
    ],
)
def test_default_modsw(vendor, expected_modsw):
    c = Compiler(_ns(compiler=vendor))
    assert c.modsw == expected_modsw


def test_custom_compiler_empty_fcs():
    """Custom compiler initialises with empty strings."""
    c = Compiler(_ns(compiler="custom"))
    assert c.fcs == ""
    assert c.cflags == ""
    assert c.modsw == ""


def test_unknown_compiler_falls_back_to_gnu():
    """An unrecognised compiler name falls back to gnu defaults."""
    c = Compiler(_ns(compiler="unknown_xyz"))
    assert c.fcs == "gfortran"


# ---------------------------------------------------------------------------
# CLI override of defaults
# ---------------------------------------------------------------------------


def test_fc_override():
    c = Compiler(_ns(compiler="gnu", fc="my_fortran"))
    assert c.fcs == "my_fortran"


def test_cflags_override():
    c = Compiler(_ns(compiler="gnu", cflags="-O2"))
    assert "-O2" in c.cflags


def test_lflags_override():
    c = Compiler(_ns(compiler="gnu", lflags="-lm"))
    assert "-lm" in c.lflags


def test_modsw_override():
    c = Compiler(_ns(compiler="gnu", modsw="-I "))
    assert c.modsw == "-I "


def test_modsw_strips_quotes():
    c = Compiler(_ns(compiler="gnu", modsw="'-J '"))
    assert "'" not in c.modsw


# ---------------------------------------------------------------------------
# Feature flags — MPI
# ---------------------------------------------------------------------------


def test_mpi_gnu_switches_fcs():
    c = Compiler(_ns(compiler="gnu", mpi=True))
    assert c.fcs == "mpif90"


def test_mpi_intel_switches_fcs():
    c = Compiler(_ns(compiler="intel", mpi=True))
    assert c.fcs == "mpiifort"


def test_mpi_intel_nextgen_switches_fcs():
    c = Compiler(_ns(compiler="intel_nextgen", mpi=True))
    assert c.fcs == "mpiifort -fc=ifx"


# ---------------------------------------------------------------------------
# Feature flags — OpenMP
# ---------------------------------------------------------------------------


def test_openmp_gnu_cflags():
    c = Compiler(_ns(compiler="gnu", openmp=True))
    assert "-fopenmp" in c.cflags


def test_openmp_gnu_lflags():
    c = Compiler(_ns(compiler="gnu", openmp=True))
    assert "-fopenmp" in c.lflags


def test_openmp_intel_cflags():
    c = Compiler(_ns(compiler="intel", openmp=True))
    assert "-qopenmp" in c.cflags


# ---------------------------------------------------------------------------
# Feature flags — coarray
# ---------------------------------------------------------------------------


def test_coarray_gnu_cflags():
    c = Compiler(_ns(compiler="gnu", coarray=True))
    assert "-fcoarray=lib" in c.cflags


def test_coarray_gnu_lflags():
    c = Compiler(_ns(compiler="gnu", coarray=True))
    assert "-lcaf_mpi" in c.lflags


# ---------------------------------------------------------------------------
# Feature flags — coverage
# ---------------------------------------------------------------------------


def test_coverage_gnu_cflags():
    c = Compiler(_ns(compiler="gnu", coverage=True))
    assert "-ftest-coverage" in c.cflags
    assert "-fprofile-arcs" in c.cflags


def test_coverage_gnu_lflags():
    c = Compiler(_ns(compiler="gnu", coverage=True))
    assert "-fprofile-arcs" in c.lflags


# ---------------------------------------------------------------------------
# mklib — shared library flag
# ---------------------------------------------------------------------------


def test_mklib_shared_adds_flag():
    c = Compiler(_ns(compiler="gnu", mklib="shared"))
    assert "-shared" in c.lflags


def test_mklib_static_no_shared_flag():
    c = Compiler(_ns(compiler="gnu", mklib="static"))
    assert "-shared" not in c.lflags


# ---------------------------------------------------------------------------
# compile_cmd / link_cmd
# ---------------------------------------------------------------------------


def test_compile_cmd_contains_modsw():
    c = Compiler(_ns(compiler="gnu"))
    cmd = c.compile_cmd("./mod/")
    assert "-J ./mod/" in cmd


def test_compile_cmd_contains_include():
    c = Compiler(_ns(compiler="gnu"))
    cmd = c.compile_cmd("./mod/")
    assert "-I./mod/" in cmd


def test_link_cmd_contains_fcs():
    c = Compiler(_ns(compiler="gnu"))
    cmd = c.link_cmd("./mod/")
    assert "gfortran" in cmd


# ---------------------------------------------------------------------------
# pprint / __str__
# ---------------------------------------------------------------------------


def test_pprint_contains_vendor():
    c = Compiler(_ns(compiler="gnu"))
    s = str(c)
    assert "gnu" in s


def test_pprint_contains_compiler_cmd():
    c = Compiler(_ns(compiler="intel"))
    s = str(c)
    assert "ifort" in s
