"""search.py — lexical retrieval over knowledge packs: BM25 plus exact-symbol matching.

Technical questions name exact things (`firstprivate`, `mpi_isend`, `C1012`), where lexical matching beats
embeddings, and the corpus is small: a few thousand chunks scored in memory. Heading words count twice
(a section's title says what it is about); a query term that is one of a chunk's symbols adds a bonus.
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

import math
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from .pack import Chunk, Pack, PackError, discover_packs

K1 = 1.2
B = 0.75
SYMBOL_BONUS = 2.0
_TOKEN_RE = re.compile(r"[a-z_][a-z0-9_]*|\d+")
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "can",
        "do",
        "does",
        "for",
        "from",
        "has",
        "have",
        "how",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "no",
        "not",
        "of",
        "on",
        "or",
        "such",
        "that",
        "the",
        "their",
        "then",
        "there",
        "these",
        "this",
        "to",
        "was",
        "what",
        "when",
        "where",
        "which",
        "while",
        "with",
        "without",
        "you",
        "your",
    ]
)


def tokenize(text: str) -> list[str]:
    """Lower-case terms of *text*; a snake_case term also yields its parts (``mpi_isend`` -> ``mpi``, ``isend``)."""
    terms = []
    for token in _TOKEN_RE.findall(text.lower()):
        if token in _STOPWORDS:
            continue
        terms.append(token)
        if "_" in token.strip("_"):
            terms.extend(part for part in token.split("_") if part and part not in _STOPWORDS)
    return terms


@dataclass(frozen=True)
class Result:
    """A retrieved chunk and its score."""

    chunk: Chunk
    score: float


class KnowledgeBase:
    """The chunks of a set of packs, indexed for retrieval."""

    def __init__(self, packs: Iterable[Pack]) -> None:
        self.packs = {pack.name: pack for pack in packs}
        self.chunks: list[Chunk] = [chunk for pack in self.packs.values() for chunk in pack.chunks]
        self.by_id = {chunk.id: chunk for chunk in self.chunks}
        self._terms: list[Counter] = []
        self._lengths: list[int] = []
        document_frequency: Counter = Counter()
        for chunk in self.chunks:
            terms = Counter(tokenize(chunk.text) + 2 * tokenize(chunk.heading))
            self._terms.append(terms)
            self._lengths.append(sum(terms.values()))
            document_frequency.update(terms.keys())
        count = max(len(self.chunks), 1)
        self._average = sum(self._lengths) / count if self._lengths else 0.0
        self._idf = {t: math.log(1 + (count - n + 0.5) / (n + 0.5)) for t, n in document_frequency.items()}

    @classmethod
    def load(cls, root: str = ".", names: Iterable[str] | None = None) -> KnowledgeBase:
        """The installed packs (see `discover_packs`), optionally only those named.

        Raises
        ------
        PackError
            A requested pack is not installed.
        """
        packs = discover_packs(root)
        if names:
            wanted = set(names)
            missing = wanted - {p.name for p in packs}
            if missing:
                raise PackError(f"pack(s) not installed: {', '.join(sorted(missing))} (see fobis kb list)")
            packs = [p for p in packs if p.name in wanted]
        return cls(packs)

    def search(self, query: str, k: int = 5, packs: Iterable[str] | None = None) -> list[Result]:
        """The *k* chunks best matching *query*, best first (only from *packs* when given)."""
        allowed = set(packs) if packs else None
        terms = tokenize(query)
        phrase_symbols = {" ".join(query.lower().split())} | set(terms)
        results = []
        for idx, chunk in enumerate(self.chunks):
            if allowed is not None and chunk.pack not in allowed:
                continue
            score = self._bm25(idx, terms)
            score += SYMBOL_BONUS * len(phrase_symbols & set(chunk.symbols))
            if score > 0:
                results.append(Result(chunk, score))
        results.sort(key=lambda r: (-r.score, r.chunk.id))
        return results[:k]

    def _bm25(self, idx: int, terms: list[str]) -> float:
        counts, length = self._terms[idx], self._lengths[idx]
        score = 0.0
        for term in set(terms):
            freq = counts.get(term, 0)
            if freq:
                norm = freq * (K1 + 1) / (freq + K1 * (1 - B + B * length / (self._average or 1)))
                score += self._idf.get(term, 0.0) * norm
        return score

    def get(self, chunk_id: str) -> Chunk:
        """The chunk with id *chunk_id*.

        Raises
        ------
        KeyError
            No such chunk.
        """
        return self.by_id[chunk_id]

    def neighbours(self, chunk_id: str, before: int = 1, after: int = 1) -> list[Chunk]:
        """The chunk and its neighbours in the same document, in document order."""
        chunk = self.get(chunk_id)
        same_doc = [c for c in self.packs[chunk.pack].chunks if c.doc == chunk.doc]
        pos = next(i for i, c in enumerate(same_doc) if c.id == chunk_id)
        return same_doc[max(0, pos - before) : pos + after + 1]
