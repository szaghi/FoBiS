"""Tests for fobis feature flags — conditional compilation (issue #168)."""

from __future__ import annotations

import argparse
import os
import tempfile

from fobis.Fobos import Fobos


def _make_fobos(
    root: str,
    fobos_content: str,
    extra_cliargs: dict | None = None,
) -> tuple[Fobos, argparse.Namespace]:
    """Write a fobos file and return a Fobos instance + cliargs.

    Note: ``features`` and ``no_default_features`` must NOT appear in the fobos
    mode section — they are CLI-only. When the fobos sets them, it overwrites
    the CLI values before ``_apply_features`` runs. Only put them in
    ``extra_cliargs`` to simulate CLI input.
    """
    path = os.path.join(root, "fobos")
    with open(path, "w") as f:
        f.write(fobos_content)
    cliargs = argparse.Namespace(
        fobos=path,
        fobos_case_insensitive=False,
        mode=None,
        which="build",
        cflags="-c",
        lflags="",
        features="",
        no_default_features=False,
        build_profile=None,
        # compiler capability attrs — implicit features flip these
        openmp=False,
        openmp_offload=False,
        mpi=False,
        coarray=False,
        coverage=False,
        profile=False,
    )
    if extra_cliargs:
        for k, v in extra_cliargs.items():
            setattr(cliargs, k, v)
    fobos = Fobos(cliargs=cliargs)
    return fobos, cliargs


# ── default features ─────────────────────────────────────────────────────────


def test_features_default_activated():
    """fobos default = mpi → -DUSE_MPI appears in cflags without --features."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "default = mpi\n"
            "mpi     = -DUSE_MPI\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content)
        assert "-DUSE_MPI" in cliargs.cflags


def test_features_no_default():
    """--no-default-features: default features must NOT appear in cflags."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "default = mpi\n"
            "mpi     = -DUSE_MPI\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"no_default_features": True})
        assert "-DUSE_MPI" not in cliargs.cflags


def test_features_explicit():
    """--features hdf5 must add -DUSE_HDF5 even when not in default."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "hdf5 = -DUSE_HDF5\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "hdf5"})
        assert "-DUSE_HDF5" in cliargs.cflags


def test_features_multiple():
    """--features mpi,hdf5 must add both defines."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "mpi  = -DUSE_MPI\n"
            "hdf5 = -DUSE_HDF5\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "mpi,hdf5"})
        assert "-DUSE_MPI" in cliargs.cflags
        assert "-DUSE_HDF5" in cliargs.cflags


def test_features_no_default_plus_explicit():
    """--no-default-features --features hdf5: only hdf5 flag present."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "default = mpi\n"
            "mpi  = -DUSE_MPI\n"
            "hdf5 = -DUSE_HDF5\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(
            root, content, {"features": "hdf5", "no_default_features": True}
        )
        assert "-DUSE_HDF5" in cliargs.cflags
        assert "-DUSE_MPI" not in cliargs.cflags


def test_features_unknown_warns():
    """Unknown feature name → warning emitted, no abort."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "mpi = -DUSE_MPI\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        warnings = []
        path = os.path.join(root, "fobos")
        with open(path, "w") as f:
            f.write(content)
        cliargs = argparse.Namespace(
            fobos=path,
            fobos_case_insensitive=False,
            mode=None,
            which="build",
            cflags="-c",
            lflags="",
            features="nonexistent",
            no_default_features=False,
            build_profile=None,
        )
        Fobos(cliargs=cliargs, print_w=warnings.append)
        assert any("nonexistent" in w for w in warnings)


def test_features_no_section_warns_with_unknown_flag():
    """fobos without [features] + --features foo (non-implicit) → warning, no crash."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        warnings = []
        path = os.path.join(root, "fobos")
        with open(path, "w") as f:
            f.write(content)
        cliargs = argparse.Namespace(
            fobos=path,
            fobos_case_insensitive=False,
            mode=None,
            which="build",
            cflags="-c",
            lflags="",
            features="foo",
            no_default_features=False,
            build_profile=None,
        )
        Fobos(cliargs=cliargs, print_w=warnings.append)
        assert any("foo" in w for w in warnings)


def test_features_gnu_openmp_routes_to_both():
    """-fopenmp must appear in both cflags (compile) and lflags (link)."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "omp = -DUSE_OMP -fopenmp\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "omp"})
        assert "-DUSE_OMP" in cliargs.cflags
        assert "-fopenmp" in cliargs.cflags
        assert "-fopenmp" in cliargs.lflags


def test_features_intel_openmp_routes_to_both():
    """-qopenmp (Intel) must appear in both cflags and lflags."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "omp = -DUSE_OMP -qopenmp\n\n"
            "[default]\n"
            "compiler = Intel\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "omp"})
        assert "-DUSE_OMP" in cliargs.cflags
        assert "-qopenmp" in cliargs.cflags
        assert "-qopenmp" in cliargs.lflags


def test_features_nvfortran_openmp_routes_to_both():
    """-mp (nvfortran/pgi) must appear in both cflags and lflags."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "omp = -DUSE_OMP -mp\n\n"
            "[default]\n"
            "compiler = NVFortran\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "omp"})
        assert "-DUSE_OMP" in cliargs.cflags
        assert "-mp" in cliargs.cflags
        assert "-mp" in cliargs.lflags


