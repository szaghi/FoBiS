"""Tests for fobis.Externals — automatic external library detection (issue #169)."""

from __future__ import annotations

from unittest.mock import patch

from fobis.Externals import ExternalFlags, ExternalResolver, _pkg_config, _probe_mpi

# ── ExternalFlags.merge() and is_empty() ─────────────────────────────────────


def test_external_flags_is_empty_when_default():
    assert ExternalFlags().is_empty()


def test_external_flags_not_empty_with_cflags():
    assert not ExternalFlags(cflags="-I/usr/include/mpi").is_empty()


def test_external_flags_merge():
    a = ExternalFlags(cflags="-I/mpi/include", lflags="-lmpi", includes=["/mpi/include"], lib_dirs=["/mpi/lib"])
    b = ExternalFlags(cflags="-I/hdf5/include", lflags="-lhdf5", includes=["/hdf5/include"], lib_dirs=["/hdf5/lib"])
    merged = a.merge(b)
    assert "-I/mpi/include" in merged.cflags
    assert "-I/hdf5/include" in merged.cflags
    assert "-lmpi" in merged.lflags
    assert "-lhdf5" in merged.lflags


def test_external_flags_merge_deduplicates_includes():
    a = ExternalFlags(includes=["/common/include"])
    b = ExternalFlags(includes=["/common/include"])
    merged = a.merge(b)
    assert merged.includes.count("/common/include") == 1


# ── _probe_mpi() ─────────────────────────────────────────────────────────────


def test_probe_mpi_openmpi():
    """mpifort --showme:compile returns valid flags → ExternalFlags populated."""

    def which_side(cmd):
        return "/usr/bin/mpifort" if cmd == "mpifort" else None

    def sw_side(cmd):
        if "--showme:compile" in cmd:
            return (0, "-I/usr/include/mpi")
        if "--showme:link" in cmd:
            return (0, "-L/usr/lib/mpi -lmpi")
        return (1, "")

    with patch("shutil.which", side_effect=which_side), patch("fobis.Externals.syswork", side_effect=sw_side):
        result = _probe_mpi()

    assert result is not None
    assert "-I/usr/include/mpi" in result.cflags
    assert "-lmpi" in result.lflags
    assert "/usr/include/mpi" in result.includes


def test_probe_mpi_not_available():
    """No MPI wrapper found → None returned."""
    with patch("shutil.which", return_value=None):
        result = _probe_mpi()
    assert result is None


# ── _pkg_config() ─────────────────────────────────────────────────────────────


def test_probe_pkgconfig_success():
    """pkg-config succeeds → ExternalFlags with parsed flags."""

    def sw_side(cmd):
        if "--cflags" in cmd:
            return (0, "-I/opt/blas/include")
        if "--libs" in cmd:
            return (0, "-L/opt/blas/lib -lblas")
        return (1, "")

    with (
        patch("shutil.which", return_value="/usr/bin/pkg-config"),
        patch("fobis.Externals.syswork", side_effect=sw_side),
    ):
        result = _pkg_config("blas")

    assert result is not None
    assert "-I/opt/blas/include" in result.cflags
    assert "-lblas" in result.lflags


def test_probe_pkgconfig_failure_returns_none():
    """pkg-config returns non-zero → None."""
    with (
        patch("shutil.which", return_value="/usr/bin/pkg-config"),
        patch("fobis.Externals.syswork", return_value=(1, "not found")),
    ):
        result = _pkg_config("nonexistent_lib")
    assert result is None


def test_probe_pkgconfig_not_installed_returns_none():
    """No pkg-config binary → None."""
    with patch("shutil.which", return_value=None):
        result = _pkg_config("blas")
    assert result is None


# ── ExternalResolver.resolve() ────────────────────────────────────────────────


def test_resolve_all_merges_flags():
    """Two externals → merged ExternalFlags with combined flags."""
    resolver = ExternalResolver()
    mpi_flags = ExternalFlags(cflags="-I/mpi/include", lflags="-lmpi")
    hdf5_flags = ExternalFlags(cflags="-I/hdf5/include", lflags="-lhdf5")

    with patch.object(resolver, "resolve", side_effect=[mpi_flags, hdf5_flags]):
        result = resolver.resolve_all(["mpi", "hdf5"], {})

    assert "-I/mpi/include" in result.cflags
    assert "-I/hdf5/include" in result.cflags


def test_missing_external_warns_not_aborts():
    """Probe returns None → warning emitted, empty ExternalFlags returned."""
    warnings = []
    resolver = ExternalResolver(print_w=warnings.append)

    with patch.object(resolver, "resolve", return_value=None):
        result = resolver.resolve_all(["nonexistent"], {})

    assert any("nonexistent" in w or "warning" in w.lower() or "Warning" in w for w in warnings)
    assert result.is_empty()
