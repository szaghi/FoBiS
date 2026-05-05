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

    ``features`` may appear on a mode block (it is merged with CLI input
    by ``_apply_features``).  ``no_default_features`` is CLI-only — placing
    it in a mode is silently ignored (see ``_SKIP_AUTO_ATTRS`` in Fobos).
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
            "[features]\nhdf5 = -DUSE_HDF5\n\n[default]\ncompiler = Gnu\ncflags   = -c\nlflags   =\nbuild_profile =\n"
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
        _fobos, cliargs = _make_fobos(root, content, {"features": "hdf5", "no_default_features": True})
        assert "-DUSE_HDF5" in cliargs.cflags
        assert "-DUSE_MPI" not in cliargs.cflags


def test_features_unknown_warns():
    """Unknown feature name → warning emitted, no abort."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\nmpi = -DUSE_MPI\n\n[default]\ncompiler = Gnu\ncflags   = -c\nlflags   =\nbuild_profile =\n"
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
        content = "[default]\ncompiler = Gnu\ncflags   = -c\nlflags   =\nbuild_profile =\n"
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
        content = "[default]\ncompiler = Gnu\ncflags   = -c\nlflags   =\nbuild_profile =\n"
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
        content = "[default]\ncompiler = Gnu\ncflags   = -c\nlflags   =\nbuild_profile =\n"
        _fobos, cliargs = _make_fobos(root, content, {"features": "openmp"})
        assert cliargs.openmp is True


def test_implicit_omp_alias_sets_cliarg():
    """Short alias 'omp' is equivalent to 'openmp'."""
    with tempfile.TemporaryDirectory() as root:
        content = "[default]\ncompiler = Gnu\ncflags   = -c\nlflags   =\nbuild_profile =\n"
        _fobos, cliargs = _make_fobos(root, content, {"features": "omp"})
        assert cliargs.openmp is True


def test_implicit_mpi_sets_cliarg():
    """--features mpi sets cliargs.mpi = True."""
    with tempfile.TemporaryDirectory() as root:
        content = "[default]\ncompiler = Gnu\ncflags   = -c\nlflags   =\nbuild_profile =\n"
        _fobos, cliargs = _make_fobos(root, content, {"features": "mpi"})
        assert cliargs.mpi is True


def test_implicit_coarray_sets_cliarg():
    """--features coarray sets cliargs.coarray = True."""
    with tempfile.TemporaryDirectory() as root:
        content = "[default]\ncompiler = Gnu\ncflags   = -c\nlflags   =\nbuild_profile =\n"
        _fobos, cliargs = _make_fobos(root, content, {"features": "coarray"})
        assert cliargs.coarray is True


def test_implicit_coverage_sets_cliarg():
    """--features coverage sets cliargs.coverage = True."""
    with tempfile.TemporaryDirectory() as root:
        content = "[default]\ncompiler = Gnu\ncflags   = -c\nlflags   =\nbuild_profile =\n"
        _fobos, cliargs = _make_fobos(root, content, {"features": "coverage"})
        assert cliargs.coverage is True


def test_implicit_no_section_needed():
    """Implicit features work even when [features] section is absent."""
    with tempfile.TemporaryDirectory() as root:
        content = "[default]\ncompiler = Gnu\ncflags   = -c\nlflags   =\nbuild_profile =\n"
        _fobos, cliargs = _make_fobos(root, content, {"features": "openmp"})
        assert cliargs.openmp is True
        # no warning should have been emitted (openmp is a known implicit feature)


def test_implicit_no_section_unknown_warns():
    """Unknown feature with no [features] section still emits a warning."""
    with tempfile.TemporaryDirectory() as root:
        content = "[default]\ncompiler = Gnu\ncflags   = -c\nlflags   =\nbuild_profile =\n"
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


# ── composite features (Tier 1: @-prefix expansion) ──────────────────────────


def test_composite_simple():
    """prod = @release @hdf5 → activating prod pulls in release + hdf5 leaves."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "release = -O3 -DNDEBUG\n"
            "hdf5    = -DUSE_HDF5\n"
            "prod    = @release @hdf5\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "prod"})
        assert "-O3" in cliargs.cflags
        assert "-DNDEBUG" in cliargs.cflags
        assert "-DUSE_HDF5" in cliargs.cflags
        # prod has no own flag tokens, but it is still recorded as active.
        assert "prod" in cliargs.active_features
        assert "release" in cliargs.active_features
        assert "hdf5" in cliargs.active_features


