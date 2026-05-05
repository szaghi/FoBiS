"""Tests for the [include] directive in fobos files."""

from __future__ import annotations

import argparse
import configparser
import os
import tempfile

from fobis.Fobos import Fobos, _merge_into, _resolve_includes


def _write(path: str, content: str) -> None:
    with open(path, "w") as f:
        f.write(content)


def _make_parser(content: str | None = None) -> configparser.RawConfigParser:
    """Construct a case-sensitive RawConfigParser, optionally seeded from text."""
    parser = configparser.RawConfigParser()
    parser.optionxform = str
    if content is not None:
        parser.read_string(content)
    return parser


def _make_fobos(
    root: str,
    fobos_content: str,
    extra_cliargs: dict | None = None,
) -> tuple[Fobos, argparse.Namespace]:
    """Write the main fobos and instantiate a Fobos with substitution-friendly cliargs.

    The helper mirrors tests/test_variables.py so that include-merged results can
    be asserted on cliargs the same way variable substitution is.
    """
    path = os.path.join(root, "fobos")
    _write(path, fobos_content)
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


# ── Step 1: helpers in isolation ─────────────────────────────────────────────


def test_no_include_section_unchanged():
    """A parser without [include] is left untouched by _resolve_includes."""
    with tempfile.TemporaryDirectory() as root:
        path = os.path.join(root, "fobos")
        _write(path, "[default]\ncompiler = Gnu\ncflags   = -c -O2\n")
        parser = _make_parser()
        parser.read(path)
        before_sections = sorted(parser.sections())
        before_items = dict(parser.items("default"))
        _resolve_includes(parser, base_path=path, print_w=None, case_insensitive=False)
        assert sorted(parser.sections()) == before_sections
        assert dict(parser.items("default")) == before_items


def test_simple_include_pulls_in_section():
    """[include] paths = X.fobos merges X's sections into the parent."""
    with tempfile.TemporaryDirectory() as root:
        # The included file declares [template-gnu]; the main fobos uses it
        # in [default] and adds [include].  After resolution, the parser
        # contains both sections and the [include] directive is gone.
        included = os.path.join(root, "templates.fobos")
        _write(
            included,
            "[template-gnu]\ncompiler = gnu\ncflags   = -cpp -c -O2\n",
        )
        main = os.path.join(root, "fobos")
        _write(
            main,
            "[include]\npaths = templates.fobos\n\n[default]\ncompiler = gnu\ncflags   = -c\n",
        )
        parser = _make_parser()
        parser.read(main)
        _resolve_includes(parser, base_path=main, print_w=None, case_insensitive=False)
        # [include] removed; [template-gnu] absorbed; [default] preserved.
        assert not parser.has_section("include")
        assert parser.has_section("template-gnu")
        assert parser.get("template-gnu", "compiler") == "gnu"
        assert parser.get("template-gnu", "cflags") == "-cpp -c -O2"
        assert parser.has_section("default")


def test_merge_into_parent_wins():
    """_merge_into with child_wins=False preserves target values on conflict."""
    target = _make_parser("[mode-X]\ncflags = -O2\ntarget = main.f90\n")
    source = _make_parser("[mode-X]\ncflags = -O0\nmod_dir = ./mod/\n")
    _merge_into(target, source, child_wins=False)
    assert target.get("mode-X", "cflags") == "-O2"  # parent wins on conflict
    assert target.get("mode-X", "target") == "main.f90"  # parent's own keys preserved
    assert target.get("mode-X", "mod_dir") == "./mod/"  # missing key filled from child


def test_merge_into_child_wins():
    """_merge_into with child_wins=True overwrites target values on conflict."""
    target = _make_parser("[mode-X]\ncflags = -O2\n")
    source = _make_parser("[mode-X]\ncflags = -O0\nmod_dir = ./mod/\n")
    _merge_into(target, source, child_wins=True)
    assert target.get("mode-X", "cflags") == "-O0"  # child wins on conflict
    assert target.get("mode-X", "mod_dir") == "./mod/"


# ── Step 2: end-to-end through Fobos construction ────────────────────────────


