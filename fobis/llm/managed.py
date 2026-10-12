"""managed.py — the ``managed`` provider: FoBiS runs llama.cpp itself.

On the first chat it resolves the runtime (`fobis.llm.runtime`) and the model (`fobis.llm.models`), starts a
`fobis.llm.server.LlamaServer` on loopback and talks to it through the OpenAI-compatible client; the same server
answers every later chat of the command, and `ManagedProvider.close` (or interpreter exit) stops it. Nothing is
downloaded here: a missing runtime or model raises an error naming the command that installs it.
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

import os
import subprocess
from collections.abc import Callable

from .errors import ModelMissingError, RuntimeMissingError
from .http import DEFAULT_TIMEOUT
from .models import ModelStore, default_root
from .openai import OpenAICompatProvider
from .provider import Completion, Message
from .runtime import RuntimeManager
from .server import LlamaServer, running_state


class ManagedProvider:
    """Chat with a local model served by a llama-server that FoBiS starts and stops.

    Parameters
    ----------
    model : str
        Alias, ``hf:`` spec or GGUF path (see `fobis.llm.models.parse_spec`).
    runtime, variant : str
        Which ``llama-server`` to run (see `fobis.llm.runtime.RuntimeManager.resolve`).
    n_ctx, n_gpu_layers, threads, startup_timeout :
        Server settings (see `fobis.llm.server.LlamaServer`).
    timeout : float
        Socket timeout of each chat request.
    root : str or None
        LLM directory (``$FOBIS_LLM_DIR`` or ``~/.fobis/llm``).
    on_status : callable or None
        Receives progress messages (server starting).
    popen : callable
        ``subprocess.Popen``; injectable for tests.
    """

    name = "managed"

    def __init__(
        self,
        model: str,
        *,
        runtime: str = "pinned",
        variant: str = "auto",
        n_ctx: int = 16384,
        n_gpu_layers: str = "auto",
        threads: int = 0,
        startup_timeout: float = 120.0,
        timeout: float = DEFAULT_TIMEOUT,
        root: str | None = None,
        on_status: Callable[[str], None] | None = None,
        popen: Callable = subprocess.Popen,
    ) -> None:
        self.model = model
        self.runtime = runtime
        self.variant = variant
        self.n_ctx = n_ctx
        self.n_gpu_layers = n_gpu_layers
        self.threads = threads
        self.startup_timeout = startup_timeout
        self.timeout = timeout
        self.root = root or default_root()
        self.on_status = on_status
        self.popen = popen
        self.server: LlamaServer | None = None
        self.attached: dict | None = None
        self._client: OpenAICompatProvider | None = None

    def resolve(self) -> tuple[str, str]:
        """(llama-server path, GGUF path), checking both before anything starts.

        Raises
        ------
        RuntimeMissingError, ModelMissingError
            When either is missing; with both missing, one `RuntimeMissingError` names both commands.
        """
        problems: list[str] = []
        binary = model_path = ""
        try:
            binary = RuntimeManager(self.root).resolve(self.runtime, self.variant)
        except RuntimeMissingError as exc:
            problems.append(str(exc))
        try:
            model_path = ModelStore(self.root).locate(self.model)
        except ModelMissingError as exc:
            if not problems:
                raise
            problems.append(str(exc))
        if problems:
            raise RuntimeMissingError("; ".join(problems))
        return binary, model_path

    def attach(self) -> dict | None:
        """Use the persistent server (``fobis llm serve start``) when it is alive and serves this model.

        Returns its record, None when there is none to use (an ephemeral server is started instead).
        """
        state = running_state(self.root)
        if state is None:
            return None
        try:
            model_path = ModelStore(self.root).locate(self.model)
        except ModelMissingError:
            return None
        if os.path.realpath(state.get("model_path", "")) != os.path.realpath(model_path):
            return None
        self.attached = state
        self._client = OpenAICompatProvider(state["url"], self.model, api_key=state["api_key"], timeout=self.timeout)
        return state

    def start(self) -> LlamaServer | None:
        """Start the server unless one is running (own or persistent); returns the own server, None when attached
        to the persistent one."""
        if self.server is not None or self._client is not None:
            return self.server
        if self.attach() is not None:
            if self.on_status:
                self.on_status(f"Using the running llama-server at {self.attached['url']}")
            return None
        binary, model_path = self.resolve()
        server = LlamaServer(
            binary,
            model_path,
            log_path=os.path.join(self.root, "logs", "llama-server.log"),
            n_ctx=self.n_ctx,
            n_gpu_layers=self.n_gpu_layers,
            threads=self.threads,
            startup_timeout=self.startup_timeout,
            popen=self.popen,
        )
        if self.on_status:
            self.on_status(f"Starting llama-server with {os.path.basename(model_path)}...")
        server.start()
        self.server = server
        self._client = OpenAICompatProvider(server.url, self.model, api_key=server.api_key, timeout=self.timeout)
        return server

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
        """Send *messages* to the local model (see `fobis.llm.provider.Provider.chat`)."""
        self.start()
        completion = self._client.chat(
            messages, schema=schema, temperature=temperature, seed=seed, max_tokens=max_tokens, on_token=on_token
        )
        return Completion(text=completion.text, provider=self.name, model=self.model)

    def close(self) -> None:
        """Stop the server this provider started; a persistent server it attached to keeps running."""
        if self.server is not None:
            self.server.stop()
        self.server = None
        self.attached = None
        self._client = None

    def __enter__(self) -> ManagedProvider:
        return self

    def __exit__(self, *exc) -> None:
        self.close()
