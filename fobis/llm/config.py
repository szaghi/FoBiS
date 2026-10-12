"""config.py — effective LLM configuration: user config file overridden by CLI options."""

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
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .errors import ApiKeyError, ConfigError
from .http import DEFAULT_TIMEOUT

if TYPE_CHECKING:
    from ..UserConfig import UserConfig

PROVIDERS = ("managed", "ollama", "openai")


def resolve_api_key(api_key_env: str | None) -> str | None:
    """Return the API key held by the environment variable *api_key_env*.

    No variable configured means no key: a key is never read from an implicit default variable, so it
    cannot leak to a server it was not meant for.

    Raises
    ------
    ApiKeyError
        *api_key_env* names a variable that is unset or empty.
    """
    if not api_key_env:
        return None
    key = os.environ.get(api_key_env, "").strip()
    if not key:
        raise ApiKeyError(f"api_key_env is set to {api_key_env!r}, but that environment variable is unset or empty")
    return key


@dataclass(frozen=True)
class LLMConfig:
    """Everything needed to build a provider.

    Attributes
    ----------
    provider : str
        One of `PROVIDERS`.
    url : str
        Base URL of the server.
    model : str
        Model identifier.
    api_key_env : str
        Name of the environment variable holding the API key ('' = no credentials).
    timeout : float
        Socket timeout in seconds.
    runtime, runtime_variant, n_ctx, n_gpu_layers, threads, startup_timeout :
        Managed provider only (see `fobis.llm.managed.ManagedProvider`).
    """

    provider: str
    url: str
    model: str
    api_key_env: str = ""
    timeout: float = DEFAULT_TIMEOUT
    runtime: str = "pinned"
    runtime_variant: str = "auto"
    n_ctx: int = 16384
    n_gpu_layers: str = "auto"
    threads: int = 0
    startup_timeout: float = 120.0

    def __post_init__(self) -> None:
        if self.provider not in PROVIDERS:
            choices = ", ".join(f'"{p}"' for p in PROVIDERS)
            raise ConfigError(f"unknown LLM provider {self.provider!r}: use one of {choices}")

    @classmethod
    def from_user_config(
        cls,
        ucfg: UserConfig,
        *,
        provider: str | None = None,
        url: str | None = None,
        model: str | None = None,
        api_key_env: str | None = None,
    ) -> LLMConfig:
        """Settings of *ucfg* (``[llm]`` section), each overridden by the matching non-empty argument."""
        provider = provider or ucfg.llm_provider
        return cls(
            provider=provider,
            url=url or ucfg.llm_url,
            model=model or ucfg.llm_model_for(provider),
            api_key_env=api_key_env or ucfg.llm_api_key_env,
            runtime=ucfg.llm_runtime,
            runtime_variant=ucfg.llm_runtime_variant,
            n_ctx=ucfg.llm_n_ctx,
            n_gpu_layers=ucfg.llm_n_gpu_layers,
            threads=ucfg.llm_threads,
            startup_timeout=ucfg.llm_startup_timeout,
        )
