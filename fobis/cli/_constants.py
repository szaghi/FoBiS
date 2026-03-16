"""
_constants.py — file extension and compiler constants for FoBiS.py CLI.

These constants are re-exported from the top-level cli_parser module for
backward compatibility.
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

__extensions_inc__ = [".inc", ".INC", ".h", ".H"]
__extensions_old__ = [".f", ".F", ".for", ".FOR", ".fpp", ".FPP", ".fortran", ".f77", ".F77"]
__extensions_modern__ = [".f90", ".F90", ".f95", ".F95", ".f03", ".F03", ".f08", ".F08", ".f2k", ".F2K"]
__extensions_parsed__ = __extensions_inc__ + __extensions_old__ + __extensions_modern__
__compiler_supported__ = (
    "gnu",
    "intel",
    "intel_nextgen",
    "g95",
    "opencoarrays-gnu",
    "pgi",
    "ibm",
    "nag",
    "nvfortran",
    "amd",
    "custom",
)
