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

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

Message = dict[str, str]
"""A chat message: ``{"role": "system" | "user" | "assistant", "content": str}``."""


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