def test_composite_nested():
    """tier2 = @tier1 @coverage; tier1 = @debug. Activating tier2 → debug + coverage."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "debug    = -g -O0\n"
            "tier1    = @debug\n"
            "tier2    = @tier1 coverage\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "tier2"})
        assert "-g" in cliargs.cflags
        assert "-O0" in cliargs.cflags
        # 'coverage' inside the composite value (no @-prefix) is a literal flag
        # token of the tier2 leaf — not a reference to the implicit feature.
        # That is the documented behaviour: only @-tokens recurse.
        assert "coverage" in cliargs.cflags
        assert "debug" in cliargs.active_features
        assert "tier1" in cliargs.active_features
        assert "tier2" in cliargs.active_features


def test_composite_mixed_leaf_and_ref():
    """dev-mpi = @debug @mpi -DEXTRA_LOG → debug + mpi leaves + literal flag."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "debug   = -g -O0\n"
            "dev-mpi = @debug @mpi -DEXTRA_LOG\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "dev-mpi"})
        assert "-g" in cliargs.cflags
        assert "-O0" in cliargs.cflags
        assert "-DEXTRA_LOG" in cliargs.cflags
        # @mpi is implicit — flips the capability bool, no -D added.
        assert cliargs.mpi is True


def test_composite_cycle_detected(capsys):
    """a = @b; b = @a → cycle warning, no crash, no flags applied."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "a = @b -DA\n"
            "b = @a -DB\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "a"})
        captured = capsys.readouterr()
        # Cycle warning must surface; the build must not crash.
        assert "cycle" in (captured.out + captured.err).lower()
        # The starting leaf 'a' is still emitted (it was inserted before the
        # cycle was hit), so its own flag '-DA' is present, but 'b' must NOT
        # cause re-entry into 'a'.  Both leaves end up active because b was
        # walked before the back-edge to a was rejected.
        # The contract is: no infinite recursion, no crash, warning emitted.
        assert "-DA" in cliargs.cflags
        assert "-DB" in cliargs.cflags


def test_composite_implicit_reference():
    """accel = @openmp @mpi → both implicit capabilities flipped on."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "accel = @openmp @mpi\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "accel"})
        assert cliargs.openmp is True
        assert cliargs.mpi is True


# ── CLI negation (Tier 1: -name post-expansion filter) ───────────────────────


def test_negation_drops_default():
    """default = release coverage; --features -coverage → only release applied."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "default  = release coverage\n"
            "release  = -O3\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "-coverage"})
        assert "-O3" in cliargs.cflags
        # 'coverage' is implicit and would flip cliargs.coverage; negation must prevent that.
        assert cliargs.coverage is False
        assert "release" in cliargs.active_features
        assert "coverage" not in cliargs.active_features


def test_negation_inside_composite():
    """prod = @release @coverage; --features prod,-coverage → coverage removed."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "release  = -O3\n"
            "prod     = @release @coverage\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "prod,-coverage"})
        assert "-O3" in cliargs.cflags
        assert cliargs.coverage is False
        assert "prod" in cliargs.active_features
        assert "release" in cliargs.active_features
        assert "coverage" not in cliargs.active_features


def test_negation_post_expansion_order_independent():
    """'prod,-release' and '-release,prod' produce identical results."""
    base = (
        "[features]\n"
        "release  = -O3 -DNDEBUG\n"
        "prod     = @release\n\n"
        "[default]\n"
        "compiler = Gnu\n"
        "cflags   = -c\n"
        "lflags   =\n"
        "build_profile =\n"
    )
    with tempfile.TemporaryDirectory() as r1:
        _, cli_a = _make_fobos(r1, base, {"features": "prod,-release"})
    with tempfile.TemporaryDirectory() as r2:
        _, cli_b = _make_fobos(r2, base, {"features": "-release,prod"})
    assert cli_a.cflags == cli_b.cflags
    assert cli_a.active_features == cli_b.active_features
    # Sanity: -release was removed in both — no -O3 leaked through.
    assert "-O3" not in cli_a.cflags
    assert "-DNDEBUG" not in cli_a.cflags
    # 'prod' itself has no own flags, so it stays active without contributing flags.
    assert "prod" in cli_a.active_features
    assert "release" not in cli_a.active_features


