"""openai.py — provider for any OpenAI-compatible chat-completions endpoint."""

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

from .http import DEFAULT_TIMEOUT, post_stream
from .provider import Completion, Message, without_length_bounds


class OpenAICompatProvider:
    """Chat through ``{url}/v1/chat/completions`` (llama-server, vLLM, LM Studio, hosted services).

    Parameters
    ----------
    url : str
        Base URL of the server (no ``/v1`` suffix).
    model : str
        Model identifier sent with every request.
    api_key : str or None
        Bearer token; None sends no credentials.
    timeout : float
        Socket timeout in seconds.
    length_bounds : bool
        Send the schema's ``maxLength``/``minLength``. Off by default: OpenAI's strict structured outputs may
        reject them (``maxItems`` is kept); the managed llama-server turns them into its grammar.
    """

    name = "openai"

    def __init__(
        self,
        url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        length_bounds: bool = False,
    ) -> None:
        self.url = url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.length_bounds = length_bounds  # send maxLength/minLength (llama-server: yes; unknown server: no)

    @property
    def endpoint(self) -> str:
        """Full URL of the chat-completions endpoint."""
        return f"{self.url}/v1/chat/completions"

    def payload(
        self,
        messages: list[Message],
        *,
        schema: dict | None = None,
        temperature: float | None = None,
        seed: int | None = None,
        max_tokens: int | None = None,
    ) -> dict:
        """Request body for *messages*; optional fields are sent only when set."""
        body: dict = {"model": self.model, "messages": messages, "stream": True}
        if schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "schema": schema if self.length_bounds else without_length_bounds(schema),
                    "strict": True,
                },
            }
        if temperature is not None:
            body["temperature"] = temperature
        if seed is not None:
            body["seed"] = seed
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        return body

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
        """Send *messages* and return the complete answer (see `fobis.llm.provider.Provider.chat`)."""
        body = self.payload(messages, schema=schema, temperature=temperature, seed=seed, max_tokens=max_tokens)
        text = post_stream(self.endpoint, body, api_key=self.api_key, timeout=self.timeout, on_token=on_token)
        return Completion(text=text, provider=self.name, model=self.model)
