"""ollama.py — provider for the Ollama native chat API."""

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
from .provider import Completion, Message


class OllamaProvider:
    """Chat through Ollama's native ``{url}/api/chat`` endpoint.

    Parameters
    ----------
    url : str
        Base URL of the Ollama server.
    model : str
        Model tag sent with every request.
    api_key : str or None
        Bearer token (Ollama behind an authenticating proxy, hosted Ollama); None sends no credentials.
    timeout : float
        Socket timeout in seconds.
    """

    name = "ollama"

    def __init__(self, url: str, model: str, api_key: str | None = None, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.url = url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout

    @property
    def endpoint(self) -> str:
        """Full URL of the chat endpoint."""
        return f"{self.url}/api/chat"

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
            body["format"] = schema
        options = {
            key: value
            for key, value in (("temperature", temperature), ("seed", seed), ("num_predict", max_tokens))
            if value is not None
        }
        if options:
            body["options"] = options
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