# ── mode-level features = a b c (Tier 1: per-mode declaration) ───────────────


def test_mode_features_picked_up():
    """[default] features = release mpi → both activated without --features."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "release = -O3\n"
            "mpi     = -DUSE_MPI\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
            "features = release mpi\n"
        )
        _fobos, cliargs = _make_fobos(root, content)
        assert "-O3" in cliargs.cflags
        assert "-DUSE_MPI" in cliargs.cflags
        assert "release" in cliargs.active_features
        assert "mpi" in cliargs.active_features


def test_mode_features_merge_with_cli():
    """Mode declares 'release', CLI passes 'mpi' → both active (mode + CLI merge)."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "release = -O3\n"
            "mpi     = -DUSE_MPI\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
            "features = release\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "mpi"})
        assert "-O3" in cliargs.cflags
        assert "-DUSE_MPI" in cliargs.cflags
        assert "release" in cliargs.active_features
        assert "mpi" in cliargs.active_features


def test_mode_features_does_not_overwrite_cliargs_features_string():
    """Regression: mode 'features = a b' must NOT clobber CLI '--features c'.

    Before the skip-list in _set_cliargs_attributes, configparser auto-copy
    would replace cliargs.features with the mode string, dropping CLI input.
    """
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "a = -DA\n"
            "b = -DB\n"
            "c = -DC\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
            "features = a b\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "c"})
        # All three must be present; CLI input was not overwritten.
        assert "-DA" in cliargs.cflags
        assert "-DB" in cliargs.cflags
        assert "-DC" in cliargs.cflags
        # And cliargs.features (the raw CLI string) must still be 'c', not 'a b'.
        assert cliargs.features == "c"


def test_mode_features_with_negation():
    """Mode declares 'release coverage', CLI '-coverage' drops it."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "release = -O3\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
            "features = release coverage\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "-coverage"})
        assert "-O3" in cliargs.cflags
        assert cliargs.coverage is False
        assert "coverage" not in cliargs.active_features


def test_negation_unmatched_warns(capsys):
    """--features -nonexistent must surface a warning (likely typo)."""
    with tempfile.TemporaryDirectory() as root:
        content = "[features]\nrelease = -O3\n\n[default]\ncompiler = Gnu\ncflags   = -c\nlflags   =\nbuild_profile =\n"
        _fobos, cliargs = _make_fobos(root, content, {"features": "release,-nonexistent"})
        captured = capsys.readouterr()
        msg = (captured.out + captured.err).lower()
        assert "negation" in msg
        assert "nonexistent" in msg
        # The valid feature still applies.
        assert "-O3" in cliargs.cflags


# ── Tier 2: feature metadata sections ────────────────────────────────────────


def test_tier2_no_metadata_section_unchanged():
    """A fobos with no [feature:X] / [feature-group:X] sections behaves identically.

    Sanity check: introducing the metadata layer must not change anything for
    projects that stick with the legacy flat [features] form.
    """
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "default = mpi hdf5\n"
            "mpi   = -DUSE_MPI\n"
            "hdf5  = -DUSE_HDF5\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content)
        assert "-DUSE_MPI" in cliargs.cflags
        assert "-DUSE_HDF5" in cliargs.cflags
        assert "mpi" in cliargs.active_features
        assert "hdf5" in cliargs.active_features


def test_feature_metadata_section_alone():
    """[feature:X] flags = -DA acts identically to [features] X = -DA."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[feature:hdf5]\n"
            "flags = -DUSE_HDF5 -I/opt/hdf5/include\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "hdf5"})
        assert "-DUSE_HDF5" in cliargs.cflags
        assert "-I/opt/hdf5/include" in cliargs.cflags
        assert "hdf5" in cliargs.active_features


def test_feature_metadata_section_double_declaration_errors():
    """Defining flags in BOTH [features] and [feature:X] is a hard error.

    The user has two sources of truth for the same feature's flags — there is
    no sane merge rule, so abort with exit 1.
    """
    import pytest

    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "hdf5 = -DUSE_HDF5\n\n"
            "[feature:hdf5]\n"
            "flags = -DUSE_HDF5_DIFFERENT\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        with pytest.raises(SystemExit) as excinfo:
            _make_fobos(root, content, {"features": "hdf5"})
        assert excinfo.value.code == 1


