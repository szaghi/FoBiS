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

import typer

from ._constants import __compiler_supported__, __extensions_parsed__


def _complete_compiler(incomplete: str):
    return [c for c in __compiler_supported__ if c.startswith(incomplete.lower())]


def _complete_mklib(incomplete: str):
    return [m for m in ("static", "shared") if m.startswith(incomplete)]


def _complete_extensions(incomplete: str):
    return [e for e in __extensions_parsed__ if e.startswith(incomplete)]


def _complete_doctests_preprocessor(incomplete: str):
    return [p for p in ("cpp", "fpp") if p.startswith(incomplete)]


def _complete_fobos_mode(ctx: typer.Context, incomplete: str):
    import configparser
    import os

    fobos_path = ctx.params.get("fobos") or "fobos"
    if not os.path.exists(fobos_path):
        return []
    cp = configparser.RawConfigParser()
    cp.read(fobos_path)
    if cp.has_option("modes", "modes"):
        modes = [m.strip() for m in cp.get("modes", "modes").split()]
        return [m for m in modes if m.startswith(incomplete)]
    _NON_MODE_SECTIONS = frozenset(
        ("modes", "rules", "dependencies", "project", "features", "externals", "test", "coverage")
    )
    return [
        s
        for s in cp.sections()
        if s.startswith(incomplete)
        and s not in _NON_MODE_SECTIONS
        and not s.startswith(("target.", "example.", "rule-"))
    ]
