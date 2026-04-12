"""Tests for fobis.Profiles — named build profiles (issue #176)."""

from __future__ import annotations

from fobis.Profiles import get_profile_flags, list_profiles

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
