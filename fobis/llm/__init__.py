"""fobis.llm — provider-agnostic access to chat LLMs for FoBiS features.

Features build their prompts and call ``provider.chat(...)``; how the model is reached (Ollama native API,
any OpenAI-compatible server or hosted service, a scripted fake in tests) is the provider's business.
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

from .config import PROVIDERS, LLMConfig, resolve_api_key
from .errors import (
    ApiKeyError,
    ChecksumMismatchError,
    ConfigError,
    DownloadError,
    LLMError,
    ModelMissingError,
    ProviderResponseError,
    ProviderUnavailableError,
    RuntimeMissingError,
    ServerStartError,
)
from .fake import FakeProvider
from .ollama import OllamaProvider
from .openai import OpenAICompatProvider
from .provider import Completion, Message, Provider, messages

__all__ = [
    "PROVIDERS",
    "ApiKeyError",
    "ChecksumMismatchError",
    "Completion",
    "ConfigError",
    "DownloadError",
    "FakeProvider",
    "LLMConfig",
    "LLMError",
    "Message",
    "ModelMissingError",
    "OllamaProvider",
    "OpenAICompatProvider",
    "Provider",
    "ProviderResponseError",
    "ProviderUnavailableError",
    "RuntimeMissingError",
    "ServerStartError",
    "get_provider",
    "messages",
    "resolve_api_key",
]


def get_provider(cfg: LLMConfig, on_status=None) -> Provider:
    """Build the provider described by *cfg*.

    A ``managed`` provider starts llama-server on its first chat: call its ``close()`` when done (interpreter
    exit stops it too). *on_status* receives its progress messages.

    Raises
    ------
    ApiKeyError
        ``cfg.api_key_env`` names an unset or empty environment variable.
    """
    if cfg.provider == "managed":
        from .managed import ManagedProvider

        return ManagedProvider(
            cfg.model,
            runtime=cfg.runtime,
            variant=cfg.runtime_variant,
            n_ctx=cfg.n_ctx,
            n_gpu_layers=cfg.n_gpu_layers,
            threads=cfg.threads,
            startup_timeout=cfg.startup_timeout,
            timeout=cfg.timeout,
            on_status=on_status,
        )
    api_key = resolve_api_key(cfg.api_key_env)
    cls = OpenAICompatProvider if cfg.provider == "openai" else OllamaProvider
    return cls(cfg.url, cfg.model, api_key=api_key, timeout=cfg.timeout)
