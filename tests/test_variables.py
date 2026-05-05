"""Tests for fobis $variable substitution and [varset:NAME] mechanism."""

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

    Variable substitution runs as part of Fobos construction, so the resulting
    cliargs has fully-substituted values (cflags, lflags, libs, lib_dir,
    include, …) ready for assertion.
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
        libs=[],
        lib_dir=[],
        include=[],
        features="",
        no_default_features=False,
        varset="",
        build_profile=None,
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


# ── Step 1: substitution prefix-collision bug fix ────────────────────────────


def test_substitute_simple_variable():
    """Baseline: a single $variable is substituted into a mode value."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[paths]\n"
            "$HDF5 = /opt/hdf5\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c -I$HDF5/include\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content)
        assert "-I/opt/hdf5/include" in cliargs.cflags
        # No literal $HDF5 left behind.
        assert "$HDF5" not in cliargs.cflags


def test_substitute_prefix_collision_does_not_mangle_longer_name():
    """Defining $HDF5 and $HDF5_PREFIX must not corrupt the longer name.

    Pre-existing bug: naive re.sub('$HDF5', ...) would match inside
    '$HDF5_PREFIX' and leave '/legacy_PREFIX' garbage in the output.
    The fix is a (?![A-Za-z0-9_]) negative-lookahead.
    """
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[paths]\n"
            "$HDF5        = /legacy/hdf5\n"
            "$HDF5_PREFIX = /modern/hdf5\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c -I$HDF5_PREFIX/include -L$HDF5/lib\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content)
        # The longer name resolves to its own value, not /legacy/hdf5_PREFIX.
        assert "-I/modern/hdf5/include" in cliargs.cflags
        # The shorter name still resolves correctly in its own context.
        assert "-L/legacy/hdf5/lib" in cliargs.cflags
        # Nothing of the form 'XXX_PREFIX' (the bug's fingerprint) leaked through.
        assert "_PREFIX" not in cliargs.cflags
        # No literal $-tokens left.
        assert "$HDF5" not in cliargs.cflags


def test_substitute_prefix_collision_at_end_of_value():
    """$HDF5 at end of string (no trailing char) still substitutes correctly."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[paths]\n"
            "$HDF5        = /legacy/hdf5\n"
            "$HDF5_PREFIX = /modern/hdf5\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c -I$HDF5\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content)
        # End-of-string position must trigger the lookahead pass.
        assert "-I/legacy/hdf5" in cliargs.cflags
        # Crucially: the value is exactly /legacy/hdf5, not /modern/hdf5
        # (which would happen if the lookahead were broken and $HDF5 were
        # eagerly matched to $HDF5_PREFIX's prefix).


