"""fobis.analysis — Fortran source facts for the linter and the AI features.

A tolerant, statement-level analysis (not a parser): `lex` turns a file into logical statements after resolving
conditional compilation with the build mode's defines; `build_units` derives the program-unit tree with the
specification facts of each unit.
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

from .lexer import SourceFile, Statement, Suppression, lex, mask_strings, read_source
from .preprocessor import parse_defines, preprocess
from .units import Decl, FileUnits, Unit, Use, build_units, split_top

__all__ = [
    "Decl",
    "FileUnits",
    "SourceFile",
    "Statement",
    "Suppression",
    "Unit",
    "Use",
    "build_units",
    "lex",
    "mask_strings",
    "parse_defines",
    "preprocess",
    "read_source",
    "split_top",
]