def test_feature_metadata_section_extends_legacy_entry():
    """[features] X = -DA + [feature:X] requires = ... is allowed (metadata extends flags).

    Step 1 only checks parsing — the requires field is not yet enforced
    (that is Step 2).  This test pins down that mixing the two forms is
    allowed when there is no flag-string conflict.
    """
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "hdf5 = -DUSE_HDF5\n\n"
            "[feature:hdf5]\n"
            "requires = mpi\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        # No SystemExit; flags resolve from [features], metadata accepted.
        _fobos, cliargs = _make_fobos(root, content, {"features": "hdf5"})
        assert "-DUSE_HDF5" in cliargs.cflags


def test_feature_group_section_parses():
    """[feature-group:X] sections are parsed without affecting Step 1 behaviour."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "single = -DPRECISION_SINGLE\n"
            "double = -DPRECISION_DOUBLE\n\n"
            "[feature-group:precision]\n"
            "members = single double\n"
            "default = double\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        # Step 1: groups parsed but not enforced. Activating a member is fine.
        fobos, cliargs = _make_fobos(root, content, {"features": "single"})
        assert "-DPRECISION_SINGLE" in cliargs.cflags
        # Reader sanity check.
        groups = fobos.get_feature_groups()
        assert "precision" in groups
        assert groups["precision"].members == ["single", "double"]
        assert groups["precision"].default == "double"


# ── Tier 2: requires (auto-pull + cycle-safe) ────────────────────────────────


def test_requires_pulls_in_prereq():
    """Activating a feature with `requires = X` auto-activates X."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "mpi  = -DUSE_MPI\n"
            "hdf5 = -DUSE_HDF5\n\n"
            "[feature:hdf5]\n"
            "requires = mpi\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "hdf5"})
        assert "-DUSE_HDF5" in cliargs.cflags
        assert "-DUSE_MPI" in cliargs.cflags
        assert "mpi" in cliargs.active_features
        assert "hdf5" in cliargs.active_features


def test_requires_transitive():
    """A requires B; B requires C → activating A pulls all three."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "a = -DA\n"
            "b = -DB\n"
            "c = -DC\n\n"
            "[feature:a]\n"
            "requires = b\n\n"
            "[feature:b]\n"
            "requires = c\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "a"})
        assert "-DA" in cliargs.cflags
        assert "-DB" in cliargs.cflags
        assert "-DC" in cliargs.cflags


def test_requires_cycle_handled(capsys):
    """A requires B; B requires A → cycle warning, no crash, both active."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "a = -DA\n"
            "b = -DB\n\n"
            "[feature:a]\n"
            "requires = b\n\n"
            "[feature:b]\n"
            "requires = a\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "a"})
        captured = capsys.readouterr()
        assert "cycle" in (captured.out + captured.err).lower()
        # Both should be active despite the cycle (each was pulled exactly once).
        assert "-DA" in cliargs.cflags
        assert "-DB" in cliargs.cflags


def test_requires_unknown_warns(capsys):
    """A requires X (X undefined) → unknown-feature warning surfaces."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "a = -DA\n\n"
            "[feature:a]\n"
            "requires = nonexistent\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "a"})
        captured = capsys.readouterr()
        msg = (captured.out + captured.err).lower()
        # The unknown feature is auto-pulled into active set, then the leaf
        # resolution loop emits the existing unknown-feature warning.
        assert "unknown" in msg
        assert "nonexistent" in msg
        # The valid feature still applies.
        assert "-DA" in cliargs.cflags


def test_requires_emits_info(capsys):
    """An auto-pulled prereq emits 'Activating X required by Y'."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "mpi  = -DUSE_MPI\n"
            "hdf5 = -DUSE_HDF5\n\n"
            "[feature:hdf5]\n"
            "requires = mpi\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _make_fobos(root, content, {"features": "hdf5"})
        captured = capsys.readouterr()
        msg = captured.out + captured.err
        assert "Activating 'mpi'" in msg
        assert "required by 'hdf5'" in msg


