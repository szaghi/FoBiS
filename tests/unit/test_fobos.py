"""Unit tests for fobis.Fobos — uses tmp_path, no compiler needed."""

import argparse

import pytest

from fobis.Fobos import Fobos


def _ns(fobos_path, mode=None, fobos_case_insensitive=False):
    """Build a minimal cliargs namespace for Fobos construction."""
    return argparse.Namespace(
        fobos=str(fobos_path),
        fobos_case_insensitive=fobos_case_insensitive,
        mode=mode,
    )


def _write_fobos(tmp_path, content):
    """Write fobos INI content and return the file path."""
    p = tmp_path / "fobos"
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Basic construction
# ---------------------------------------------------------------------------


def test_fobos_none_when_file_missing(tmp_path):
    """Fobos.fobos stays None when the file does not exist."""
    ns = _ns(tmp_path / "nonexistent.fobos")
    fobos = Fobos(cliargs=ns)
    assert fobos.fobos is None


def test_fobos_loaded_when_file_exists(tmp_path):
    """Fobos.fobos is set when the file exists."""
    _write_fobos(tmp_path, "[default]\ncompiler = gnu\n")
    fobos = Fobos(cliargs=_ns(tmp_path / "fobos"))
    assert fobos.fobos is not None


# ---------------------------------------------------------------------------
# Mode selection
# ---------------------------------------------------------------------------


def test_default_section_used_when_no_modes(tmp_path):
    """[default] section is selected when no [modes] section is present."""
    _write_fobos(tmp_path, "[default]\ncompiler = intel\n")
    fobos = Fobos(cliargs=_ns(tmp_path / "fobos"))
    assert fobos.mode == "default"


def test_first_mode_selected_automatically(tmp_path):
    """First mode listed in [modes] is auto-selected when mode=None."""
    content = "[modes]\nmodes = gnu intel\n[gnu]\ncompiler = gnu\n[intel]\ncompiler = intel\n"
    _write_fobos(tmp_path, content)
    fobos = Fobos(cliargs=_ns(tmp_path / "fobos"))
    assert fobos.mode == "gnu"


def test_explicit_mode_selection(tmp_path):
    """Explicitly named mode is selected when mode= is set."""
    content = "[modes]\nmodes = gnu intel\n[gnu]\ncompiler = gnu\n[intel]\ncompiler = intel\n"
    _write_fobos(tmp_path, content)
    fobos = Fobos(cliargs=_ns(tmp_path / "fobos", mode="intel"))
    assert fobos.mode == "intel"


def test_invalid_mode_raises_system_exit(tmp_path):
    """Unknown mode name causes SystemExit."""
    content = "[modes]\nmodes = gnu\n[gnu]\ncompiler = gnu\n"
    _write_fobos(tmp_path, content)
    with pytest.raises(SystemExit):
        Fobos(cliargs=_ns(tmp_path / "fobos", mode="nonexistent"))


# ---------------------------------------------------------------------------
# Template inheritance
# ---------------------------------------------------------------------------


def test_template_option_inherited(tmp_path):
    """Options from a template section are applied to a mode that uses it."""
    content = "[modes]\nmodes = debug\n[base]\ncompiler = gnu\n[debug]\ntemplate = base\n"
    _write_fobos(tmp_path, content)
    fobos = Fobos(cliargs=_ns(tmp_path / "fobos", mode="debug"))
    # The template's compiler option should be merged into debug
    assert fobos.fobos.get("debug", "compiler") == "gnu"


def test_mode_option_overrides_template(tmp_path):
    """Mode-specific option wins over the template value."""
    content = "[modes]\nmodes = debug\n[base]\ncompiler = gnu\n[debug]\ntemplate = base\ncompiler = intel\n"
    _write_fobos(tmp_path, content)
    fobos = Fobos(cliargs=_ns(tmp_path / "fobos", mode="debug"))
    assert fobos.fobos.get("debug", "compiler") == "intel"


