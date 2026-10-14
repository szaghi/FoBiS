"""Tests for fobis.Profiles — named build profiles (issue #176)."""

from __future__ import annotations

import pytest

from fobis.Profiles import PROFILES, get_profile_flags, list_profiles

# ── Positive lookup ──────────────────────────────────────────────────────────


def test_get_profile_gnu_debug():
    flags = get_profile_flags("gnu", "debug")
    assert "-fcheck=all" in flags["cflags"]
    assert "-fbacktrace" in flags["cflags"]
    assert "-O0" in flags["cflags"]


def test_get_profile_gnu_release():
    flags = get_profile_flags("gnu", "release")
    assert "-O3" in flags["cflags"]


def test_get_profile_gnu_asan():
    flags = get_profile_flags("gnu", "asan")
    assert "-fsanitize=address,undefined" in flags["cflags"]
    assert "-fsanitize=address,undefined" in flags["lflags"]


def test_get_profile_gnu_coverage():
    flags = get_profile_flags("gnu", "coverage")
    assert "--coverage" in flags["cflags"]
    assert "--coverage" in flags["lflags"]


def test_get_profile_intel_debug():
    flags = get_profile_flags("intel", "debug")
    assert "-check all" in flags["cflags"]
    assert "-traceback" in flags["cflags"]


def test_get_profile_intel_release():
    flags = get_profile_flags("intel", "release")
    assert "-O3" in flags["cflags"]


def test_get_profile_case_insensitive():
    flags_lower = get_profile_flags("gnu", "debug")
    flags_upper = get_profile_flags("GNU", "Debug")
    assert flags_lower == flags_upper


# ── Fallback behaviour ───────────────────────────────────────────────────────


def test_get_profile_unknown_compiler_falls_back():
    """Unknown compiler with a known profile → gnu flags + warning."""
    warnings = []
    flags = get_profile_flags("xlf", "debug", print_w=warnings.append)
    # Warning must mention the unknown compiler and fallback
    assert any("xlf" in w or "falling back" in w.lower() for w in warnings)
    # Still returns usable flags (gnu/debug)
    assert "-fcheck=all" in flags["cflags"]


def test_get_profile_unknown_profile_returns_empty():
    """Known compiler, unknown profile → empty flags + warning."""
    warnings = []
    flags = get_profile_flags("gnu", "bogus", print_w=warnings.append)
    assert any("bogus" in w for w in warnings)
    assert flags["cflags"] == ""
    assert flags["lflags"] == ""


def test_get_profile_empty_profile_returns_empty():
    """Empty profile string → empty flags, no warning."""
    flags = get_profile_flags("gnu", "")
    assert flags == {"cflags": "", "lflags": ""}


def test_get_profile_none_profile_returns_empty():
    """None profile → empty flags."""
    flags = get_profile_flags("gnu", None)
    assert flags == {"cflags": "", "lflags": ""}


# ── list_profiles() ──────────────────────────────────────────────────────────


def test_list_profiles_output():
    output = list_profiles()
    assert "gnu" in output
    assert "debug" in output
    assert "intel" in output
    assert "release" in output
    # Should show at least gnu/debug and intel/release
    assert "gnu" in output and "intel" in output


def test_get_profile_of_another_family_never_gets_gfortran_flags():
    """nvfortran has no asan profile (it rejects -fsanitize=address): no flags, not gfortran's -fsanitize."""
    warnings = []
    flags = get_profile_flags("nvfortran", "asan", print_w=warnings.append)
    assert flags == {"cflags": "", "lflags": ""} and "no 'asan' profile" in warnings[0]


# ── every profile flag is accepted by its compiler ───────────────────────────

_COMMANDS = {
    "gnu": "gfortran",
    "intel": "ifort",
    "intel_nextgen": "ifx",
    "nvfortran": "nvfortran",
    "nag": "nagfor",
    "amd": "flang",
    "lfortran": "lfortran",
}
_REFUSED = ("unknown switch", "not supported", "ignoring unknown option", "unrecognized", "unknown argument")


@pytest.mark.parametrize("key", sorted(PROFILES), ids=lambda k: f"{k[0]}-{k[1]}")
def test_profile_flags_are_accepted_by_the_compiler(key, tmp_path):
    """A profile flag the compiler rejects breaks the build; one it ignores builds silently without the profile
    (ifort and -fsanitize=address). Checked with every compiler on PATH: load the toolchains (module load
    nvhpc, oneapi vars.sh) to check them all."""
    import shutil
    import subprocess

    compiler, _ = key
    command = shutil.which(_COMMANDS[compiler])
    if command is None:
        pytest.skip(f"{_COMMANDS[compiler]} not on PATH")
    (tmp_path / "p.f90").write_text("program p\nprint *, 1\nend program\n")
    flags = PROFILES[key]
    result = subprocess.run(
        [command, *flags["cflags"].split(), "p.f90", *flags["lflags"].split(), "-o", "p"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0 and not any(r in output.lower() for r in _REFUSED), output
