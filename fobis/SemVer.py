"""
SemVer.py — Lightweight semantic version constraint resolver.

Implements issue #171: parse and evaluate Cargo-compatible semver constraint
expressions against a list of Git tags, returning the highest satisfying tag.

Only stdlib — no external semver library required.
"""

from __future__ import annotations

import re
from collections.abc import Callable

# ---------------------------------------------------------------------------
# Version triple
# ---------------------------------------------------------------------------


class Version:
    """Parsed semantic version triple (major.minor.patch)."""

    def __init__(self, s: str) -> None:
        """
        Parameters
        ----------
        s : str
            Version string, with or without a leading 'v' prefix.
            Accepts X, X.Y, or X.Y.Z forms.
        """
        cleaned = s.lstrip("v").strip()
        parts = cleaned.split(".")
        try:
            self.major = int(parts[0])
            self.minor = int(parts[1]) if len(parts) > 1 else 0
            self.patch = int(parts[2]) if len(parts) > 2 else 0
        except (ValueError, IndexError) as exc:
            raise ValueError(f"Cannot parse version: {s!r}") from exc

    def __repr__(self) -> str:
        return f"Version({self.major}.{self.minor}.{self.patch})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)

    def __lt__(self, other: Version) -> bool:
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def __le__(self, other: Version) -> bool:
        return self == other or self < other

    def __gt__(self, other: Version) -> bool:
        return not self <= other

    def __ge__(self, other: Version) -> bool:
        return not self < other


# ---------------------------------------------------------------------------
# Constraint parsing
# ---------------------------------------------------------------------------

_CARET_RE = re.compile(r"^\^(.+)$")
_TILDE_RE = re.compile(r"^~(.+)$")
_EXACT_RE = re.compile(r"^=(.+)$")
_RANGE_RE = re.compile(r"^(>=|<=|>|<)(.+)$")
_WILDCARD_RE = re.compile(r"^\*$")


def _parse_single_constraint(expr: str) -> Callable[[Version], bool]:
    """
    Parse a single constraint expression into a predicate.

    Parameters
    ----------
    expr : str
        A single constraint like ``^1.5``, ``>=1.0``, ``=1.5.0``, or ``*``.

    Returns
    -------
    Callable[[Version], bool]
        Predicate returning True when a Version satisfies the constraint.
    """
    expr = expr.strip()

    # Wildcard — any version
    if _WILDCARD_RE.match(expr):
        return lambda v: True

    # Exact match: =1.5.0
    m = _EXACT_RE.match(expr)
    if m:
        target = Version(m.group(1))
        return lambda v, t=target: v == t

    # Caret: ^1.5  → >=1.5.0, <2.0.0
    m = _CARET_RE.match(expr)
    if m:
        base = Version(m.group(1))
        upper = Version(f"{base.major + 1}.0.0")
        return lambda v, lo=base, hi=upper: lo <= v < hi

    # Tilde: ~1.5.2 → >=1.5.2, <1.6.0
    m = _TILDE_RE.match(expr)
    if m:
        base = Version(m.group(1))
        upper = Version(f"{base.major}.{base.minor + 1}.0")
        return lambda v, lo=base, hi=upper: lo <= v < hi

    # Comparison: >=1.0, <=2.0, >1, <2
    m = _RANGE_RE.match(expr)
    if m:
        op, ver_str = m.group(1), m.group(2)
        target = Version(ver_str)
        if op == ">=":
            return lambda v, t=target: v >= t
        if op == "<=":
            return lambda v, t=target: v <= t
        if op == ">":
            return lambda v, t=target: v > t
        if op == "<":
            return lambda v, t=target: v < t

    # Bare version — treat as exact
    try:
        target = Version(expr)
        return lambda v, t=target: v == t
    except ValueError:
        pass

    raise ValueError(f"Cannot parse constraint: {expr!r}")


def parse_constraint(expr: str) -> list[Callable[[Version], bool]]:
    """
    Parse a constraint expression (possibly comma-separated) into a list of predicates.

    Parameters
    ----------
    expr : str
        Constraint expression, e.g. ``'^1.5'``, ``'>=1.0,<2.0'``, ``'*'``.

    Returns
    -------
    list[Callable[[Version], bool]]
        All predicates must be satisfied simultaneously.
    """
    parts = [p.strip() for p in expr.split(",") if p.strip()]
    return [_parse_single_constraint(p) for p in parts]


def satisfies(version: Version, constraints: list[Callable[[Version], bool]]) -> bool:
    """
    Return True if *version* satisfies all *constraints*.

    Parameters
    ----------
    version : Version
    constraints : list[Callable]
    """
    return all(c(version) for c in constraints)


def resolve(tags: list[str], constraint_expr: str) -> str | None:
    """
    Return the highest tag (as a string, preserving the original tag name)
    that satisfies *constraint_expr*, or ``None`` if no tag qualifies.

    Non-semver tags (e.g. ``latest``, ``nightly``) are silently ignored.

    Parameters
    ----------
    tags : list[str]
        List of Git tag names (e.g. ``['v1.4.0', 'v1.5.3', '2.0.0']``).
    constraint_expr : str
        Constraint expression string.

    Returns
    -------
    str or None
        The best matching tag name, or None.
    """
    constraints = parse_constraint(constraint_expr)

    # Build (Version, tag_str) pairs, skip non-semver
    candidates: list[tuple[Version, str]] = []
    for tag in tags:
        try:
            v = Version(tag)
            candidates.append((v, tag))
        except ValueError:
            continue

    # Sort descending; pick the first that satisfies all constraints
    candidates.sort(key=lambda pair: pair[0], reverse=True)
    for version, tag in candidates:
        if satisfies(version, constraints):
            return tag
    return None
