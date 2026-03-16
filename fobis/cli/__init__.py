"""
fobis.cli — FoBiS.py CLI sub-package.

This package owns the Typer application and all subcommand definitions.
Symbols re-exported here preserve the public API that the rest of
FoBiS.py (and user code) previously imported from ``fobis.cli_parser``.
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

# Import command modules to register their @app.command decorators
from . import build, clean, doctests, fetch, install, rule  # noqa: F401
from ._app import _normalize_args, app
from ._constants import (
    __compiler_supported__,
    __extensions_inc__,
    __extensions_modern__,
    __extensions_old__,
    __extensions_parsed__,
)

__all__ = [
    "__compiler_supported__",
    "__extensions_inc__",
    "__extensions_modern__",
    "__extensions_old__",
    "__extensions_parsed__",
    "_normalize_args",
    "app",
]
