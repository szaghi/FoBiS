"""fobis.lint — rule-based Fortran linter behind ``fobis lint``.

Rules are deterministic checks over the facts of `fobis.analysis`; each has an id (family prefix + number),
documentation (``fobis lint --explain ID``) and, when one exists, the code of the equivalent Fortitude rule.
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

from . import rules  # noqa: F401 - registers the rules
from .engine import (
    BaselineError,
    LintResult,
    apply_baseline,
    discover_files,
    lint_files,
    lint_text,
    load_baseline,
    write_baseline,
)
from .report import FORMATS, render, render_rule_list
from .rule import FAMILIES, RULES, Finding, Rule, select_rules

__all__ = [
    "FAMILIES",
    "FORMATS",
    "RULES",
    "BaselineError",
    "Finding",
    "LintResult",
    "Rule",
    "apply_baseline",
    "discover_files",
    "lint_files",
    "lint_text",
    "load_baseline",
    "render",
    "render_rule_list",
    "select_rules",
    "write_baseline",
]
