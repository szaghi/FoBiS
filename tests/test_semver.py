"""Tests for fobis.SemVer — version constraint resolution (issue #171)."""

from __future__ import annotations

import pytest

from fobis.SemVer import Version, parse_constraint, resolve, satisfies


# ── Version parsing ──────────────────────────────────────────────────────────


def test_version_parses_xyz():
    v = Version("1.5.3")
    assert (v.major, v.minor, v.patch) == (1, 5, 3)


def test_version_parses_with_v_prefix():
    v = Version("v1.5.3")
    assert (v.major, v.minor, v.patch) == (1, 5, 3)


def test_version_parses_major_only():
    v = Version("2")
    assert (v.major, v.minor, v.patch) == (2, 0, 0)


def test_version_parses_major_minor():
    v = Version("1.5")
    assert (v.major, v.minor, v.patch) == (1, 5, 0)


def test_version_ordering():
    assert Version("1.4.0") < Version("1.5.0")
    assert Version("1.5.0") < Version("1.5.3")
    assert Version("1.5.3") < Version("2.0.0")
    assert Version("2.0.0") > Version("1.9.9")


def test_version_equality():
    assert Version("1.5.0") == Version("v1.5.0")


def test_version_invalid_raises():
    with pytest.raises(ValueError):
        Version("not-a-version")


# ── Caret constraints ────────────────────────────────────────────────────────


def test_parse_caret_major_minor():
    """^1.5 → >=1.5.0, <2.0.0"""
    preds = parse_constraint("^1.5")
    assert satisfies(Version("1.5.0"), preds)
    assert satisfies(Version("1.9.9"), preds)
    assert not satisfies(Version("2.0.0"), preds)
    assert not satisfies(Version("1.4.9"), preds)


def test_parse_caret_patch():
    """^1.5.2 → >=1.5.2, <2.0.0"""
    preds = parse_constraint("^1.5.2")
    assert not satisfies(Version("1.5.1"), preds)
    assert satisfies(Version("1.5.2"), preds)
    assert satisfies(Version("1.9.0"), preds)
    assert not satisfies(Version("2.0.0"), preds)


def test_parse_tilde():
    """~1.5.2 → >=1.5.2, <1.6.0"""
    preds = parse_constraint("~1.5.2")
    assert not satisfies(Version("1.5.1"), preds)
    assert satisfies(Version("1.5.2"), preds)
    assert satisfies(Version("1.5.9"), preds)
    assert not satisfies(Version("1.6.0"), preds)


# ── Range constraints ────────────────────────────────────────────────────────


def test_parse_explicit_range():
    """>=1.0,<2.0 boundary conditions."""
    preds = parse_constraint(">=1.0,<2.0")
    assert satisfies(Version("1.0.0"), preds)
    assert satisfies(Version("1.9.9"), preds)
    assert not satisfies(Version("0.9.9"), preds)
    assert not satisfies(Version("2.0.0"), preds)


def test_parse_greater_equal():
    preds = parse_constraint(">=2.0")
    assert satisfies(Version("2.0.0"), preds)
    assert satisfies(Version("3.1.0"), preds)
    assert not satisfies(Version("1.9.9"), preds)


def test_parse_less_than():
    preds = parse_constraint("<2.0")
    assert satisfies(Version("1.9.9"), preds)
    assert not satisfies(Version("2.0.0"), preds)


def test_parse_less_equal():
    preds = parse_constraint("<=2.0")
    assert satisfies(Version("2.0.0"), preds)
    assert not satisfies(Version("2.0.1"), preds)


def test_parse_greater_than():
    preds = parse_constraint(">1.5")
    assert satisfies(Version("1.5.1"), preds)
    assert not satisfies(Version("1.5.0"), preds)


# ── Exact and wildcard ───────────────────────────────────────────────────────


def test_parse_exact():
    """=1.5.0 — only 1.5.0 passes."""
    preds = parse_constraint("=1.5.0")
    assert satisfies(Version("1.5.0"), preds)
    assert not satisfies(Version("1.5.1"), preds)
    assert not satisfies(Version("1.4.9"), preds)


def test_parse_wildcard():
    """* — any version passes."""
    preds = parse_constraint("*")
    assert satisfies(Version("0.0.1"), preds)
    assert satisfies(Version("99.99.99"), preds)


# ── resolve() ───────────────────────────────────────────────────────────────


def test_resolve_selects_highest():
    tags = ["v1.4.0", "v1.5.0", "v1.5.3", "v2.0.0"]
    # ^1.5 → >=1.5.0, <2.0.0 — highest is v1.5.3
    assert resolve(tags, "^1.5") == "v1.5.3"


def test_resolve_no_match_returns_none():
    tags = ["v1.4.0", "v1.5.0"]
    assert resolve(tags, "^2.0") is None


def test_resolve_ignores_non_semver_tags():
    tags = ["latest", "nightly", "v1.5.0", "rc-build"]
    # Non-semver tags must be silently skipped
    result = resolve(tags, "^1.5")
    assert result == "v1.5.0"


def test_resolve_strips_v_prefix():
    tags = ["v1.5.0", "1.5.0"]
    # Both should parse correctly; highest wins
    result = resolve(tags, "=1.5.0")
    assert result in ("v1.5.0", "1.5.0")


def test_resolve_empty_tags_returns_none():
    assert resolve([], "^1.0") is None


def test_resolve_wildcard_returns_highest():
    tags = ["v1.0.0", "v2.0.0", "v1.5.0"]
    assert resolve(tags, "*") == "v2.0.0"


def test_resolve_exact_match():
    tags = ["v1.4.0", "v1.5.0", "v1.6.0"]
    assert resolve(tags, "=1.5.0") == "v1.5.0"
