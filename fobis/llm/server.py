"""server.py — the lifecycle of one ``llama-server`` process: spawn, wait until ready, tear down.

The server listens on loopback only, on a free port, and requires a random API key generated per process, so
other users of a shared login node cannot use it. It runs in its own process group; `LlamaServer.stop` sends
SIGTERM, waits, then SIGKILL. Every live server is also stopped at interpreter exit and on SIGTERM, so a FoBiS
command never leaves an orphan behind. Readiness is ``GET /health`` answering 200 (503 while the model loads);
an exit or a timeout raises `ServerStartError` with the tail of the server log.
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

import atexit
import os
import re
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable

from .errors import ServerStartError
from .runtime import runtime_env

HOST = "127.0.0.1"
_LIVE: set[LlamaServer] = set()
_LOCK = threading.Lock()
_BIND_ERRORS = ("address already in use", "couldn't bind", "bind failed", "failed to bind")


def free_port() -> int:
    """A port free on loopback right now (the server may still lose a race for it: see `LlamaServer.start`)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((HOST, 0))
        return probe.getsockname()[1]


def _stop_all() -> None:
    with _LOCK:
        live = list(_LIVE)
    for server in live:
        server.stop()


atexit.register(_stop_all)


def _on_sigterm(signum, frame) -> None:
    _stop_all()
    sys.exit(128 + signum)


class LlamaServer:
    """One ``llama-server`` process.

    Parameters
    ----------
    binary : str
        Path of ``llama-server``.
    model : str
        Path of the GGUF file (first part of a split model).
    n_ctx : int
        Context size (``-c``); 0 lets llama.cpp use the model's.
    n_gpu_layers : str
        ``-ngl``: a number, ``auto`` or ``all``.
    threads : int
        ``-t``; 0 lets llama.cpp choose.
    startup_timeout : float
        Seconds to wait for ``/health`` = 200.
    log_path : str
        File receiving the server's stdout and stderr.
    extra_args : list of str
        Appended to the command line.
    popen : callable
        ``subprocess.Popen``; injectable for tests.
    """

    def __init__(
        self,
        binary: str,
        model: str,
        *,
        log_path: str,
        n_ctx: int = 16384,
        n_gpu_layers: str = "auto",
        threads: int = 0,
        startup_timeout: float = 120.0,
        extra_args: list[str] | None = None,
        popen: Callable = subprocess.Popen,
    ) -> None:
        self.binary = binary
        self.model = model
        self.log_path = log_path
        self.n_ctx = n_ctx
        self.n_gpu_layers = str(n_gpu_layers)
        self.threads = threads
        self.startup_timeout = startup_timeout
        self.extra_args = list(extra_args or [])
        self.popen = popen
        self.api_key = secrets.token_urlsafe(24)
        self.port = 0
        self.process: subprocess.Popen | None = None
        self._previous_sigterm = None

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self.port}"

    def command(self) -> list[str]:
        """The command line (the API key included: it is per process and local)."""
        cmd = [self.binary, "-m", self.model, "--host", HOST, "--port", str(self.port), "--api-key", self.api_key]
        cmd += ["-c", str(self.n_ctx), "-ngl", self.n_gpu_layers, "--parallel", "1", "--no-webui"]
        if self.threads > 0:
            cmd += ["-t", str(self.threads)]
        return cmd + self.extra_args

    def generation_speed(self) -> float | None:
        """Tokens per second of the last generation, read from the server log (None when not logged)."""
        try:
            with open(self.log_path, encoding="utf-8", errors="replace") as handle:
                found = re.findall(r"\beval time =.*?([0-9.]+) tokens per second", handle.read())
        except OSError:
            return None
        return float(found[-1]) if found else None

    def log_tail(self, lines: int = 20) -> str:
        """The last *lines* lines of the server log."""
        try:
            with open(self.log_path, encoding="utf-8", errors="replace") as handle:
                return "".join(handle.readlines()[-lines:]).rstrip()
        except OSError:
            return ""

    def _spawn(self) -> None:
        os.makedirs(os.path.dirname(self.log_path) or ".", exist_ok=True)
        with open(self.log_path, "w", encoding="utf-8") as log:
            self.process = self.popen(
                self.command(),
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=runtime_env(self.binary),
                start_new_session=os.name == "posix",
            )
        with _LOCK:
            _LIVE.add(self)
        if threading.current_thread() is threading.main_thread() and self._previous_sigterm is None:
            self._previous_sigterm = signal.signal(signal.SIGTERM, _on_sigterm)

    def _health(self) -> int:
        try:
            with urllib.request.urlopen(f"{self.url}/health", timeout=5) as response:
                return response.status
        except urllib.error.HTTPError as exc:
            return exc.code
        except (urllib.error.URLError, OSError):
            return 0

    def start(self, on_wait: Callable[[float], None] | None = None) -> LlamaServer:
        """Spawn the server and wait until it is ready.

        Raises
        ------
        ServerStartError
            The process exited (after up to 3 attempts when another process took the port meanwhile) or did
            not get ready within ``startup_timeout``.
        """
        for attempt in range(3):
            self.port = free_port()
            self._spawn()
            started = time.monotonic()
            while True:
                code = self.process.poll()
                if code is not None:
                    tail = self.log_tail()
                    self._forget()
                    if attempt < 2 and any(e in tail.lower() for e in _BIND_ERRORS):
                        break  # lost the port to another process: try a new one
                    raise ServerStartError(f"llama-server exited with status {code} while starting:\n{tail}")
                if self._health() == 200:
                    return self
                if time.monotonic() - started > self.startup_timeout:
                    tail = self.log_tail()
                    self.stop()
                    raise ServerStartError(
                        f"llama-server not ready after {self.startup_timeout:.0f} s (startup_timeout):\n{tail}"
                    )
                if on_wait:
                    on_wait(time.monotonic() - started)
                time.sleep(0.2)
        raise ServerStartError("llama-server could not bind a port (3 attempts)")

    def _forget(self) -> None:
        with _LOCK:
            _LIVE.discard(self)
        if self._previous_sigterm is not None and threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGTERM, self._previous_sigterm)
            self._previous_sigterm = None

    def stop(self, grace: float = 5.0) -> None:
        """Terminate the server (its whole process group), then kill it after *grace* seconds."""
        process = self.process
        if process is not None and process.poll() is None:
            try:
                if os.name == "posix":
                    os.killpg(process.pid, signal.SIGTERM)
                else:
                    process.terminate()
                process.wait(timeout=grace)
            except (subprocess.TimeoutExpired, ProcessLookupError, PermissionError):
                try:
                    if os.name == "posix":
                        os.killpg(process.pid, signal.SIGKILL)
                    else:
                        process.kill()
                    process.wait(timeout=grace)
                except (ProcessLookupError, PermissionError, subprocess.TimeoutExpired):
                    pass
        self._forget()

    def __enter__(self) -> LlamaServer:
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()