# ── Tier 2: conflicts (hard error, verbose message) ──────────────────────────


def test_conflicts_aborts(capsys):
    """X conflicts Y; both active → SystemExit(1) with verbose message."""
    import pytest

    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "static = -static\n"
            "shared = -shared\n\n"
            "[feature:static]\n"
            "conflicts = shared\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        with pytest.raises(SystemExit) as excinfo:
            _make_fobos(root, content, {"features": "static,shared"})
        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        msg = captured.out + captured.err
        assert "static" in msg
        assert "shared" in msg
        assert "conflict" in msg.lower()


def test_conflicts_via_requires(capsys):
    """X requires A; Y requires B; A conflicts B → error names originators."""
    import pytest

    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "embedded = -DEMBEDDED\n"
            "plugin   = -DPLUGIN\n"
            "static   = -static\n"
            "shared   = -shared\n\n"
            "[feature:embedded]\n"
            "requires = static\n\n"
            "[feature:plugin]\n"
            "requires = shared\n\n"
            "[feature:static]\n"
            "conflicts = shared\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        with pytest.raises(SystemExit) as excinfo:
            _make_fobos(root, content, {"features": "embedded,plugin"})
        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        msg = captured.out + captured.err
        # Message must trace 'static' back to 'embedded' and 'shared' back to 'plugin'.
        assert "static" in msg
        assert "shared" in msg
        assert "required by 'embedded'" in msg
        assert "required by 'plugin'" in msg


def test_conflicts_self_warns(capsys):
    """[feature:X] conflicts = X is silly but should warn, not abort."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "weird = -DWEIRD\n\n"
            "[feature:weird]\n"
            "conflicts = weird\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "weird"})
        # No SystemExit; the feature is still applied.
        assert "-DWEIRD" in cliargs.cflags
        captured = capsys.readouterr()
        msg = (captured.out + captured.err).lower()
        assert "self" in msg or "itself" in msg
        assert "weird" in msg


def test_conflicts_symmetric_no_duplicate(capsys):
    """A conflicts B AND B conflicts A → single error message, not two."""
    import pytest

    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "a = -DA\n"
            "b = -DB\n\n"
            "[feature:a]\n"
            "conflicts = b\n\n"
            "[feature:b]\n"
            "conflicts = a\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        with pytest.raises(SystemExit):
            _make_fobos(root, content, {"features": "a,b"})
        captured = capsys.readouterr()
        msg = captured.out + captured.err
        # The 'X and Y conflict' phrase should appear exactly once.
        assert msg.lower().count("conflict.") == 1


# ── Tier 2: feature groups (at-most-one + optional default) ──────────────────


def test_group_at_most_one_violation(capsys):
    """Two members of a mutually-exclusive group active → SystemExit(1)."""
    import pytest

    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "single = -DPRECISION_SINGLE\n"
            "double = -DPRECISION_DOUBLE\n\n"
            "[feature-group:precision]\n"
            "members = single double\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        with pytest.raises(SystemExit) as excinfo:
            _make_fobos(root, content, {"features": "single,double"})
        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        msg = (captured.out + captured.err).lower()
        assert "precision" in msg
        assert "mutually" in msg or "exclusive" in msg


def test_group_default_fills_empty():
    """Group has default = double, no member activated → double is auto-active."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "single = -DPRECISION_SINGLE\n"
            "double = -DPRECISION_DOUBLE\n\n"
            "[feature-group:precision]\n"
            "members = single double\n"
            "default = double\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        # No --features at all: group default fills.
        _fobos, cliargs = _make_fobos(root, content)
        assert "-DPRECISION_DOUBLE" in cliargs.cflags
        assert "double" in cliargs.active_features


def test_group_default_suppressed_by_explicit():
    """User activates `single`; group default `double` must NOT be auto-pulled."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "single = -DPRECISION_SINGLE\n"
            "double = -DPRECISION_DOUBLE\n\n"
            "[feature-group:precision]\n"
            "members = single double\n"
            "default = double\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "single"})
        assert "-DPRECISION_SINGLE" in cliargs.cflags
        assert "-DPRECISION_DOUBLE" not in cliargs.cflags


def test_group_negation_drops_default():
    """User passes -double → group is left empty (intentional negation wins)."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "single = -DPRECISION_SINGLE\n"
            "double = -DPRECISION_DOUBLE\n\n"
            "[feature-group:precision]\n"
            "members = single double\n"
            "default = double\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "-double"})
        # Neither member ends up active.
        assert "-DPRECISION_SINGLE" not in cliargs.cflags
        assert "-DPRECISION_DOUBLE" not in cliargs.cflags
        assert "double" not in cliargs.active_features
        assert "single" not in cliargs.active_features


