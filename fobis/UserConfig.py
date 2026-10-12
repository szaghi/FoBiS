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


def default_config_path() -> str:
    """``$XDG_CONFIG_HOME/fobis/config.ini`` (``~/.config`` when unset), read when called, not at import."""
    return os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "fobis", "config.ini")


_TEMPLATE = """\
# FoBiS user configuration
# Location: {path}
#
# All values shown are the defaults.  Uncomment and edit to override.

[llm]
# LLM provider: "managed" (fobis runs llama.cpp locally: fobis llm runtime install, fobis llm pull),
# "ollama" (native API) or "openai" (any OpenAI-compatible endpoint)
# (the former key name `backend` is still read)
# provider = managed

# Base URL of the LLM server (no trailing slash)
# url = http://localhost:11434

# Name of the environment variable holding the API key, sent as "Authorization: Bearer <key>".
# Needed by hosted endpoints (OpenAI, Mistral, ...); unset = no credentials are sent.
# api_key_env = OPENAI_API_KEY

# Model: for "managed" an alias (fobis llm recommended), hf:<org>/<repo>[@<rev>]/<file>.gguf or a GGUF path;
# for ollama/openai the server's model name. Default: coder-7b (managed), qwen3-coder:30b-a3b-q4_K_M (others)
# model = coder-7b

# managed only: which llama-server to run: "pinned" (fobis llm runtime install), "PATH", or a path
# runtime = pinned
# managed only: build variant when several are installed: auto, cpu, metal, cuda12, cuda13, vulkan, rocm, sycl
# runtime_variant = auto
# managed only: context size, layers offloaded to the GPU (a number, auto or all), CPU threads (0 = llama.cpp
# default), seconds to wait for the model to load
# n_ctx = 16384
# n_gpu_layers = auto
# threads = 0
# startup_timeout = 120

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

_BACKENDS = ("managed", "ollama", "openai")
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

    DEFAULT_PROVIDER = "managed"
    DEFAULT_BACKEND = DEFAULT_PROVIDER  # former name, kept for compatibility
    DEFAULT_URL = "http://localhost:11434"
    # The default model depends on the provider: an alias of the local store for "managed", an Ollama tag
    # otherwise (also sent to OpenAI-compatible servers, which mostly ignore it).
    DEFAULT_MODELS = {
        "managed": "coder-7b",
        "ollama": "qwen3-coder:30b-a3b-q4_K_M",
        "openai": "qwen3-coder:30b-a3b-q4_K_M",
    }
    DEFAULT_MODEL = DEFAULT_MODELS[DEFAULT_PROVIDER]
    DEFAULT_RUNTIME = "pinned"
    DEFAULT_RUNTIME_VARIANT = "auto"
    DEFAULT_N_CTX = 16384
    DEFAULT_N_GPU_LAYERS = "auto"
    DEFAULT_THREADS = 0
    DEFAULT_STARTUP_TIMEOUT = 120.0
    DEFAULT_MAX_DIFF_CHARS = 12_000
    DEFAULT_REFINE_PASSES = 0

    def __init__(self, path: str | None = None) -> None:
        self.path = path or default_config_path()
        self._cp = configparser.ConfigParser()
        if os.path.exists(self.path):
            self._cp.read(self.path)

    def _get(self, section: str, key: str, fallback):
        return self._cp.get(section, key, fallback=fallback)

    # ── LLM settings ──────────────────────────────────────────────────────────

    LEGACY_PROVIDER = "ollama"  # the default before the managed runtime existed

    @property
    def llm_provider(self) -> str:
        """The LLM provider: key ``provider``, else the former key ``backend``, else the default.

        A ``[llm]`` section that sets ``model`` or ``url`` without naming a provider was written for the former
        implicit default (Ollama): it keeps meaning Ollama, so that the switch of the default to ``managed``
        does not turn an Ollama model tag into a missing local file.
        """
        explicit = self._get("llm", "provider", self._get("llm", "backend", ""))
        if explicit:
            return explicit
        if self._get("llm", "model", "") or self._get("llm", "url", ""):
            return self.LEGACY_PROVIDER
        return self.DEFAULT_PROVIDER

    @property
    def llm_backend(self) -> str:
        """Former name of `llm_provider`, kept for compatibility."""
        return self.llm_provider

    @property
    def llm_url(self) -> str:
        return self._get("llm", "url", self.DEFAULT_URL)

    @property
    def llm_api_key_env(self) -> str:
        """Name of the environment variable holding the LLM API key ('' when not configured)."""
        return self._get("llm", "api_key_env", "")

    @property
    def llm_model(self) -> str:
        return self.llm_model_for(self.llm_provider)

    def llm_model_for(self, provider: str) -> str:
        """The configured model, else the default model of *provider*."""
        return self._get("llm", "model", self.DEFAULT_MODELS.get(provider, self.DEFAULT_MODEL))

    @property
    def llm_runtime(self) -> str:
        """Managed provider: ``pinned`` (installed by fobis), ``PATH`` or a path to llama-server."""
        return self._get("llm", "runtime", self.DEFAULT_RUNTIME)

    @property
    def llm_runtime_variant(self) -> str:
        return self._get("llm", "runtime_variant", self.DEFAULT_RUNTIME_VARIANT)

    @property
    def llm_n_ctx(self) -> int:
        return int(self._get("llm", "n_ctx", str(self.DEFAULT_N_CTX)))

    @property
    def llm_n_gpu_layers(self) -> str:
        return self._get("llm", "n_gpu_layers", self.DEFAULT_N_GPU_LAYERS)

    @property
    def llm_threads(self) -> int:
        return int(self._get("llm", "threads", str(self.DEFAULT_THREADS)))

    @property
    def llm_startup_timeout(self) -> float:
        return float(self._get("llm", "startup_timeout", str(self.DEFAULT_STARTUP_TIMEOUT)))

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
            f"  provider      = {self.llm_provider}",
            f"  url           = {self.llm_url}",
            f"  api_key_env   = {self.llm_api_key_env or '(none)'}",
            f"  model         = {self.llm_model}",
            f"  runtime       = {self.llm_runtime} (variant {self.llm_runtime_variant})",
            f"  n_ctx         = {self.llm_n_ctx}",
            f"  n_gpu_layers  = {self.llm_n_gpu_layers}",
            f"  threads       = {self.llm_threads}",
            f"  startup_timeout = {self.llm_startup_timeout:g}",
            f"  max_diff_chars= {self.llm_max_diff_chars}",
            f"  refine_passes = {self.llm_refine_passes}",
        ]
        return "\n".join(lines)
