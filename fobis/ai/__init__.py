"""fobis.ai — LLM features grounded on FoBiS's facts and knowledge packs.

Every feature builds a deterministic `grounding.ContextBundle`, asks the model for schema-constrained, cited
claims, and drops what is not cited (`grounding.check_claims`). Prompts are templates in ``prompts/``.
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

from .grounding import Claim, ContextBundle, Grounded, Source, check_claims, claims_schema, render_answer, to_json

__all__ = [
    "Claim",
    "ContextBundle",
    "Grounded",
    "Source",
    "check_claims",
    "claims_schema",
    "render_answer",
    "to_json",
]
