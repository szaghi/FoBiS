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
import re
import tempfile

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

[ecosystem]
# Directory the projects live in (relative entries of 'projects' are resolved against it)
# root = ~/fortran

# The managed projects: directory names under root, or paths; whitespace or newline separated
# projects = PENF FACE BeFoR64 StringiFor FLAP

# HTML dashboard palette: github solarized dracula nord tokyo-night catppuccin gruvbox one rose-pine
# theme = github

# HTML dashboard mode: auto (follow the system), light or dark
# mode = auto
"""

_BACKENDS = ("ollama", "openai")
_KEY_RE = re.compile(r"^([A-Za-z_][\w-]*)\s*[=:]")  # an uncommented, unindented key line


def _format_list(key: str, values: list[str], width: int = 100) -> list[str]:
    """Format ``key = v1 v2 ...`` as INI lines, wrapping long lists on indented continuation lines."""
    prefix = f"{key} = "
    lines, current = [], prefix
    for value in values:
        if current != prefix and len(current) + len(value) + 1 > width:
            lines.append(current.rstrip())
            current = " " * len(prefix)
        current += value + " "
    lines.append(current.rstrip())
    return lines


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

    # ── Ecosystem settings ────────────────────────────────────────────────────

    @property
    def ecosystem_root(self) -> str:
        """Directory the managed projects live in ('' when not configured)."""
        root = self._get("ecosystem", "root", "")
        return os.path.abspath(os.path.expanduser(root)) if root else ""

    @property
    def ecosystem_entries(self) -> list[str]:
        """The ``projects`` entries as written (names under root, or paths)."""
        return self._get("ecosystem", "projects", "").split()

    @property
    def ecosystem_projects(self) -> list[str]:
        """Absolute paths of the managed projects, in the order they are listed."""
        return [self.ecosystem_path(entry) for entry in self.ecosystem_entries]

    def ecosystem_path(self, entry: str) -> str:
        """Return the absolute path of a ``projects`` entry (relative entries resolve against root, else the cwd)."""
        path = os.path.expanduser(entry)
        return os.path.abspath(path if os.path.isabs(path) else os.path.join(self.ecosystem_root or os.getcwd(), path))

    def ecosystem_entry(self, path: str) -> str:
        """Return how *path* is written in ``projects``: its bare name when it sits directly in root, else ``~/...`` or absolute."""
        path = os.path.abspath(os.path.expanduser(path))
        if self.ecosystem_root and os.path.dirname(path) == self.ecosystem_root:
            return os.path.basename(path)
        home = os.path.expanduser("~")
        return "~" + path[len(home) :] if path.startswith(home + os.sep) else path

    def set_ecosystem_projects(self, entries: list[str]) -> None:
        """
        Write the ``[ecosystem] projects`` list, leaving the rest of the file as it is.

        configparser would drop every comment when writing the file back, so only the lines of the
        ``projects`` key (and its continuation lines) are replaced; the section, or the file, is
        created when missing. The file is replaced atomically.

        Parameters
        ----------
        entries : list[str]
            Project entries (names under root, or paths), in order.
        """
        lines = []
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        new = _format_list("projects", entries)
        header = next((i for i, line in enumerate(lines) if line.strip().lower() == "[ecosystem]"), None)
        if header is None:
            lines += ([""] if lines and lines[-1].strip() else []) + ["[ecosystem]", *new]
        else:
            end = next((i for i in range(header + 1, len(lines)) if lines[i].lstrip().startswith("[")), len(lines))
            key = next(
                (
                    i
                    for i in range(header + 1, end)
                    if _KEY_RE.match(lines[i]) and _KEY_RE.match(lines[i]).group(1) == "projects"
                ),
                None,
            )
            if key is None:
                lines[header + 1 : header + 1] = new
            else:
                stop = key + 1
                while stop < end and lines[stop].strip() and lines[stop][:1] in " \t":  # continuation lines
                    stop += 1
                lines[key:stop] = new
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(self.path)), prefix=".config-", suffix=".ini")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        os.replace(tmp, self.path)
        self._cp = configparser.ConfigParser()
        self._cp.read(self.path)

    @property
    def ecosystem_theme(self) -> str:
        """Palette of the HTML dashboard."""
        return self._get("ecosystem", "theme", "github")

    @property
    def ecosystem_mode(self) -> str:
        """Light/dark mode of the HTML dashboard: auto, light or dark."""
        return self._get("ecosystem", "mode", "auto")

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