def test_include_e2e_through_fobos():
    """Fobos construction resolves includes and produces a substituted cliargs."""
    with tempfile.TemporaryDirectory() as root:
        # An included file defines a $variable used by the main mode.
        _write(
            os.path.join(root, "paths.fobos"),
            "[paths]\n$HDF5_PREFIX = /opt/hdf5\n",
        )
        content = (
            "[include]\n"
            "paths = paths.fobos\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c -I$HDF5_PREFIX/include\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content)
        # The included $HDF5_PREFIX flowed through the substitution pipeline.
        assert "-I/opt/hdf5/include" in cliargs.cflags


# ── Step 3: path resolution + ? optional prefix ──────────────────────────────


def test_path_relative_to_including_file():
    """Relative paths resolve against the *including* file's directory.

    Place the included file in a sub-directory and reference it as
    'sub/templates.fobos' from a main fobos at the project root.
    """
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, "sub"))
        _write(
            os.path.join(root, "sub", "templates.fobos"),
            "[template-gnu]\ncompiler = gnu\ncflags = -O3\n",
        )
        content = (
            "[include]\n"
            "paths = sub/templates.fobos\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        fobos, _cliargs = _make_fobos(root, content)
        assert fobos.fobos.has_section("template-gnu")
        assert fobos.fobos.get("template-gnu", "cflags") == "-O3"


def test_path_absolute():
    """Absolute paths are honoured as-is, regardless of including-file location."""
    with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as other_root:
        included_abs = os.path.join(other_root, "external.fobos")
        _write(included_abs, "[template-gnu]\ncompiler = gnu\ncflags = -Owow\n")
        content = (
            f"[include]\npaths = {included_abs}\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        fobos, _cliargs = _make_fobos(root, content)
        assert fobos.fobos.get("template-gnu", "cflags") == "-Owow"


def test_path_envvar_expansion(monkeypatch):
    """${ENVVAR} in include paths is expanded via os.path.expandvars."""
    with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as other_root:
        _write(
            os.path.join(other_root, "external.fobos"),
            "[paths]\n$EXTRA = /from/envvar\n",
        )
        monkeypatch.setenv("FOBIS_TEST_INCLUDE_DIR", other_root)
        content = (
            "[include]\n"
            "paths = ${FOBIS_TEST_INCLUDE_DIR}/external.fobos\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c -I$EXTRA\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content)
        assert "-I/from/envvar" in cliargs.cflags


def test_path_tilde_expansion(monkeypatch):
    """~ in include paths is expanded via os.path.expanduser."""
    with tempfile.TemporaryDirectory() as fake_home:
        # Stage an included file at $fake_home/.fobis/local.fobos and point
        # ~ at fake_home so '~/.fobis/local.fobos' resolves there.
        sub = os.path.join(fake_home, ".fobis")
        os.makedirs(sub)
        _write(
            os.path.join(sub, "local.fobos"),
            "[paths]\n$LOCAL = /tilde/path\n",
        )
        monkeypatch.setenv("HOME", fake_home)
        with tempfile.TemporaryDirectory() as root:
            content = (
                "[include]\n"
                "paths = ~/.fobis/local.fobos\n\n"
                "[default]\n"
                "compiler = Gnu\n"
                "cflags   = -c -I$LOCAL\n"
                "lflags   =\n"
                "build_profile =\n"
            )
            _fobos, cliargs = _make_fobos(root, content)
            assert "-I/tilde/path" in cliargs.cflags


def test_required_missing_aborts(capsys):
    """A required (no '?' prefix) include that is missing aborts with exit 1."""
    import pytest

    with tempfile.TemporaryDirectory() as root:
        content = (
            "[include]\n"
            "paths = does-not-exist.fobos\n\n"
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
        msg = captured.out + captured.err
        # Error message names the missing file and suggests the optional form.
        assert "does-not-exist.fobos" in msg
        assert "?" in msg


def test_optional_missing_silent():
    """A '?' prefixed include that is missing is silently skipped."""
    with tempfile.TemporaryDirectory() as root:
        content = (
            "[include]\n"
            "paths = ?does-not-exist.fobos\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c -O2\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        # Build proceeds; the optional include simply did not contribute.
        _fobos, cliargs = _make_fobos(root, content)
        assert "-O2" in cliargs.cflags


def test_optional_present_applies():
    """A '?' prefixed include that exists is applied normally (just optional, not different)."""
    with tempfile.TemporaryDirectory() as root:
        _write(
            os.path.join(root, "local.fobos"),
            "[paths]\n$EXTRA = /local/value\n",
        )
        content = (
            "[include]\n"
            "paths = ?local.fobos\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c -I$EXTRA\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content)
        assert "-I/local/value" in cliargs.cflags


# ── Step 4: merge semantics through actual files ─────────────────────────────


def test_parent_wins_on_conflict_e2e():
    """Main fobos and included file both define a key; main wins."""
    with tempfile.TemporaryDirectory() as root:
        _write(
            os.path.join(root, "templates.fobos"),
            "[template-gnu]\ncompiler = gnu\ncflags = -INCLUDED\n",
        )
        content = (
            "[include]\n"
            "paths = templates.fobos\n\n"
            "[template-gnu]\n"
            "cflags = -MAIN\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        fobos, _cliargs = _make_fobos(root, content)
        # Main's value of cflags wins; compiler key (only in include) survives.
        assert fobos.fobos.get("template-gnu", "cflags") == "-MAIN"
        assert fobos.fobos.get("template-gnu", "compiler") == "gnu"


def test_parent_fills_in_keys_from_include():
    """Keys present only in the include are absorbed into the parent."""
    with tempfile.TemporaryDirectory() as root:
        _write(
            os.path.join(root, "templates.fobos"),
            "[template-gnu]\ncompiler = gnu\ncflags = -O3\nmod_dir = ./mod/gnu/\n",
        )
        content = (
            "[include]\n"
            "paths = templates.fobos\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        fobos, _cliargs = _make_fobos(root, content)
        # All three keys from the include flow into the merged parser.
        assert fobos.fobos.get("template-gnu", "compiler") == "gnu"
        assert fobos.fobos.get("template-gnu", "cflags") == "-O3"
        assert fobos.fobos.get("template-gnu", "mod_dir") == "./mod/gnu/"


def test_sibling_last_wins():
    """Among sibling includes, the last one in `paths =` wins on conflict."""
    with tempfile.TemporaryDirectory() as root:
        _write(
            os.path.join(root, "a.fobos"),
            "[template-gnu]\ncflags = -FIRST\nfirst_only = a-key\n",
        )
        _write(
            os.path.join(root, "b.fobos"),
            "[template-gnu]\ncflags = -LAST\nlast_only = b-key\n",
        )
        content = (
            "[include]\n"
            "paths = a.fobos b.fobos\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        fobos, _cliargs = _make_fobos(root, content)
        # b.fobos appears later → its cflags win.
        assert fobos.fobos.get("template-gnu", "cflags") == "-LAST"
        # Each sibling's unique keys still survive.
        assert fobos.fobos.get("template-gnu", "first_only") == "a-key"
        assert fobos.fobos.get("template-gnu", "last_only") == "b-key"


def test_parent_wins_over_last_sibling():
    """Parent's own value beats even the last-included sibling."""
    with tempfile.TemporaryDirectory() as root:
        _write(
            os.path.join(root, "a.fobos"),
            "[template-gnu]\ncflags = -A\n",
        )
        _write(
            os.path.join(root, "b.fobos"),
            "[template-gnu]\ncflags = -B\n",
        )
        content = (
            "[include]\n"
            "paths = a.fobos b.fobos\n\n"
            "[template-gnu]\n"
            "cflags = -PARENT\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        fobos, _cliargs = _make_fobos(root, content)
        assert fobos.fobos.get("template-gnu", "cflags") == "-PARENT"


def test_paths_separators_mixed():
    """`paths` accepts whitespace and newline separators interchangeably."""
    with tempfile.TemporaryDirectory() as root:
        _write(os.path.join(root, "a.fobos"), "[paths]\n$A = a-val\n")
        _write(os.path.join(root, "b.fobos"), "[paths]\n$B = b-val\n")
        # Mix newline-continuation and space-separated tokens.
        content = (
            "[include]\n"
            "paths = a.fobos\n"
            "        b.fobos\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c -I$A -I$B\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content)
        assert "-Ia-val" in cliargs.cflags
        assert "-Ib-val" in cliargs.cflags


# ── Step 5: recursion + cycle detection + depth cap ──────────────────────────


def test_recursive_include():
    """A → B → C: contents from C reach A through transitive merge."""
    with tempfile.TemporaryDirectory() as root:
        _write(
            os.path.join(root, "c.fobos"),
            "[paths]\n$DEEP = /from/c\n",
        )
        _write(
            os.path.join(root, "b.fobos"),
            "[include]\npaths = c.fobos\n\n[paths]\n$MID = /from/b\n",
        )
        # Main includes b, b includes c.
        content = (
            "[include]\n"
            "paths = b.fobos\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c -I$DEEP -I$MID\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content)
        assert "-I/from/c" in cliargs.cflags
        assert "-I/from/b" in cliargs.cflags


def test_cycle_detected(capsys):
    """A → B → A produces a cycle error and exits 1, no infinite loop."""
    import pytest

    with tempfile.TemporaryDirectory() as root:
        # a includes b, b includes a — a self-referential pair.
        _write(
            os.path.join(root, "a.fobos"),
            "[include]\npaths = b.fobos\n\n[paths]\n$A = a-val\n",
        )
        _write(
            os.path.join(root, "b.fobos"),
            "[include]\npaths = a.fobos\n",
        )
        content = (
            "[include]\npaths = a.fobos\n\n[default]\ncompiler = Gnu\ncflags   = -c\nlflags   =\nbuild_profile =\n"
        )
        with pytest.raises(SystemExit) as excinfo:
            _make_fobos(root, content)
        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        msg = (captured.out + captured.err).lower()
        assert "cycle" in msg


def test_self_include_detected(capsys):
    """A file that includes itself is treated as a cycle."""
    import pytest

    with tempfile.TemporaryDirectory() as root:
        # main fobos that includes itself.
        path = os.path.join(root, "fobos")
        content = "[include]\npaths = fobos\n\n[default]\ncompiler = Gnu\ncflags   = -c\nlflags   =\nbuild_profile =\n"
        _write(path, content)
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
        with pytest.raises(SystemExit) as excinfo:
            Fobos(cliargs=cliargs, print_w=lambda m: None)
        assert excinfo.value.code == 1


def test_depth_exceeded(capsys):
    """A chain of includes longer than _INCLUDE_MAX_DEPTH aborts cleanly."""
    import pytest

    from fobis.Fobos import _INCLUDE_MAX_DEPTH

    with tempfile.TemporaryDirectory() as root:
        # Create a chain of files each including the next, longer than the cap.
        chain_len = _INCLUDE_MAX_DEPTH + 2
        for i in range(chain_len):
            next_target = f"chain-{i + 1}.fobos" if i + 1 < chain_len else None
            body = ""
            if next_target is not None:
                body += f"[include]\npaths = {next_target}\n\n"
            body += f"[paths]\n$LEVEL_{i} = level-{i}\n"
            _write(os.path.join(root, f"chain-{i}.fobos"), body)
        content = (
            "[include]\n"
            "paths = chain-0.fobos\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        with pytest.raises(SystemExit) as excinfo:
            _make_fobos(root, content)
        assert excinfo.value.code == 1
        msg = (capsys.readouterr().out + capsys.readouterr().err).lower()
        assert "depth" in msg or "recursion" in msg


def test_diamond_include_no_cycle():
    """A → B → D and A → C → D is a diamond, not a cycle. Should resolve fine."""
    with tempfile.TemporaryDirectory() as root:
        # Shared leaf
        _write(
            os.path.join(root, "d.fobos"),
            "[paths]\n$LEAF = /leaf/path\n",
        )
        _write(
            os.path.join(root, "b.fobos"),
            "[include]\npaths = d.fobos\n",
        )
        _write(
            os.path.join(root, "c.fobos"),
            "[include]\npaths = d.fobos\n",
        )
        content = (
            "[include]\n"
            "paths = b.fobos c.fobos\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c -I$LEAF\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        # No SystemExit: diamonds are not cycles.  D is loaded twice
        # (once via B, once via C); the second load is independent of
        # the first because the visited-set is per-walk down each branch.
        _fobos, cliargs = _make_fobos(root, content)
        assert "-I/leaf/path" in cliargs.cflags


# ── Step 6: composition with features, varsets, templates ────────────────────


def test_include_features_section():
    """An included file's [features] section is honoured by the active mode."""
    with tempfile.TemporaryDirectory() as root:
        _write(
            os.path.join(root, "features.fobos"),
            "[features]\nmpi = -DUSE_MPI\nhdf5 = -DUSE_HDF5\n",
        )
        content = (
            "[include]\n"
            "paths = features.fobos\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "mpi,hdf5"})
        assert "-DUSE_MPI" in cliargs.cflags
        assert "-DUSE_HDF5" in cliargs.cflags


def test_include_feature_constraints_compose():
    """An included [feature:NAME] block applies its `requires` after merge.

    The included file declares hdf5 with `requires = mpi`; activating hdf5
    via --features auto-pulls mpi exactly as if the [feature:hdf5] section
    were declared in the main fobos.
    """
    with tempfile.TemporaryDirectory() as root:
        _write(
            os.path.join(root, "features.fobos"),
            "[features]\nmpi  = -DUSE_MPI\nhdf5 = -DUSE_HDF5\n\n[feature:hdf5]\nrequires = mpi\n",
        )
        content = (
            "[include]\n"
            "paths = features.fobos\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"features": "hdf5"})
        # hdf5 active, mpi auto-pulled.
        assert "-DUSE_HDF5" in cliargs.cflags
        assert "-DUSE_MPI" in cliargs.cflags


def test_include_varset_selectable_by_cli():
    """An included [varset:NAME] is selectable via --varset on the CLI."""
    with tempfile.TemporaryDirectory() as root:
        _write(
            os.path.join(root, "clusters.fobos"),
            "[varset:leonardo]\n$HDF5_PREFIX = /leonardo/hdf5\n\n[varset:iac]\n$HDF5_PREFIX = /iac/hdf5\n",
        )
        content = (
            "[include]\n"
            "paths = clusters.fobos\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c -I$HDF5_PREFIX/include\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content, {"varset": "leonardo"})
        assert "-I/leonardo/hdf5/include" in cliargs.cflags


def test_include_template_resolved_by_main_mode():
    """An included [template-X] is usable as `template = template-X` in the main mode."""
    with tempfile.TemporaryDirectory() as root:
        _write(
            os.path.join(root, "templates.fobos"),
            "[template-gnu]\ncompiler = gnu\ncflags   = -cpp -c -O3\nlflags   = -O3\n",
        )
        content = (
            "[modes]\n"
            "modes = release\n\n"
            "[include]\n"
            "paths = templates.fobos\n\n"
            "[release]\n"
            "template = template-gnu\n"
            "target   = main.F90\n"
        )
        # Not using _make_fobos's default-mode helper; the test fobos
        # explicitly declares a mode list, so build_profile etc. don't apply.
        path = os.path.join(root, "fobos")
        _write(path, content)
        cliargs = argparse.Namespace(
            fobos=path,
            fobos_case_insensitive=False,
            mode="release",
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
        fobos = Fobos(cliargs=cliargs)
        # Template inheritance kicks in *after* include merge, so cflags
        # from the included template propagate to the active mode.
        assert "-O3" in cliargs.cflags
        # Sanity: the section actually got merged.
        assert fobos.fobos.has_section("template-gnu")


def test_local_overrides_pattern_full():
    """The canonical use case: required base + optional dev-local overrides.

    The main fobos provides project defaults; an optional `?fobos.local` is
    pulled in if present and overrides specific $variables.  When absent
    (CI machines), the build proceeds with project defaults.
    """
    # Case 1: fobos.local is present — its bindings win over [paths] defaults.
    with tempfile.TemporaryDirectory() as root:
        _write(
            os.path.join(root, "fobos.local"),
            "[paths]\n$HDF5_PREFIX = /home/dev/hdf5-custom\n",
        )
        content = (
            "[paths]\n"
            "$HDF5_PREFIX = /opt/hdf5\n\n"
            "[include]\n"
            "paths = ?fobos.local\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c -I$HDF5_PREFIX/include\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        # Note: the include is merged with parent-wins, but since the parent's
        # [paths] $HDF5_PREFIX is *also* in the main fobos, parent wins.
        # → this behaviour matches D5: the file you read top-to-bottom is
        #   authoritative.  For dev-overrides to take effect, put the parent
        #   default in the *included* file, not the main one.
        _fobos, cliargs = _make_fobos(root, content)
        assert "-I/opt/hdf5/include" in cliargs.cflags

    # Case 2: dev-overrides done correctly — defaults live in another included
    # file, with fobos.local as the *last* sibling so it wins per D5.
    with tempfile.TemporaryDirectory() as root:
        _write(
            os.path.join(root, "defaults.fobos"),
            "[paths]\n$HDF5_PREFIX = /opt/hdf5\n",
        )
        _write(
            os.path.join(root, "fobos.local"),
            "[paths]\n$HDF5_PREFIX = /home/dev/hdf5-custom\n",
        )
        content = (
            "[include]\n"
            "paths = defaults.fobos\n"
            "        ?fobos.local\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c -I$HDF5_PREFIX/include\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content)
        # fobos.local is later in the include list → its value wins among siblings.
        assert "-I/home/dev/hdf5-custom/include" in cliargs.cflags

    # Case 3: fobos.local absent → default applies, no error.
    with tempfile.TemporaryDirectory() as root:
        _write(
            os.path.join(root, "defaults.fobos"),
            "[paths]\n$HDF5_PREFIX = /opt/hdf5\n",
        )
        # No fobos.local on disk.
        content = (
            "[include]\n"
            "paths = defaults.fobos\n"
            "        ?fobos.local\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c -I$HDF5_PREFIX/include\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content)
        assert "-I/opt/hdf5/include" in cliargs.cflags


# ── shell-completion regression: --mode picks up modes from includes ────────


class _CompletionCtx:
    """Minimal stand-in for typer.Context — only `params` is consulted."""

    def __init__(self, params: dict) -> None:
        self.params = params


def test_completion_lists_modes_from_includes():
    """Shell completion for --mode must surface modes declared in included files.

    Bug: the completion callback originally called RawConfigParser.read()
    directly, bypassing include resolution.  Modes in included files were
    invisible at the TAB prompt.  Fix: run _resolve_includes before
    extracting the modes list.
    """
    from fobis.cli._completions import _complete_fobos_mode

    with tempfile.TemporaryDirectory() as root:
        # Modes are declared *only* in the included file.
        _write(
            os.path.join(root, "modes.fobos"),
            "[modes]\nmodes = leonardo iac local-dev\n\n"
            "[leonardo]\ntemplate = template-nvf-oac\ntarget = main.F90\n"
            "[iac]\ntemplate = template-nvf-oac\ntarget = main.F90\n"
            "[local-dev]\ntemplate = template-gnu\ntarget = main.F90\n",
        )
        path = os.path.join(root, "fobos")
        _write(
            path,
            "[include]\npaths = modes.fobos\n",
        )
        ctx = _CompletionCtx({"fobos": path, "fobos_case_insensitive": False})
        completions = _complete_fobos_mode(ctx, "")
        assert set(completions) == {"leonardo", "iac", "local-dev"}
        # Prefix filtering still works on the include-merged list.
        assert _complete_fobos_mode(ctx, "le") == ["leonardo"]


def test_completion_merges_main_and_included_modes_via_sections():
    """Without [modes], completion falls back to scanning sections from the merged parser."""
    from fobis.cli._completions import _complete_fobos_mode

    with tempfile.TemporaryDirectory() as root:
        _write(
            os.path.join(root, "external.fobos"),
            "[external-mode]\ntemplate = template-gnu\ntarget = ext.F90\n",
        )
        path = os.path.join(root, "fobos")
        _write(
            path,
            "[include]\npaths = external.fobos\n\n[main-mode]\ntemplate = template-gnu\ntarget = main.F90\n",
        )
        ctx = _CompletionCtx({"fobos": path, "fobos_case_insensitive": False})
        completions = set(_complete_fobos_mode(ctx, ""))
        assert "main-mode" in completions
        assert "external-mode" in completions


def test_completion_filters_non_mode_sections_from_includes():
    """Sections like [feature:X] / [varset:X] from includes must not be offered as modes."""
    from fobis.cli._completions import _complete_fobos_mode

    with tempfile.TemporaryDirectory() as root:
        _write(
            os.path.join(root, "shared.fobos"),
            "[features]\nmpi = -DUSE_MPI\n\n"
            "[feature:hdf5]\nrequires = mpi\n\n"
            "[varset:leonardo]\n$HDF5_PREFIX = /leonardo/hdf5\n\n"
            "[shared-mode]\ntemplate = template-gnu\ntarget = s.F90\n",
        )
        path = os.path.join(root, "fobos")
        _write(path, "[include]\npaths = shared.fobos\n")
        ctx = _CompletionCtx({"fobos": path, "fobos_case_insensitive": False})
        completions = set(_complete_fobos_mode(ctx, ""))
        # Only the actual mode should be offered.
        assert completions == {"shared-mode"}


def test_completion_swallows_broken_include():
    """Best-effort completion: a missing required include must not crash."""
    from fobis.cli._completions import _complete_fobos_mode

    with tempfile.TemporaryDirectory() as root:
        path = os.path.join(root, "fobos")
        _write(
            path,
            "[include]\npaths = does-not-exist.fobos\n\n[main-mode]\ntemplate = template-gnu\ntarget = main.F90\n",
        )
        ctx = _CompletionCtx({"fobos": path, "fobos_case_insensitive": False})
        # Should NOT raise SystemExit even though the include is broken;
        # whatever was loaded from the main file is offered as fallback.
        completions = set(_complete_fobos_mode(ctx, ""))
        assert "main-mode" in completions


# ── shell-completion: --features ─────────────────────────────────────────────


def test_completion_features_from_main_and_includes():
    """--features completes from [features] in main file AND included files."""
    from fobis.cli._completions import _complete_fobos_feature

    with tempfile.TemporaryDirectory() as root:
        _write(
            os.path.join(root, "shared.fobos"),
            "[features]\nshared-feat = -DSHARED\n\n[feature:hdf5]\nflags = -DUSE_HDF5\n",
        )
        path = os.path.join(root, "fobos")
        _write(
            path,
            "[include]\npaths = shared.fobos\n\n[features]\nlocal-feat = -DLOCAL\n",
        )
        ctx = _CompletionCtx({"fobos": path, "fobos_case_insensitive": False})
        completions = set(_complete_fobos_feature(ctx, ""))
        assert "shared-feat" in completions
        assert "local-feat" in completions
        assert "hdf5" in completions  # [feature:hdf5] sibling section
        # Implicit feature names are always offered.
        assert "openmp" in completions
        assert "mpi" in completions
        # The reserved "default" key inside [features] is NOT a feature name.
        assert "default" not in completions


def test_completion_features_csv_preserves_earlier_tokens():
    """Comma-separated input: completion preserves earlier tokens.

    Typing `--features mpi,hd<TAB>` should suggest `mpi,hdf5` so the shell
    keeps the leading `mpi,` intact.
    """
    from fobis.cli._completions import _complete_fobos_feature

    with tempfile.TemporaryDirectory() as root:
        _write(
            os.path.join(root, "fobos"),
            "[features]\nhdf5 = -DUSE_HDF5\nmpi = -DUSE_MPI\n",
        )
        ctx = _CompletionCtx({"fobos": os.path.join(root, "fobos"), "fobos_case_insensitive": False})
        completions = _complete_fobos_feature(ctx, "mpi,hd")
        assert "mpi,hdf5" in completions
        # Must NOT offer the bare "hdf5" — that would replace the user's "mpi,".
        assert "hdf5" not in completions


def test_completion_features_prefix_filters_last_token_only():
    """When typing `mpi,hdf5,c<TAB>`, only candidates starting with `c` qualify."""
    from fobis.cli._completions import _complete_fobos_feature

    with tempfile.TemporaryDirectory() as root:
        _write(
            os.path.join(root, "fobos"),
            "[features]\nhdf5 = -DUSE_HDF5\nmpi = -DUSE_MPI\ncoverage-feat = -DCOV\n",
        )
        ctx = _CompletionCtx({"fobos": os.path.join(root, "fobos"), "fobos_case_insensitive": False})
        completions = _complete_fobos_feature(ctx, "mpi,hdf5,c")
        offered_last = {c.split(",")[-1] for c in completions}
        # Candidates whose name starts with 'c': the explicit 'coverage-feat'
        # plus the implicit 'coarray' and 'coverage'.
        assert "coverage-feat" in offered_last
        assert "coarray" in offered_last
        assert "coverage" in offered_last
        # Already-listed prefix tokens that don't start with 'c' are not offered.
        assert "mpi" not in offered_last
        assert "hdf5" not in offered_last


# ── shell-completion: --varset ───────────────────────────────────────────────


def test_completion_varset_from_main_and_includes():
    """--varset completes from [varset:NAME] in main file and includes."""
    from fobis.cli._completions import _complete_fobos_varset

    with tempfile.TemporaryDirectory() as root:
        _write(
            os.path.join(root, "clusters.fobos"),
            "[varset:leonardo]\n$HDF5_PREFIX = /leonardo/hdf5\n\n[varset:iac]\n$HDF5_PREFIX = /iac/hdf5\n",
        )
        path = os.path.join(root, "fobos")
        _write(
            path,
            "[include]\npaths = clusters.fobos\n\n[varset:local]\n$HDF5_PREFIX = /opt/hdf5\n",
        )
        ctx = _CompletionCtx({"fobos": path, "fobos_case_insensitive": False})
        completions = set(_complete_fobos_varset(ctx, ""))
        assert completions == {"leonardo", "iac", "local"}


def test_completion_varset_csv_preserves_earlier():
    """--varset accepts multiple values; CSV completion preserves prefix."""
    from fobis.cli._completions import _complete_fobos_varset

    with tempfile.TemporaryDirectory() as root:
        _write(
            os.path.join(root, "fobos"),
            "[varset:leonardo]\n$X = a\n\n[varset:cuda-cc89]\n$X = b\n",
        )
        ctx = _CompletionCtx({"fobos": os.path.join(root, "fobos"), "fobos_case_insensitive": False})
        completions = _complete_fobos_varset(ctx, "leonardo,cu")
        assert "leonardo,cuda-cc89" in completions


# ── shell-completion: --execute / --pre-build / --post-build ─────────────────


def test_completion_rule_from_main_and_includes():
    """Rule names from [rule-NAME] sections complete (used by --execute and pre/post)."""
    from fobis.cli._completions import _complete_fobos_rule

    with tempfile.TemporaryDirectory() as root:
        _write(
            os.path.join(root, "rules.fobos"),
            "[rule-shared-rule]\nrule = echo shared\n",
        )
        path = os.path.join(root, "fobos")
        _write(
            path,
            "[include]\npaths = rules.fobos\n\n[rule-local-rule]\nrule = echo local\n",
        )
        ctx = _CompletionCtx({"fobos": path, "fobos_case_insensitive": False})
        completions = set(_complete_fobos_rule(ctx, ""))
        assert completions == {"shared-rule", "local-rule"}


def test_completion_rule_prefix_filter():
    """Rule completion supports prefix filtering."""
    from fobis.cli._completions import _complete_fobos_rule

    with tempfile.TemporaryDirectory() as root:
        _write(
            os.path.join(root, "fobos"),
            "[rule-build]\nrule = make\n[rule-clean]\nrule = rm\n",
        )
        ctx = _CompletionCtx({"fobos": os.path.join(root, "fobos"), "fobos_case_insensitive": False})
        assert _complete_fobos_rule(ctx, "bu") == ["build"]


# ── shell-completion: --target-filter ────────────────────────────────────────


def test_completion_target_from_target_sections():
    """--target-filter completes from [target.NAME] sections."""
    from fobis.cli._completions import _complete_fobos_target

    with tempfile.TemporaryDirectory() as root:
        _write(
            os.path.join(root, "fobos"),
            "[target.solver]\ntarget = solver.F90\n[target.viewer]\ntarget = viewer.F90\n",
        )
        ctx = _CompletionCtx({"fobos": os.path.join(root, "fobos"), "fobos_case_insensitive": False})
        completions = set(_complete_fobos_target(ctx, ""))
        assert completions == {"solver", "viewer"}


# ── shell-completion: --build-profile (static enum) ──────────────────────────


def test_completion_build_profile_static():
    """--build-profile offers the four built-in profile names."""
    from fobis.cli._completions import _complete_build_profile

    completions = set(_complete_build_profile(""))
    assert completions == {"debug", "release", "asan", "coverage"}
    assert _complete_build_profile("co") == ["coverage"]


# ── list-merge semantics for [modes] / [features] / [varsets] defaults ──────


def test_modes_list_unions_across_includes():
    """[modes] modes = ... is token-merged across includes (parent + every include).

    Before this rule, parent-wins on [modes]/modes meant an included file's
    modes were silently shadowed: `--mode prism-X` (defined in include)
    would error as "not defined in fobos".  This is the regression test
    for that bug, reported on the adam fobos.
    """
    with tempfile.TemporaryDirectory() as root:
        _write(
            os.path.join(root, "fobos_prism"),
            "[modes]\n"
            "modes = prism-fnl-nvf prism-fnl-nvf-debug\n\n"
            "[prism-fnl-nvf]\ntemplate = template-nvf\ntarget = prism.F90\n\n"
            "[prism-fnl-nvf-debug]\ntemplate = template-nvf\ntarget = prism.F90\n\n"
            "[template-nvf]\ncompiler = nvfortran\ncflags = -cpp -c\n",
        )
        path = os.path.join(root, "fobos")
        _write(
            path,
            "[include]\npaths = fobos_prism\n\n"
            "[modes]\nmodes = adam-com-gnu nasto-cpu-gnu\n\n"
            "[adam-com-gnu]\ntemplate = template-nvf\ntarget = adam.F90\n\n"
            "[nasto-cpu-gnu]\ntemplate = template-nvf\ntarget = nasto.F90\n",
        )
        # Build prism-fnl-nvf from the included file — the substring/list
        # merge bug would surface here as "mode not defined".
        cliargs = argparse.Namespace(
            fobos=path,
            fobos_case_insensitive=False,
            mode="prism-fnl-nvf",
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
        # Should NOT raise SystemExit — prism-fnl-nvf is in the merged modes list.
        fobos = Fobos(cliargs=cliargs)
        # Verify the merged modes string is the union, not just one side.
        merged = fobos.fobos.get("modes", "modes").split()
        assert "prism-fnl-nvf" in merged
        assert "prism-fnl-nvf-debug" in merged
        assert "adam-com-gnu" in merged
        assert "nasto-cpu-gnu" in merged


def test_modes_list_token_match_not_substring():
    """`--mode prism` must NOT silently match `prism-fnl-nvf` via substring.

    Pre-existing bug in _check_mode: substring `in` lookup let a typo or
    truncated mode name pick the wrong mode.  This test pins the
    token-level match.
    """
    import pytest

    with tempfile.TemporaryDirectory() as root:
        path = os.path.join(root, "fobos")
        _write(
            path,
            "[modes]\nmodes = prism-fnl-nvf prism-fnl-nvf-debug\n\n"
            "[prism-fnl-nvf]\ntemplate = template-x\ntarget = prism.F90\n\n"
            "[prism-fnl-nvf-debug]\ntemplate = template-x\ntarget = prism.F90\n\n"
            "[template-x]\ncompiler = nvfortran\ncflags = -cpp -c\n",
        )
        cliargs = argparse.Namespace(
            fobos=path,
            fobos_case_insensitive=False,
            mode="prism",  # truncated — substring match would accept; token match must reject.
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
        with pytest.raises(SystemExit):
            Fobos(cliargs=cliargs, print_w=lambda m: None)


def test_features_default_unions_across_includes():
    """[features] default = ... merges as a token-union across includes."""
    with tempfile.TemporaryDirectory() as root:
        _write(
            os.path.join(root, "shared.fobos"),
            "[features]\ndefault = mpi\nmpi = -DUSE_MPI\nhdf5 = -DUSE_HDF5\n",
        )
        content = (
            "[include]\npaths = shared.fobos\n\n"
            "[features]\ndefault = hdf5\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content)
        # Both 'mpi' (from include) and 'hdf5' (from main) are activated as defaults.
        assert "-DUSE_MPI" in cliargs.cflags
        assert "-DUSE_HDF5" in cliargs.cflags


def test_varsets_default_unions_across_includes():
    """[varsets] default = ... merges as a token-union across includes."""
    with tempfile.TemporaryDirectory() as root:
        _write(
            os.path.join(root, "shared.fobos"),
            "[varsets]\ndefault = base\n\n[varset:base]\n$BASE = base-val\n",
        )
        content = (
            "[include]\npaths = shared.fobos\n\n"
            "[varsets]\ndefault = override\n\n"
            "[varset:override]\n$EXTRA = override-val\n\n"
            "[default]\n"
            "compiler = Gnu\n"
            "cflags   = -c -I$BASE -I$EXTRA\n"
            "lflags   =\n"
            "build_profile =\n"
        )
        _fobos, cliargs = _make_fobos(root, content)
        # Both default varsets apply (token-union).
        assert "-Ibase-val" in cliargs.cflags
        assert "-Ioverride-val" in cliargs.cflags
