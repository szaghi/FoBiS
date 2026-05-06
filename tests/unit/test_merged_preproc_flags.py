"""Unit tests for fobis.fobis._merged_preproc_flags."""

from __future__ import annotations

import argparse

from fobis.fobis import _merged_preproc_flags


def _ns(**kwargs) -> argparse.Namespace:
    """Minimal cliargs stub with the two attributes the helper consults."""
    base = {"preproc": "", "cflags": ""}
    base.update(kwargs)
    return argparse.Namespace(**base)


def test_returns_empty_when_both_empty():
    assert _merged_preproc_flags(_ns()) == ""


def test_returns_preproc_unchanged_when_no_D_in_cflags():
    out = _merged_preproc_flags(_ns(preproc="-D_FNL -DDEV_OAC", cflags="-O2 -fast"))
    assert out == "-D_FNL -DDEV_OAC"


def test_extracts_D_from_cflags_when_preproc_empty():
    out = _merged_preproc_flags(_ns(preproc="", cflags="-c -O3 -DUSE_MPI -DDEBUG"))
    assert "-DUSE_MPI" in out
    assert "-DDEBUG" in out
    # Non-D tokens must NOT bleed through.
    assert "-O3" not in out
    assert "-c" not in out


def test_merges_preproc_and_D_from_cflags():
    out = _merged_preproc_flags(
        _ns(preproc="-D_FNL", cflags="-cpp -c -DUSE_MPI -O3"),
    )
    tokens = out.split()
    assert "-D_FNL" in tokens
    assert "-DUSE_MPI" in tokens
    # Non-D tokens from cflags are filtered out.
    assert "-cpp" not in tokens
    assert "-O3" not in tokens


def test_extracts_U_undefine_from_cflags():
    """-U (undefine) is also a cpp-meaningful flag and must be propagated."""
    out = _merged_preproc_flags(_ns(preproc="", cflags="-c -UDEBUG"))
    assert "-UDEBUG" in out


def test_handles_none_preproc_gracefully():
    """cliargs.preproc defaults to None in some entry points."""
    out = _merged_preproc_flags(_ns(preproc=None, cflags="-DFOO"))
    assert out == "-DFOO"


def test_handles_missing_attributes():
    """getattr fallbacks: a stripped namespace returns ''."""
    ns = argparse.Namespace()
    assert _merged_preproc_flags(ns) == ""