def test_group_default_fills_with_other_features_active():
    """Other features active but no group member → group default still fills."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "mpi    = -DUSE_MPI\n"
            "single = -DPRECISION_SINGLE\n"
            "double = -DPRECISION_DOUBLE\n\n"
            "[feature-group:precision]\n"
            "members = single double\n"
            "default = double\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "mpi"})
        assert "-DUSE_MPI" in cliargs.cflags
        assert "-DPRECISION_DOUBLE" in cliargs.cflags
        assert "-DPRECISION_SINGLE" not in cliargs.cflags


# ── Tier 2: integration ──────────────────────────────────────────────────────


_TIER2_INTEGRATION_FOBOS = (
    "[features]\n"
    "default = release\n"
    "release  = -O3 -DNDEBUG\n"
    "debug    = -g -O0\n"
    "single   = -DPRECISION_SINGLE\n"
    "double   = -DPRECISION_DOUBLE\n"
    "mpi      = -DUSE_MPI\n"
    "hdf5     = -DUSE_HDF5\n"
    "embedded = -DEMBEDDED\n"
    "static   = -static\n"
    "shared   = -shared\n"
    "prod     = @release @hdf5\n\n"
    "[feature:hdf5]\n"
    "requires = mpi\n\n"
    "[feature:embedded]\n"
    "requires = static\n\n"
    "[feature:static]\n"
    "conflicts = shared\n\n"
    "[feature-group:precision]\n"
    "members = single double\n"
    "default = double\n\n"
    "[default]\n"
    "compiler = Gnu\n"
    "cflags   = -c\n"
    "lflags   =\n"
    "build_profile =\n"
)


def test_tier2_integration_full_valid():
    """All Tier 2 features compose: composite + group default + requires."""
    with tempfile.TemporaryDirectory() as root:
        _fobos, cliargs = _make_fobos(root, _TIER2_INTEGRATION_FOBOS, {"features": "prod"})
        # default 'release' + composite 'prod' (= release + hdf5)
        assert "-O3" in cliargs.cflags
        assert "-DNDEBUG" in cliargs.cflags
        # hdf5 requires mpi → mpi auto-pulled
        assert "-DUSE_HDF5" in cliargs.cflags
        assert "-DUSE_MPI" in cliargs.cflags
        # group precision empty → default 'double' kicks in
        assert "-DPRECISION_DOUBLE" in cliargs.cflags
        assert "-DPRECISION_SINGLE" not in cliargs.cflags
        # No conflicts triggered.


def test_tier2_integration_conflict_via_requires(capsys):
    """Activating embedded + shared triggers static-vs-shared conflict via requires."""
    import pytest

    with tempfile.TemporaryDirectory() as root:
        with pytest.raises(SystemExit) as excinfo:
            _make_fobos(root, _TIER2_INTEGRATION_FOBOS, {"features": "embedded,shared"})
        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        msg = captured.out + captured.err
        assert "static" in msg
        assert "shared" in msg
        assert "required by 'embedded'" in msg


def test_tier2_integration_explicit_overrides_group_default():
    """Activating 'single' suppresses precision group default 'double'."""
    with tempfile.TemporaryDirectory() as root:
        _fobos, cliargs = _make_fobos(root, _TIER2_INTEGRATION_FOBOS, {"features": "single"})
        assert "-DPRECISION_SINGLE" in cliargs.cflags
        assert "-DPRECISION_DOUBLE" not in cliargs.cflags


def test_tier2_integration_group_violation_aborts(capsys):
    """Activating both single and double aborts with the group error message."""
    import pytest

    with tempfile.TemporaryDirectory() as root:
        with pytest.raises(SystemExit) as excinfo:
            _make_fobos(root, _TIER2_INTEGRATION_FOBOS, {"features": "single,double"})
        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        msg = (captured.out + captured.err).lower()
        assert "precision" in msg