def test_circular_template_raises_system_exit(tmp_path):
    """Circular template reference causes SystemExit."""
    content = "[modes]\nmodes = a\n[a]\ntemplate = b\n[b]\ntemplate = a\n"
    _write_fobos(tmp_path, content)
    with pytest.raises(SystemExit):
        Fobos(cliargs=_ns(tmp_path / "fobos", mode="a"))


def test_missing_template_raises_system_exit(tmp_path):
    """Reference to a non-existent template causes SystemExit."""
    content = "[modes]\nmodes = a\n[a]\ntemplate = ghost\n"
    _write_fobos(tmp_path, content)
    with pytest.raises(SystemExit):
        Fobos(cliargs=_ns(tmp_path / "fobos", mode="a"))


# ---------------------------------------------------------------------------
# Local variable substitution
# ---------------------------------------------------------------------------


def test_local_variable_substituted(tmp_path):
    """$var references in option values are substituted with their definitions."""
    content = "[default]\n$mydir = /some/path\nbuild_dir = $mydir/build\n"
    _write_fobos(tmp_path, content)
    fobos = Fobos(cliargs=_ns(tmp_path / "fobos"))
    assert fobos.fobos.get("default", "build_dir") == "/some/path/build"


# ---------------------------------------------------------------------------
# get() method
# ---------------------------------------------------------------------------


def test_get_returns_option_value(tmp_path):
    """get() returns the value for an existing option."""
    _write_fobos(tmp_path, "[default]\ncompiler = gnu\n")
    fobos = Fobos(cliargs=_ns(tmp_path / "fobos"))
    value = fobos.get(option="compiler", toprint=False)
    assert value == "gnu"


def test_get_returns_empty_for_missing_option(tmp_path):
    """get() returns '' for an option not in the fobos file."""
    _write_fobos(tmp_path, "[default]\ncompiler = gnu\n")
    fobos = Fobos(cliargs=_ns(tmp_path / "fobos"))
    value = fobos.get(option="nonexistent_option", toprint=False)
    assert value == ""


def test_get_returns_empty_when_no_fobos(tmp_path):
    """get() returns '' gracefully when no fobos file is loaded."""
    fobos = Fobos(cliargs=_ns(tmp_path / "nonexistent"))
    value = fobos.get(option="compiler", toprint=False)
    assert value == ""


# ---------------------------------------------------------------------------
# [project] section
# ---------------------------------------------------------------------------


def test_get_project_info_full(tmp_path):
    """get_project_info() parses all fields from [project]."""
    content = (
        "[default]\n[project]\nname = MyProject\nversion = 1.2.3\nauthors = Alice\n    Bob\nsummary = A test project\n"
    )
    _write_fobos(tmp_path, content)
    fobos = Fobos(cliargs=_ns(tmp_path / "fobos"))
    info = fobos.get_project_info()
    assert info["name"] == "MyProject"
    assert info["version"] == "1.2.3"
    assert "Alice" in info["authors"]
    assert "Bob" in info["authors"]
    assert info["summary"] == "A test project"


def test_get_project_info_empty_when_no_section(tmp_path):
    """get_project_info() returns defaults when [project] is absent."""
    _write_fobos(tmp_path, "[default]\ncompiler = gnu\n")
    fobos = Fobos(cliargs=_ns(tmp_path / "fobos"))
    info = fobos.get_project_info()
    assert info["name"] == ""
    assert info["authors"] == []
    assert info["version"] == ""


# ---------------------------------------------------------------------------
# Case insensitivity flag
# ---------------------------------------------------------------------------


def test_case_insensitive_option(tmp_path):
    """With fobos_case_insensitive=True options are lowercased by configparser."""
    _write_fobos(tmp_path, "[default]\nCompiler = gnu\n")
    ns = _ns(tmp_path / "fobos", fobos_case_insensitive=True)
    fobos = Fobos(cliargs=ns)
    # configparser default behaviour lowercases keys
    assert fobos.fobos.has_option("default", "compiler")