def test_substitute_into_libs_list():
    """Substitution feeds list-typed mode values too (libs, lib_dir, include)."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[paths]\n"
            "$HDF5 = /opt/hdf5\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "libs     = $HDF5/lib/libhdf5_fortran.a $HDF5/lib/libhdf5.a\n"
            "lib_dir  = $HDF5/lib\n"
            "include  = $HDF5/include\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content)
        assert cliargs.libs == [
            "/opt/hdf5/lib/libhdf5_fortran.a",
            "/opt/hdf5/lib/libhdf5.a",
        ]
        assert cliargs.lib_dir == ["/opt/hdf5/lib"]
        assert cliargs.include == ["/opt/hdf5/include"]


# ── Step 2: [varset:*] sections are excluded from the implicit global pool ──


def test_varset_section_does_not_leak_into_global_pool():
    """A $variable defined inside [varset:NAME] must not bind globally.

    Without --varset selecting the section, the variable is unbound; the
    literal $-token must remain in the substituted value.  This guards
    against the regression of varset variables auto-merging into the
    global pool the way every other section's $-keys do.
    """
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[varset:leonardo]\n"
            "$HDF5_PREFIX = /leonardo/hdf5\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c -I$HDF5_PREFIX/include\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content)
        # No --varset given → the varset binding must not have been applied.
        # The literal $HDF5_PREFIX should still be present in the value.
        assert "$HDF5_PREFIX" in cliargs.cflags
        # And the leonardo path must NOT have leaked through.
        assert "/leonardo/hdf5" not in cliargs.cflags


def test_plain_variable_outside_varset_still_works():
    """The guard only skips [varset:*]; ordinary sections still contribute.

    Pin the existing behaviour: a $variable defined in a non-varset section
    (e.g. [paths], or any user-named section) is still merged into the
    global pool and substituted into mode values, exactly as today.
    """
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[paths]\n"
            "$HDF5_PREFIX = /opt/hdf5\n\n"
            "[varset:leonardo]\n"
            "$HDF5_PREFIX = /leonardo/hdf5\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c -I$HDF5_PREFIX/include\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content)
        # Plain definition wins (varset is silent without --varset).
        assert "-I/opt/hdf5/include" in cliargs.cflags
        assert "/leonardo/hdf5" not in cliargs.cflags


# ── Step 3: --varset selects a [varset:NAME] section ─────────────────────────


def test_varset_overrides_plain_variable():
    """--varset NAME overrides a plain $variable definition with the same name."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[paths]\n"
            "$HDF5_PREFIX = /opt/hdf5\n\n"
            "[varset:leonardo]\n"
            "$HDF5_PREFIX = /leonardo/hdf5\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c -I$HDF5_PREFIX/include\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"varset": "leonardo"})
        assert "-I/leonardo/hdf5/include" in cliargs.cflags
        assert "/opt/hdf5" not in cliargs.cflags


def test_varset_substitutes_into_libs_lib_dir_include():
    """The adam-style use case: cluster paths swapped via --varset.

    Demonstrates that varsets eliminate the per-cluster mode-block
    duplication: one mode + N varsets covers N clusters.
    """
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[varset:local]\n"
            "$HDF5_PREFIX = lib/hdf5/develop/nvf/26.1\n\n"
            "[varset:leonardo]\n"
            "$HDF5_PREFIX = /leonardo/prod/spack/hdf5-1.14.3\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "libs     = $HDF5_PREFIX/lib/libhdf5_fortran.a $HDF5_PREFIX/lib/libhdf5.a\n"
            "lib_dir  = $HDF5_PREFIX/lib\n"
            "include  = $HDF5_PREFIX/include\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"varset": "leonardo"})
        assert cliargs.libs == [
            "/leonardo/prod/spack/hdf5-1.14.3/lib/libhdf5_fortran.a",
            "/leonardo/prod/spack/hdf5-1.14.3/lib/libhdf5.a",
        ]
        assert cliargs.lib_dir == ["/leonardo/prod/spack/hdf5-1.14.3/lib"]
        assert cliargs.include == ["/leonardo/prod/spack/hdf5-1.14.3/include"]