def test_features_linker_only_flags():
    """-L and -l flags must go only to lflags, not cflags."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "hdf5 = -DUSE_HDF5 -I/opt/hdf5/include -L/opt/hdf5/lib -lhdf5\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "hdf5"})
        assert "-L/opt/hdf5/lib" not in cliargs.cflags
        assert "-lhdf5" not in cliargs.cflags
        assert "-L/opt/hdf5/lib" in cliargs.lflags
        assert "-lhdf5" in cliargs.lflags
        assert "-DUSE_HDF5" in cliargs.cflags
        assert "-I/opt/hdf5/include" in cliargs.cflags


def test_no_features_no_extra_flags():
    """fobos mode with no feature flags → cflags unchanged."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content)
        assert cliargs.cflags.strip() == "-c"


# ── get_features() / get_default_features() ─────────────────────────────────


def test_get_features_returns_dict():
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "mpi  = -DUSE_MPI\n"
            "hdf5 = -DUSE_HDF5\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags = -c\n"
            "lflags =\n"
            "build_profile =\n"
        )
        path = os.path.join(root, "fobos")
        with open(path, "w") as f:
            f.write(content)
        cliargs = argparse.Namespace(
            fobos=path,
            fobos_case_insensitive=False,
            mode=None,
            which="build",
            cflags="-c",
            lflags="",
            features="",
            no_default_features=False,
            build_profile=None,
        )
        fobos = Fobos(cliargs=cliargs)
        features = fobos.get_features()
        assert "mpi" in features
        assert "hdf5" in features


def test_get_default_features_returns_list():
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "default = mpi hdf5\n"
            "mpi  = -DUSE_MPI\n"
            "hdf5 = -DUSE_HDF5\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags = -c\n"
            "lflags =\n"
            "build_profile =\n"
        )
        path = os.path.join(root, "fobos")
        with open(path, "w") as f:
            f.write(content)
        cliargs = argparse.Namespace(
            fobos=path,
            fobos_case_insensitive=False,
            mode=None,
            which="build",
            cflags="-c",
            lflags="",
            features="",
            no_default_features=False,
            build_profile=None,
        )
        fobos = Fobos(cliargs=cliargs)
        defaults = fobos.get_default_features()
        assert "mpi" in defaults
        assert "hdf5" in defaults


# ── implicit (well-known) features ──────────────────────────────────────────


def test_implicit_openmp_sets_cliarg():
    """--features openmp with no [features] section sets cliargs.openmp = True."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "openmp"})
        assert cliargs.openmp is True


def test_implicit_omp_alias_sets_cliarg():
    """Short alias 'omp' is equivalent to 'openmp'."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "omp"})
        assert cliargs.openmp is True


def test_implicit_mpi_sets_cliarg():
    """--features mpi sets cliargs.mpi = True."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "mpi"})
        assert cliargs.mpi is True


def test_implicit_coarray_sets_cliarg():
    """--features coarray sets cliargs.coarray = True."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "coarray"})
        assert cliargs.coarray is True


def test_implicit_coverage_sets_cliarg():
    """--features coverage sets cliargs.coverage = True."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "coverage"})
        assert cliargs.coverage is True


def test_implicit_no_section_needed():
    """Implicit features work even when [features] section is absent."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "openmp"})
        assert cliargs.openmp is True
        # no warning should have been emitted (openmp is a known implicit feature)


def test_implicit_no_section_unknown_warns():
    """Unknown feature with no [features] section still emits a warning."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        warnings = []
        path = os.path.join(root, "fobos")
        with open(path, "w") as f:
            f.write(content)
        cliargs = argparse.Namespace(
            fobos=path,
            fobos_case_insensitive=False,
            mode=None,
            which="build",
            cflags="-c",
            lflags="",
            features="cuda",
            no_default_features=False,
            build_profile=None,
        )
        Fobos(cliargs=cliargs, print_w=warnings.append)
        assert any("cuda" in w for w in warnings)


def test_explicit_overrides_implicit():
    """Explicit [features] openmp definition wins over implicit resolution."""
    with tempfile.TemporaryDirectory() as root:
        # User defines openmp explicitly with raw flags (and a define)
        content = (
            "[features]\n"
            "openmp = -DUSE_OMP -fopenmp\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "openmp"})
        # Explicit definition routes -fopenmp via flag routing, not implicit
        assert "-DUSE_OMP" in cliargs.cflags
        assert "-fopenmp" in cliargs.cflags
        assert "-fopenmp" in cliargs.lflags
        # cliargs.openmp should NOT have been set by the implicit mechanism
        assert getattr(cliargs, "openmp", False) is False


def test_implicit_combined_with_explicit_feature():
    """Implicit openmp and explicit hdf5 feature can be active simultaneously."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "hdf5 = -DUSE_HDF5 -I/opt/hdf5/include\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "openmp,hdf5"})
        assert cliargs.openmp is True
        assert "-DUSE_HDF5" in cliargs.cflags
        assert "-I/opt/hdf5/include" in cliargs.cflags
