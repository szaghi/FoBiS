"""provider.py — the provider protocol shared by every LLM backend."""

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

import copy
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

Message = dict[str, str]
"""A chat message: ``{"role": "system" | "user" | "assistant", "content": str}``."""

MAX_TEXT = 600
"""Default ``maxLength`` of a free-text field of an answer (a claim, a reason, a rationale)."""
MAX_ITEMS = 12
"""Default ``maxItems`` of an array of an answer."""
LENGTH_KEYWORDS = ("maxLength", "minLength")


def bounded(
    schema: dict,
    text: int = MAX_TEXT,
    items: int = MAX_ITEMS,
    free: tuple[str, ...] = (),
    limits: dict[str, int] | None = None,
) -> dict:
    """*schema* with every free-text string bounded by ``maxLength`` *text* and every array by ``maxItems`` *items*.

    A grammar-constrained server (llama-server, Ollama) otherwise lets a small model loop inside an unbounded
    string or array until the context is full (measured: coder-0.5b repeating ``"ours", "ours", ...``): a bound
    makes the grammar close the value, so the answer stays valid JSON. Enum strings are left alone; *free* names
    properties left unbounded (code: a merged text, a test program); *limits* overrides the bound of a property
    by name (``maxLength`` for a string, ``maxItems`` for an array).
    """
    limits = limits or {}
    result = copy.deepcopy(schema)

    def walk(node: dict, name: str = "") -> None:
        if not isinstance(node, dict):
            return
        if name not in free:
            if node.get("type") == "string" and "enum" not in node:
                node["maxLength"] = limits.get(name, text)
            elif node.get("type") == "array":
                node["maxItems"] = limits.get(name, items)
        for key, child in node.get("properties", {}).items():
            walk(child, key)
        if isinstance(node.get("items"), dict):
            walk(node["items"], name)

    walk(result)
    return result


def without_length_bounds(schema: dict) -> dict:
    """*schema* without ``maxLength``/``minLength``: OpenAI's strict structured outputs may reject them."""
    if isinstance(schema, dict):
        return {k: without_length_bounds(v) for k, v in schema.items() if k not in LENGTH_KEYWORDS}
    if isinstance(schema, list):
        return [without_length_bounds(v) for v in schema]
    return schema


def messages(prompt: str, system: str | None = None) -> list[Message]:
    """Chat messages for *prompt*, preceded by the *system* prompt when one is given."""
    head = [{"role": "system", "content": system}] if system else []
    return [*head, {"role": "user", "content": prompt}]


@dataclass(frozen=True)
class Completion:
    """The answer of a provider to one chat request."""

    text: str
    provider: str
    model: str


class Provider(Protocol):
    """A chat-completion backend.

    Implementations must be stateless between calls: every ``chat`` carries the whole conversation.
    """

    name: str
    model: str

    def chat(
        self,
        messages: list[Message],
        *,
        schema: dict | None = None,
        temperature: float | None = None,
        seed: int | None = None,
        max_tokens: int | None = None,
        on_token: Callable[[str], None] | None = None,
    ) -> Completion:
        """Send *messages* and return the complete answer.

        Parameters
        ----------
        messages : list of Message
            The conversation, oldest first.
        schema : dict or None
            JSON Schema the answer must satisfy; the provider constrains generation to it when the
            backend supports it (the answer text is then a JSON document).
        temperature, seed, max_tokens : optional
            Sampling controls; None leaves the backend default.
        on_token : callable or None
            Called with each streamed text fragment as it arrives.

        Raises
        ------
        LLMError
            Any failure to obtain an answer (see `fobis.llm.errors`).
        """
        ...
