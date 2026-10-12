"""errors.py — exception hierarchy of the FoBiS LLM layer."""

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


class LLMError(Exception):
    """Base class of every error raised by the LLM layer."""


class ConfigError(LLMError):
    """The LLM configuration is invalid (unknown provider, malformed value)."""


class ApiKeyError(ConfigError):
    """The environment variable configured to hold the API key is unset or empty."""


class ProviderUnavailableError(LLMError):
    """The provider endpoint cannot be reached (refused, unresolvable, timed out, dropped)."""


class ProviderResponseError(LLMError):
    """The provider answered with an HTTP error status."""

    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.status = status


class ModelMissingError(LLMError):
    """The configured model is not in the local store (nothing is downloaded implicitly)."""


class DownloadError(LLMError):
    """A model could not be downloaded (network, HTTP status, gated repository, disk space)."""


class ChecksumMismatchError(DownloadError):
    """A downloaded file does not match the size or sha256 published by the Hub."""
