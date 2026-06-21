"""Tests for first-class LFortran compiler support.

Pure-Python checks on the LFortran default flags. These do not invoke the
``lfortran`` executable, so they run anywhere (CI installs only gfortran).
"""

import argparse

from fobis.cli._constants import __compiler_supported__
from fobis.Compiler import Compiler
from fobis.Profiles import KNOWN_COMPILERS, get_profile_flags


def _compiler(**overrides):
    """Build a Compiler with a minimal cliargs Namespace.

    All override channels (fc/cflags/lflags/preproc/modsw) default to falsy so
    the compiler's built-in defaults are exercised unless a test overrides them.
    """
    cliargs = argparse.Namespace(
        compiler="lfortran",
        fc=None,
        cflags=None,
        lflags=None,
        preproc=None,
        modsw=None,
        mklib=None,
        mpi=False,
        openmp=False,
        openmp_offload=False,
        coarray=False,
        coverage=False,
        profile=False,
    )
    for key, value in overrides.items():
        setattr(cliargs, key, value)
    return Compiler(cliargs=cliargs)


def test_lfortran_is_supported():
    """LFortran is a first-class compiler, exposed for help and completion."""
    assert "lfortran" in Compiler.supported
    assert "lfortran" in __compiler_supported__


def test_lfortran_defaults():
    """Default flags: bare -c (no imposed --cpp), -J module switch."""
    compiler = _compiler()
    assert compiler.compiler == "lfortran"
    assert compiler.fcs == "lfortran"
    assert compiler.cflags == "-c"
    assert compiler.modsw.strip() == "-J"
    # --cpp is never imposed: a bare -c must not pull in preprocessing.
    assert "--cpp" not in compiler.cflags


def test_lfortran_mpi_wrapper():
    """With mpi=True the compiler statement becomes the mpif90 wrapper."""
    compiler = _compiler(mpi=True)
    assert compiler.fcs == "mpif90"


def test_lfortran_openmp_flag():
    """OpenMP is enabled via --openmp on both compile and link phases."""
    compiler = _compiler(openmp=True)
    assert "--openmp" in compiler.cflags
    assert "--openmp" in compiler.lflags


def test_lfortran_profiles():
    """Debug/release profiles are defined with LFortran-valid flags."""
    assert "lfortran" in KNOWN_COMPILERS
    debug = get_profile_flags("lfortran", "debug")
    release = get_profile_flags("lfortran", "release")
    assert debug["cflags"] == "-O0 -g"
    assert release["cflags"] == "-O3"
