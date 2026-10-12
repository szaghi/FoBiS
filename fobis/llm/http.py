"""http.py — stdlib streaming client for chat endpoints (OpenAI SSE and Ollama NDJSON)."""

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

import json
import urllib.error
import urllib.request
from collections.abc import Callable

from .errors import ProviderResponseError, ProviderUnavailableError

DEFAULT_TIMEOUT = 120


def _token(chunk: dict) -> str:
    """The text fragment carried by one streamed *chunk* (Ollama native or OpenAI-compatible format)."""
    token = chunk.get("message", {}).get("content", "")
    if not token and chunk.get("choices"):
        token = chunk["choices"][0].get("delta", {}).get("content") or ""
    return token


def post_stream(
    url: str,
    payload: dict,
    *,
    api_key: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    on_token: Callable[[str], None] | None = None,
) -> str:
    """POST *payload* as JSON to *url* and collect the streamed answer.

    Parameters
    ----------
    url : str
        Full endpoint URL.
    payload : dict
        Request body, serialised as JSON.
    api_key : str or None
        Sent as ``Authorization: Bearer <api_key>`` when given; nothing is sent otherwise.
    timeout : float
        Socket timeout in seconds (connection and between streamed lines).
    on_token : callable or None
        Called with each text fragment as it arrives.

    Returns
    -------
    str
        The concatenated answer, stripped.

    Raises
    ------
    ProviderResponseError
        The endpoint answered with an HTTP error status.
    ProviderUnavailableError
        The endpoint cannot be reached, or the connection timed out or dropped.
    """
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
    collected = []
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            for raw_line in resp:
                line = raw_line.decode().strip()
                if not line:
                    continue
                # OpenAI SSE: "data: {...}" or "data: [DONE]"
                if line.startswith("data:"):
                    line = line[5:].strip()
                    if line == "[DONE]":
                        break
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                token = _token(chunk)
                if token:
                    collected.append(token)
                    if on_token is not None:
                        on_token(token)
                if chunk.get("done"):  # Ollama end-of-stream marker
                    break
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace").strip()[:500]
        raise ProviderResponseError(
            f"LLM at {url} answered HTTP {exc.code} {exc.reason}" + (f": {detail}" if detail else ""), exc.code
        ) from exc
    except urllib.error.URLError as exc:
        raise ProviderUnavailableError(f"cannot reach LLM at {url}: {exc.reason}") from exc
    except (TimeoutError, ConnectionError) as exc:
        raise ProviderUnavailableError(f"connection to LLM at {url} failed: {exc}") from exc
    return "".join(collected).strip()
