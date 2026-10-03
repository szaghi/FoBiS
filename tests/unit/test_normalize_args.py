"""Tests for the normaliser of the legacy command line options."""

from fobis.cli_parser import _normalize_args


def test_legacy_options_are_translated():
    """Legacy single-dash long options become double-dash ones, with hyphens."""
    assert _normalize_args(["build", "-mode", "gnu", "-build_dir", "exe"]) == [
        "build",
        "--mode",
        "gnu",
        "--build-dir",
        "exe",
    ]


def test_double_dash_underscores_are_translated():
    """Underscores of double-dash options become hyphens, the value after = is kept."""
    assert _normalize_args(["--exclude_from_doctests", "a_b.F90", "--build_dir=my_dir"]) == [
        "--exclude-from-doctests",
        "a_b.F90",
        "--build-dir=my_dir",
    ]


def test_values_starting_with_a_dash_are_kept():
    """A value that looks like a legacy option, but is not an option, is left unchanged."""
    args = ["build", "--preproc", "-DPENF_R16P", "--cflags", "-O2", "--lflags", "-fopenmp"]
    assert _normalize_args(args) == args


def test_short_options_and_numbers_are_kept():
    """Single-char options and negative numbers are left unchanged."""
    args = ["build", "-f", "fobos", "-j", "-1"]
    assert _normalize_args(args) == args
