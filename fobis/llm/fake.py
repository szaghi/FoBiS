"""fake.py — deterministic provider replaying scripted answers (tests, demos)."""

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

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from .errors import LLMError
from .provider import Completion, Message


@dataclass
class FakeCall:
    """One request received by a `FakeProvider`."""

    messages: list[Message]
    schema: dict | None
    options: dict = field(default_factory=dict)


class FakeProvider:
    """Answer each ``chat`` with the next scripted reply and record the request.

    Parameters
    ----------
    replies : iterable of str, or callable
        The answers, in order; or a function ``(messages) -> str`` computing each answer.
    model : str
        Model name reported in the completions.
    """

    name = "fake"

    def __init__(self, replies: Iterable[str] | Callable[[list[Message]], str], model: str = "fake-model") -> None:
        self.model = model
        self.calls: list[FakeCall] = []
        self._answer = replies if callable(replies) else None
        self._script = None if callable(replies) else iter(list(replies))

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
        """Record the request and return the next scripted answer.

        Raises
        ------
        LLMError
            The scripted replies are exhausted.
        """
        options = {"temperature": temperature, "seed": seed, "max_tokens": max_tokens}
        self.calls.append(FakeCall(messages=messages, schema=schema, options=options))
        if self._answer is not None:
            text = self._answer(messages)
        else:
            text = next(self._script, None)
            if text is None:
                raise LLMError(f"FakeProvider: no scripted reply left for call {len(self.calls)}")
        if on_token is not None:
            on_token(text)
        return Completion(text=text, provider=self.name, model=self.model)
