"""fobis.verification — FoBiS as the oracle of a change: cases, quantities, runs and their provenance.

Phase V1 of ``PLAN-verification.md``: runnable cases declared in the fobos (`case`), the quantities extracted from
what they produce (`probes`), how they are built and run (`runner`), and what produced a result (`provenance`).
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

from .case import Case, CaseError, Settings, load_cases, load_settings
from .probes import Probe, ProbeError, Quantity, RunOutput, extract, parse_probes
from .runner import LocalRunner, RunResult

__all__ = [
    "Case",
    "CaseError",
    "LocalRunner",
    "Probe",
    "ProbeError",
    "Quantity",
    "RunOutput",
    "RunResult",
    "Settings",
    "extract",
    "load_cases",
    "load_settings",
    "parse_probes",
]
