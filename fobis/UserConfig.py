"""
UserConfig.py — user-level FoBiS configuration (~/.config/fobis/config.ini).
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

import configparser
import os

_DEFAULT_CONFIG_PATH = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "fobis",
    "config.ini",
)

_TEMPLATE = """\
# FoBiS user configuration
# Location: {path}
#
# All values shown are the defaults.  Uncomment and edit to override.

[llm]
# LLM backend: "ollama" (native API) or "openai" (any OpenAI-compatible endpoint)
# backend = ollama

# Base URL of the LLM server (no trailing slash)
# url = http://localhost:11434

# Model to use for commit-message generation
# model = qwen3-coder:30b-a3b-q4_K_M

# Maximum staged-diff characters sent to the model (long diffs are truncated)
# max_diff_chars = 12000

# Critique-and-rewrite passes after the initial draft (0 = single pass)
# Increase to 1-3 for small/fast models that produce shallow first drafts
# refine_passes = 0
"""

_BACKENDS = ("ollama", "openai")


class UserConfig:
    """
    Reads ~/.config/fobis/config.ini (or a custom path) and exposes
    LLM settings with hardcoded defaults as fallback.
    """

    DEFAULT_BACKEND = "ollama"
    DEFAULT_URL = "http://localhost:11434"
    DEFAULT_MODEL = "qwen3-coder:30b-a3b-q4_K_M"
    DEFAULT_MAX_DIFF_CHARS = 12_000
    DEFAULT_REFINE_PASSES = 0

    def __init__(self, path: str | None = None) -> None:
        self.path = path or _DEFAULT_CONFIG_PATH
        self._cp = configparser.ConfigParser()
        if os.path.exists(self.path):
            self._cp.read(self.path)

    def _get(self, section: str, key: str, fallback):
        return self._cp.get(section, key, fallback=fallback)

    # ── LLM settings ──────────────────────────────────────────────────────────

    @property
    def llm_backend(self) -> str:
        return self._get("llm", "backend", self.DEFAULT_BACKEND)

    @property
    def llm_url(self) -> str:
        return self._get("llm", "url", self.DEFAULT_URL)

    @property
    def llm_model(self) -> str:
        return self._get("llm", "model", self.DEFAULT_MODEL)

    @property
    def llm_max_diff_chars(self) -> int:
        return int(self._get("llm", "max_diff_chars", str(self.DEFAULT_MAX_DIFF_CHARS)))

    @property
    def llm_refine_passes(self) -> int:
        return int(self._get("llm", "refine_passes", str(self.DEFAULT_REFINE_PASSES)))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def create_default(self) -> None:
        """Write a commented template to self.path (only if it does not exist)."""
        if os.path.exists(self.path):
            return
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(_TEMPLATE.format(path=self.path))

    def show(self) -> str:
        """Return a human-readable summary of effective settings."""
        lines = [
            f"Config file : {self.path}",
            "  [llm]",
            f"  backend       = {self.llm_backend}",
            f"  url           = {self.llm_url}",
            f"  model         = {self.llm_model}",
            f"  max_diff_chars= {self.llm_max_diff_chars}",
            f"  refine_passes = {self.llm_refine_passes}",
        ]
        return "\n".join(lines)