def test_varset_unknown_aborts(capsys):
    """--varset NAME for an undefined varset exits 1 with a helpful list."""
    import pytest

    with tempfile.TemporaryDirectory() as root:
        content = (
            "[varset:local]\n"
            "$HDF5 = /opt/hdf5\n\n"
            "[varset:leonardo]\n"
            "$HDF5 = /leonardo/hdf5\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        with pytest.raises(SystemExit) as excinfo:
            _make_fobos(root, content, {"varset": "nonexistent"})
        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        msg = captured.out + captured.err
        assert "nonexistent" in msg
        # The error must list available varsets so the user can correct the typo.
        assert "leonardo" in msg
        assert "local" in msg


def test_varset_unknown_aborts_when_no_varsets_defined(capsys):
    """--varset NAME on a fobos with no [varset:*] sections explains the situation."""
    import pytest

    with tempfile.TemporaryDirectory() as root:
        content = "[default]\ncompiler = Gnu\ncflags   = -c\nlflags   =\nbuild_profile =\n"
        with pytest.raises(SystemExit) as excinfo:
            _make_fobos(root, content, {"varset": "leonardo"})
        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        msg = (captured.out + captured.err).lower()
        assert "leonardo" in msg
        # Tell the user there are no varsets at all rather than emitting an
        # empty 'Available varsets:' list.
        assert "no [varset:*]" in msg or "no varset" in msg


def test_varset_multiple_last_write_wins():
    """--varset a,b applies a then b; b overrides a for shared variables.

    Independent variables defined in different varsets all apply.
    """
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[varset:cluster-leonardo]\n"
            "$HDF5_PREFIX = /leonardo/hdf5\n"
            "$ARCH        = cc80\n\n"
            "[varset:gpu-cc89]\n"
            "$ARCH        = cc89\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c -gpu=$ARCH -I$HDF5_PREFIX/include\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        # Apply leonardo first, then gpu-cc89: $ARCH gets overridden;
        # $HDF5_PREFIX (only in leonardo) survives.
        _fobos, cliargs = _make_fobos(root, content, {"varset": "cluster-leonardo,gpu-cc89"})
        assert "-gpu=cc89" in cliargs.cflags
        assert "-I/leonardo/hdf5/include" in cliargs.cflags


def test_varset_warns_on_non_dollar_key(capsys):
    """A key without a leading $ inside a varset is warned about and ignored."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[varset:typo]\n"
            "HDF5_PREFIX = /should/be/ignored\n"
            "$REAL       = /actually/applied\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c -I$REAL/include\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"varset": "typo"})
        captured = capsys.readouterr()
        msg = (captured.out + captured.err).lower()
        assert "without a leading '$'" in msg or "without a leading $" in msg
        assert "hdf5_prefix" in msg
        # The well-formed key still applied.
        assert "-I/actually/applied/include" in cliargs.cflags


def test_varset_empty_warns(capsys):
    """A [varset:NAME] with no $-keys at all triggers a warning."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[varset:empty]\n"
            "; this varset has no $-bindings\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, _cliargs = _make_fobos(root, content, {"varset": "empty"})
        captured = capsys.readouterr()
        msg = (captured.out + captured.err).lower()
        assert "no variables" in msg or "defines no variables" in msg


def test_varset_compatible_with_features():
    """Varsets and features compose orthogonally: paths via varset, defines via feature."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[features]\n"
            "mpi = -DUSE_MPI\n\n"
            "[varset:leonardo]\n"
            "$HDF5_PREFIX = /leonardo/hdf5\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c -I$HDF5_PREFIX/include\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"varset": "leonardo", "features": "mpi"})
        assert "-I/leonardo/hdf5/include" in cliargs.cflags
        assert "-DUSE_MPI" in cliargs.cflags


def test_varset_no_flag_falls_back_to_plain():
    """Without --varset, plain $variables are used (existing behaviour preserved)."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[paths]\n"
            "$HDF5_PREFIX = /opt/hdf5\n\n"
            "[varset:leonardo]\n"
            "$HDF5_PREFIX = /leonardo/hdf5\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c -I$HDF5_PREFIX/include\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        # Note: cliargs.varset is "" by default in _make_fobos.
        _fobos, cliargs = _make_fobos(root, content)
        assert "-I/opt/hdf5/include" in cliargs.cflags


# ── Step 4: [varsets] default = ... — fobos-declared fallback ────────────────


def test_default_varset_applies_when_cli_omitted():
    """[varsets] default = NAME applies the named varset when --varset is absent."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[varsets]\n"
            "default = local\n\n"
            "[varset:local]\n"
            "$HDF5_PREFIX = /opt/hdf5/local\n\n"
            "[varset:leonardo]\n"
            "$HDF5_PREFIX = /leonardo/hdf5\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c -I$HDF5_PREFIX/include\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        # No --varset on CLI: default should kick in.
        _fobos, cliargs = _make_fobos(root, content)
        assert "-I/opt/hdf5/local/include" in cliargs.cflags
        assert "/leonardo/hdf5" not in cliargs.cflags


def test_cli_varset_overrides_default():
    """An explicit --varset on the CLI overrides the fobos-declared default."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[varsets]\n"
            "default = local\n\n"
            "[varset:local]\n"
            "$HDF5_PREFIX = /opt/hdf5/local\n\n"
            "[varset:leonardo]\n"
            "$HDF5_PREFIX = /leonardo/hdf5\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c -I$HDF5_PREFIX/include\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"varset": "leonardo"})
        # CLI choice wins — default does NOT also apply (no stacking).
        assert "-I/leonardo/hdf5/include" in cliargs.cflags
        assert "/opt/hdf5/local" not in cliargs.cflags


def test_default_varset_multiple():
    """[varsets] default = a b applies both varsets (last-write-wins)."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[varsets]\n"
            "default = base override\n\n"
            "[varset:base]\n"
            "$HDF5_PREFIX = /opt/base\n"
            "$ARCH        = cc70\n\n"
            "[varset:override]\n"
            "$ARCH        = cc89\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c -gpu=$ARCH -I$HDF5_PREFIX/include\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content)
        # Both apply: $HDF5_PREFIX from base, $ARCH from override.
        assert "-gpu=cc89" in cliargs.cflags
        assert "-I/opt/base/include" in cliargs.cflags


def test_default_varset_undefined_aborts(capsys):
    """A default varset that does not exist aborts with the same error as CLI."""
    import pytest

    with tempfile.TemporaryDirectory() as root:
        content = (
            "[varsets]\n"
            "default = nonexistent\n\n"
            "[varset:leonardo]\n"
            "$HDF5_PREFIX = /leonardo/hdf5\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        with pytest.raises(SystemExit) as excinfo:
            _make_fobos(root, content)
        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        assert "nonexistent" in (captured.out + captured.err)


def test_default_varset_only_no_varsets_section():
    """No [varsets] section → no default → behaves as today (no overlay)."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[paths]\n"
            "$HDF5_PREFIX = /opt/hdf5\n\n"
            "[varset:leonardo]\n"
            "$HDF5_PREFIX = /leonardo/hdf5\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c -I$HDF5_PREFIX/include\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content)
        # Plain definition wins; no varset auto-applied.
        assert "-I/opt/hdf5/include" in cliargs.cflags


# ── Step 5: introspection helper ─────────────────────────────────────────────


def test_get_varsets_info_lists_all_varsets():
    """get_varsets_info() returns every [varset:*] section's bindings + default."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[varsets]\n"
            "default = local\n\n"
            "[varset:local]\n"
            "$HDF5_PREFIX = /opt/hdf5/local\n\n"
            "[varset:leonardo]\n"
            "$HDF5_PREFIX = /leonardo/hdf5\n"
            "$ARCH        = cc80\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        fobos, _cliargs = _make_fobos(root, content)
        info = fobos.get_varsets_info()
        assert info["default"] == ["local"]
        assert set(info["varsets"].keys()) == {"local", "leonardo"}
        assert info["varsets"]["local"] == {"$HDF5_PREFIX": "/opt/hdf5/local"}
        assert info["varsets"]["leonardo"] == {
            "$HDF5_PREFIX": "/leonardo/hdf5",
            "$ARCH": "cc80",
        }


def test_get_varsets_info_empty_when_none_declared():
    """Fobos without [varset:*] returns an empty info dict, not None."""
    with tempfile.TemporaryDirectory() as root:
        content = "[default]\ncompiler = Gnu\ncflags   = -c\nlflags   =\nbuild_profile =\n"
        fobos, _cliargs = _make_fobos(root, content)
        info = fobos.get_varsets_info()
        assert info == {"default": [], "varsets": {}}
