"""fobis.kb — knowledge packs: reference material for explanations, searchable without a model.

A pack is a directory with ``pack.ini`` (name, version, license, attribution, source), an optional ``NOTICE``
and ``index.json`` (the chunks). Packs ship with FoBiS (``fobis/kb/packs``) and can be added per user
(``~/.config/fobis/kb``) or per project (``.fobis/kb``); `KnowledgeBase` retrieves chunks by BM25 and exact
symbols.
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

from .build import Source, build_pack, clean, skill_sources
from .pack import SHIPPED_DIR, Chunk, Pack, PackError, discover_packs, load_pack, project_dir, user_dir
from .search import KnowledgeBase, Result, tokenize

__all__ = [
    "SHIPPED_DIR",
    "Chunk",
    "KnowledgeBase",
    "Pack",
    "PackError",
    "Result",
    "Source",
    "build_pack",
    "clean",
    "discover_packs",
    "load_pack",
    "project_dir",
    "skill_sources",
    "tokenize",
    "user_dir",
]
