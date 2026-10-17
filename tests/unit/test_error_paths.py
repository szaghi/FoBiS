"""Error-path integration tests for FoBiS.py — no Fortran compiler needed."""

import argparse

import pytest

from fobis.fobis import run_fobis
from fobis.Fobos import Fobos

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def _ns(fobos_path, mode=None):
    return argparse.Namespace(
        fobos=str(fobos_path),
        fobos_case_insensitive=False,
        mode=mode,
    )


# ---------------------------------------------------------------------------
# Error path 1: invalid mode in a valid fobos file → SystemExit
# ---------------------------------------------------------------------------


def test_invalid_mode_exits(tmp_path):
    """Requesting a non-existent mode exits 1 (the listing of the modes exited 0 before the error's exit)."""
    _write(tmp_path, "fobos", "[modes]\nmodes = gnu\n[gnu]\ncompiler = gnu\n")
    with pytest.raises(SystemExit) as exc:
        Fobos(cliargs=_ns(tmp_path / "fobos", mode="typo_mode"))
    assert exc.value.code == 1


# ---------------------------------------------------------------------------
# Error path 2: fobis rule with unknown execute name → SystemExit
# ---------------------------------------------------------------------------


def test_unknown_rule_exits(tmp_path, monkeypatch):
    """Executing an undefined rule name exits 1."""
    _write(
        tmp_path,
        "fobos",
        "[default]\n[rules]\n[myrule]\nexecute = echo hello\n",
    )
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        run_fobis(fake_args=["rule", "-f", "fobos", "-ex", "nonexistent_rule_xyz"])
    assert exc.value.code == 1


# ---------------------------------------------------------------------------
# Error path 3: fobis build with --mode for a mode not in fobos → SystemExit
# ---------------------------------------------------------------------------


def test_build_bad_mode_exits(tmp_path, monkeypatch):
    """fobis build with an invalid --mode exits 1."""
    _write(
        tmp_path,
        "fobos",
        "[modes]\nmodes = gnu\n[gnu]\ncompiler = gnu\nsrc = .\n",
    )
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        run_fobis(fake_args=["build", "-f", "fobos", "--mode", "bad_mode"])
    assert exc.value.code == 1


# ---------------------------------------------------------------------------
# Error path 4: fobis build with --lmodes prints modes then exits
# ---------------------------------------------------------------------------


def test_list_modes_exits(tmp_path, monkeypatch):
    """--lmodes prints available modes then exits 0."""
    _write(
        tmp_path,
        "fobos",
        "[modes]\nmodes = gnu intel\n[gnu]\ncompiler = gnu\n[intel]\ncompiler = intel\n",
    )
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        run_fobis(fake_args=["build", "-f", "fobos", "--lmodes"])
    assert exc.value.code == 0


def test_a_quiet_rule_hides_its_own_commands_only(tmp_path, monkeypatch, capsys):
    """rule --list: a rule's quiet key used to hide the commands of every rule listed after it."""
    _write(tmp_path, "fobos", "[rule-silent]\nquiet = True\nrule = echo hidden\n\n[rule-loud]\nrule = echo shown\n")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc:
        run_fobis(fake_args=["rule", "--list"])
    out = capsys.readouterr()
    assert exc.value.code == 0
    assert "echo hidden" not in out.out + out.err and "Command => echo shown" in out.out + out.err


# ---------------------------------------------------------------------------
# Error path 5: missing template reference → SystemExit
# ---------------------------------------------------------------------------


def test_missing_template_reference_exits(tmp_path):
    """A template= pointing to a non-existent section causes SystemExit."""
    _write(
        tmp_path,
        "fobos",
        "[modes]\nmodes = mymode\n[mymode]\ntemplate = ghost_template\n",
    )
    with pytest.raises(SystemExit):
        Fobos(cliargs=_ns(tmp_path / "fobos", mode="mymode"))


# ---------------------------------------------------------------------------
# Error path 6: circular template reference → SystemExit
# ---------------------------------------------------------------------------


def test_circular_template_exits(tmp_path):
    """Mutually referencing templates cause SystemExit."""
    _write(
        tmp_path,
        "fobos",
        "[modes]\nmodes = a\n[a]\ntemplate = b\n[b]\ntemplate = a\n",
    )
    with pytest.raises(SystemExit):
        Fobos(cliargs=_ns(tmp_path / "fobos", mode="a"))
