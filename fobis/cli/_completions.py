"""
_completions.py — Typer autocompletion callbacks for FoBiS.py CLI.
"""

# Copyright (C) 2015  Stefano Zaghi
#
# This file is part of FoBiS.py.
#
# FoBiS.py is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# FoBiS.py is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with FoBiS.py. If not, see <http://www.gnu.org/licenses/>.

from __future__ import annotations

import configparser

import typer

from ._constants import __compiler_supported__, __extensions_parsed__

# Section/key prefixes that should never be offered as mode completions.
# Mirrors the resolved-section landscape in Fobos.py — anything that's a
# *kind* of section (template, rule, feature, varset, target, …) is filtered.
_NON_MODE_SECTIONS = frozenset(
    (
        "modes",
        "rules",
        "dependencies",
        "project",
        "features",
        "externals",
        "test",
        "coverage",
        "include",
        "varsets",
    )
)
_NON_MODE_PREFIXES = ("target.", "example.", "rule-", "feature:", "feature-group:", "varset:", "template-")


# ─── static completions ──────────────────────────────────────────────────────


def _complete_compiler(incomplete: str):
    return [c for c in __compiler_supported__ if c.startswith(incomplete.lower())]


def _complete_mklib(incomplete: str):
    return [m for m in ("static", "shared") if m.startswith(incomplete)]


def _complete_extensions(incomplete: str):
    return [e for e in __extensions_parsed__ if e.startswith(incomplete)]


def _complete_doctests_preprocessor(incomplete: str):
    return [p for p in ("cpp", "fpp") if p.startswith(incomplete)]


def _complete_build_profile(incomplete: str):
    return [p for p in ("debug", "release", "asan", "coverage") if p.startswith(incomplete)]


# ─── fobos-derived completions ───────────────────────────────────────────────


def _load_fobos_for_completion(ctx: typer.Context) -> configparser.RawConfigParser | None:
    """Best-effort load of the active fobos with includes resolved.

    Returns ``None`` if the fobos file cannot be located.  Errors during
    parsing or include resolution are swallowed so a temporarily-broken
    fobos still produces best-effort completion based on whatever was
    successfully read.
    """
    import os

    fobos_path = ctx.params.get("fobos") or "fobos"
    if not os.path.exists(fobos_path):
        return None
    case_insensitive = bool(ctx.params.get("fobos_case_insensitive"))
    cp = configparser.RawConfigParser()
    if not case_insensitive:
        cp.optionxform = str
    try:
        cp.read(fobos_path)
    except Exception:
        return None
    try:
        from ..Fobos import _resolve_includes

        _resolve_includes(cp, base_path=fobos_path, print_w=None, case_insensitive=case_insensitive)
    except (SystemExit, Exception):
        # Best-effort: keep whatever was loaded from the main file.
        pass
    return cp


def _last_token_in_csv(incomplete: str) -> tuple[str, str]:
    """Split ``--features a,b,inc<TAB>`` into ('a,b,', 'inc').

    Returns ``(prefix, last)`` where ``prefix`` is everything up to (and
    including) the last comma or whitespace separator, and ``last`` is the
    token currently being typed.  The caller prepends ``prefix`` to each
    suggestion to keep the user's earlier tokens intact.
    """
    if not incomplete:
        return "", ""
    # Find the last separator (',' or whitespace).
    last_sep = -1
    for i, ch in enumerate(incomplete):
        if ch == "," or ch.isspace():
            last_sep = i
    if last_sep < 0:
        return "", incomplete
    return incomplete[: last_sep + 1], incomplete[last_sep + 1 :]


def _complete_fobos_mode(ctx: typer.Context, incomplete: str):
    cp = _load_fobos_for_completion(ctx)
    if cp is None:
        return []
    if cp.has_option("modes", "modes"):
        modes = [m.strip() for m in cp.get("modes", "modes").split() if m.strip()]
        return [m for m in modes if m.startswith(incomplete)]
    return [
        s
        for s in cp.sections()
        if s.startswith(incomplete) and s not in _NON_MODE_SECTIONS and not s.startswith(_NON_MODE_PREFIXES)
    ]


def _complete_fobos_feature(ctx: typer.Context, incomplete: str):
    """Complete ``--features`` values from ``[features]`` and ``[feature:NAME]``.

    Handles comma- or space-separated lists: only the last token in
    ``incomplete`` is matched against the candidate set, and each suggestion
    is returned with the earlier tokens prepended so the shell preserves
    them on completion.
    """
    cp = _load_fobos_for_completion(ctx)
    if cp is None:
        return []
    candidates: set[str] = set()
    if cp.has_section("features"):
        for key, _value in cp.items("features"):
            if key.lower() != "default":
                candidates.add(key)
    for section in cp.sections():
        if section.startswith("feature:"):
            candidates.add(section[len("feature:") :])
    # Implicit features are always available.
    candidates.update(("openmp", "omp", "mpi", "coarray", "coverage", "profile", "openmp_offload", "omp_offload"))

    prefix, last = _last_token_in_csv(incomplete)
    return [prefix + name for name in sorted(candidates) if name.startswith(last)]


def _complete_fobos_varset(ctx: typer.Context, incomplete: str):
    """Complete ``--varset`` values from ``[varset:NAME]`` sections."""
    cp = _load_fobos_for_completion(ctx)
    if cp is None:
        return []
    candidates = sorted(s[len("varset:") :] for s in cp.sections() if s.startswith("varset:"))
    prefix, last = _last_token_in_csv(incomplete)
    return [prefix + name for name in candidates if name.startswith(last)]


def _complete_fobos_rule(ctx: typer.Context, incomplete: str):
    """Complete rule names from ``[rule-NAME]`` sections.

    Used by ``--execute`` / ``--ex`` (rule subcommand) and by
    ``--pre-build`` / ``--post-build`` (build subcommand).
    """
    cp = _load_fobos_for_completion(ctx)
    if cp is None:
        return []
    candidates = sorted(s[len("rule-") :] for s in cp.sections() if s.startswith("rule-"))
    return [name for name in candidates if name.startswith(incomplete)]


def _complete_fobos_target(ctx: typer.Context, incomplete: str):
    """Complete ``--target-filter`` values from ``[target.NAME]`` sections."""
    cp = _load_fobos_for_completion(ctx)
    if cp is None:
        return []
    candidates = sorted(s[len("target.") :] for s in cp.sections() if s.startswith("target."))
    prefix, last = _last_token_in_csv(incomplete)
    return [prefix + name for name in candidates if name.startswith(last)]
