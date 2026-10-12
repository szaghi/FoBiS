"""runtime.py — the llama.cpp runtime: install the pinned ``llama-server`` build, list, remove, locate it.

Installed builds live in ``<root>/runtime/<build>-<variant>/`` (``root`` = ``$FOBIS_LLM_DIR`` or ``~/.fobis/llm``),
each with a ``runtime.json`` recording the build, variant, binary path and the sha256 of the archives. An
install downloads the release archive (plus the CUDA runtime archive for CUDA variants), verifies it against
the digest pinned in `fobis.llm.pins`, extracts it without shelling out (path-traversal checks on every member)
and runs ``llama-server --version``.

The configured runtime can also be ``PATH`` (the ``llama-server`` found on PATH) or an absolute path: the escape
hatch for systems whose glibc is older than the release binaries need, or that provide a site-built llama.cpp.
Nothing is installed implicitly: a missing runtime raises `RuntimeMissingError` with the command to run.
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

import hashlib
import http.client
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import tarfile
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import dataclass

from .errors import ChecksumMismatchError, ConfigError, DownloadError, RuntimeMissingError
from .models import CHUNK, Progress, default_root
from .pins import ASSETS, PINNED_BUILD, Asset, asset_url

VARIANTS = ("cpu", "metal", "cuda12", "cuda13", "vulkan", "rocm", "sycl")
_ARCH = {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "aarch64", "arm64": "arm64"}
_CUDA_RE = re.compile(r"CUDA Version:\s*(\d+)\.(\d+)")


def platform_key(system: str | None = None, machine: str | None = None) -> tuple[str, str]:
    """(os, arch) as used by the pin table: ``linux``/``darwin``/``windows``; Windows x86_64 is ``amd64``."""
    os_name = (system or platform.system()).lower()
    raw = (machine or platform.machine()).lower()
    arch = _ARCH.get(raw, raw)
    if os_name == "windows" and arch == "x86_64":
        arch = "amd64"
    if os_name == "linux" and arch == "arm64":
        arch = "aarch64"
    if os_name == "darwin" and arch == "aarch64":
        arch = "arm64"
    return os_name, arch


def available_variants(key: tuple[str, str] | None = None) -> list[str]:
    """The variants pinned for the platform *key* (current platform when None)."""
    key = key or platform_key()
    return [v for v in VARIANTS if (key[0], key[1], v) in ASSETS]


def detect_variant(
    key: tuple[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
    run: Callable = subprocess.run,
) -> tuple[str, str]:
    """(variant, reason): CUDA when an NVIDIA driver is present, Metal on Apple silicon, otherwise CPU."""
    key = key or platform_key()
    variants = available_variants(key)
    if not variants:
        raise ConfigError(f"no llama.cpp build is pinned for {key[0]}/{key[1]}: set 'runtime = /path/to/llama-server'")
    if "metal" in variants:
        return "metal", "Apple silicon: Metal build"
    smi = which("nvidia-smi")
    if smi:
        try:
            output = run([smi], capture_output=True, text=True, timeout=20).stdout
        except (OSError, subprocess.SubprocessError):
            output = ""
        match = _CUDA_RE.search(output or "")
        if match:
            major = int(match.group(1))
            for variant in ("cuda13", "cuda12"):
                if variant in variants and int(variant[4:]) <= major:
                    return variant, f"NVIDIA driver supports CUDA {match.group(1)}.{match.group(2)}"
    return "cpu", "no supported GPU driver found"


@dataclass(frozen=True)
class InstalledRuntime:
    """An installed llama.cpp build."""

    build: str
    variant: str
    binary: str
    directory: str
    version: str = ""

    @property
    def name(self) -> str:
        return f"{self.build}-{self.variant}"


def runtime_env(binary: str) -> dict[str, str]:
    """Environment for running *binary*: its directory first in the shared-library search path (the release
    archives ship their libraries, and the CUDA runtime, next to the executable)."""
    env = dict(os.environ)
    directory = os.path.dirname(os.path.abspath(binary))
    var = {"linux": "LD_LIBRARY_PATH", "darwin": "DYLD_LIBRARY_PATH"}.get(platform.system().lower())
    if var:
        env[var] = os.pathsep.join(p for p in (directory, env.get(var, "")) if p)
    return env


def server_version(binary: str, run: Callable = subprocess.run) -> str:
    """The ``--version`` banner of *binary* ('' when it cannot run)."""
    try:
        done = run([binary, "--version"], capture_output=True, text=True, timeout=60, env=runtime_env(binary))
    except (OSError, subprocess.SubprocessError):
        return ""
    match = re.search(r"version:.*", (done.stdout or "") + (done.stderr or ""))
    return match.group(0).strip() if match else ""


def _download(
    url: str,
    dest: str,
    expected: str | None,
    progress: Progress | None,
    urlopen: Callable,
    timeout: float = 60.0,
) -> str:
    """Download *url* to *dest*; returns the sha256. With *expected* a mismatch deletes the file and raises."""
    digest = hashlib.sha256()
    name = os.path.basename(dest)
    request = urllib.request.Request(url, headers={"User-Agent": "fobis-llm"})
    done = total = 0
    try:
        with urlopen(request, timeout=timeout) as response, open(dest + ".part", "wb") as handle:
            total = int(response.headers.get("Content-Length") or 0)
            for block in iter(lambda: response.read(CHUNK), b""):
                handle.write(block)
                digest.update(block)
                done += len(block)
                if progress:
                    progress(name, done, total or done)
    except urllib.error.HTTPError as exc:
        raise DownloadError(f"{url}: HTTP {exc.code} {exc.reason}") from exc
    except (urllib.error.URLError, http.client.HTTPException, OSError) as exc:
        raise DownloadError(f"cannot download {url}: {getattr(exc, 'reason', exc)}") from exc
    if total and done < total:
        os.remove(dest + ".part")
        raise DownloadError(f"{url}: download interrupted after {done} of {total} bytes; install again")
    sha = digest.hexdigest()
    if expected and sha != expected:
        os.remove(dest + ".part")
        raise ChecksumMismatchError(f"{name}: sha256 {sha[:16]}... does not match the pinned {expected[:16]}...")
    os.replace(dest + ".part", dest)
    return sha


def _safe_target(root: str, name: str) -> None:
    """Raise unless *name* (an archive member or link target) stays inside *root*."""
    target = os.path.realpath(os.path.join(root, name))
    if os.path.isabs(name) or not (target == root or target.startswith(root + os.sep)):
        raise DownloadError(f"refusing to extract {name!r}: it points outside the runtime directory")


def _extract(archive: str, dest: str) -> None:
    """Extract *archive* (.zip or .tar.gz) into *dest*, rejecting members that escape it."""
    root = os.path.realpath(dest)
    if archive.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            for member in zf.infolist():
                _safe_target(root, member.filename)
            zf.extractall(root)
        return
    with tarfile.open(archive, "r:gz") as tf:
        members = tf.getmembers()
        for member in members:
            _safe_target(root, member.name)
            if member.issym():
                _safe_target(root, os.path.join(os.path.dirname(member.name), member.linkname))
            elif member.islnk():
                _safe_target(root, member.linkname)
            elif not (member.isfile() or member.isdir()):
                raise DownloadError(f"refusing to extract {member.name!r}: not a regular file, link or directory")
        if hasattr(tarfile, "data_filter"):
            tf.extractall(root, members=members, filter="data")
        else:  # Python without extraction filters: every member was checked above
            tf.extractall(root, members=members)


def _flatten(directory: str) -> None:
    """Move the contents of a single top-level subdirectory of *directory* up into it."""
    entries = os.listdir(directory)
    if len(entries) == 1 and os.path.isdir(os.path.join(directory, entries[0])):
        inner = os.path.join(directory, entries[0])
        for name in os.listdir(inner):
            os.replace(os.path.join(inner, name), os.path.join(directory, name))
        os.rmdir(inner)


def _binary_in(directory: str) -> str | None:
    for name in ("llama-server", "llama-server.exe"):
        path = os.path.join(directory, name)
        if os.path.isfile(path):
            return path
    return None


class RuntimeManager:
    """Installed llama.cpp builds under ``<root>/runtime``.

    Parameters
    ----------
    root : str or None
        LLM directory (`fobis.llm.models.default_root` when None).
    key : tuple or None
        Platform (os, arch); the current one when None.
    urlopen, run : callable
        Injected for tests (``urllib.request.urlopen``, ``subprocess.run``).
    """

    def __init__(
        self,
        root: str | None = None,
        key: tuple[str, str] | None = None,
        urlopen: Callable = urllib.request.urlopen,
        run: Callable = subprocess.run,
    ) -> None:
        self.root = os.path.join(root or default_root(), "runtime")
        self.key = key or platform_key()
        self.urlopen = urlopen
        self.run = run

    def installed(self) -> list[InstalledRuntime]:
        """The installed builds, sorted by name."""
        found: list[InstalledRuntime] = []
        if not os.path.isdir(self.root):
            return found
        for name in sorted(os.listdir(self.root)):
            try:
                with open(os.path.join(self.root, name, "runtime.json"), encoding="utf-8") as handle:
                    meta = json.load(handle)
            except (OSError, ValueError):
                continue
            found.append(
                InstalledRuntime(
                    build=meta["build"],
                    variant=meta["variant"],
                    binary=os.path.join(self.root, name, meta["binary"]),  # relative: the directory can move
                    directory=os.path.join(self.root, name),
                    version=meta.get("version", ""),
                )
            )
        return found

    def install(
        self,
        variant: str | None = None,
        build: str | None = None,
        sha256: str | None = None,
        trust: bool = False,
        progress: Progress | None = None,
    ) -> tuple[InstalledRuntime, str]:
        """Install a build; returns (runtime, how the variant was chosen).

        Parameters
        ----------
        variant : str or None
            One of `available_variants`; detected when None or ``auto``.
        build : str or None
            A llama.cpp build tag (``b11308``); the pinned build when None.
        sha256 : str or None
            Expected sha256 of the main archive of a build that is not pinned.
        trust : bool
            Accept a non-pinned build without a known sha256 (trust on first use: the computed hash is
            recorded).

        Raises
        ------
        ConfigError
            Unknown variant for the platform, or a non-pinned build without ``sha256``/``trust``.
        DownloadError, ChecksumMismatchError
            Download or verification failure; nothing is left installed.
        """
        if variant in (None, "", "auto"):
            variant, reason = detect_variant(self.key, run=self.run)
        else:
            reason = "requested"
        entry = ASSETS.get((*self.key, variant))
        if entry is None:
            choices = ", ".join(available_variants(self.key)) or "none"
            raise ConfigError(f"no '{variant}' build for {self.key[0]}/{self.key[1]} (available: {choices})")
        build = build or PINNED_BUILD
        main, cudart = entry
        if build != PINNED_BUILD:
            if not sha256 and not trust:
                raise ConfigError(
                    f"build {build} is not pinned by this FoBiS: pass --sha256 <hash of the archive> or --trust"
                )
            if cudart is not None and not trust:
                raise ConfigError(f"build {build} with {variant} also needs the CUDA runtime archive: pass --trust")
            main = Asset(main.name.replace(PINNED_BUILD, build), sha256 or "")
            cudart = Asset(cudart.name.replace(PINNED_BUILD, build), "") if cudart else None
        directory = os.path.join(self.root, f"{build}-{variant}")
        staging = directory + ".installing"
        shutil.rmtree(staging, ignore_errors=True)
        os.makedirs(staging)
        recorded = []
        try:
            for index, asset in enumerate(a for a in (main, cudart) if a is not None):
                archive = os.path.join(staging, asset.name)
                sha = _download(asset_url(build, asset.name), archive, asset.sha256 or None, progress, self.urlopen)
                unpack = os.path.join(staging, f".unpack{index}")
                os.makedirs(unpack)
                _extract(archive, unpack)
                _flatten(unpack)
                for entry_name in os.listdir(unpack):
                    os.replace(os.path.join(unpack, entry_name), os.path.join(staging, entry_name))
                os.rmdir(unpack)
                os.remove(archive)
                recorded.append({"name": asset.name, "sha256": sha, "pinned": bool(asset.sha256)})
            binary = _binary_in(staging)
            if binary is None:
                raise DownloadError(f"{main.name} contains no llama-server executable")
            os.chmod(binary, os.stat(binary).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            shutil.rmtree(directory, ignore_errors=True)
            os.replace(staging, directory)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        binary = _binary_in(directory)
        version = server_version(binary, self.run)
        meta = {
            "build": build,
            "variant": variant,
            "binary": os.path.basename(binary),
            "assets": recorded,
            "installed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "version": version,
        }
        with open(os.path.join(directory, "runtime.json"), "w", encoding="utf-8") as handle:
            json.dump(meta, handle, indent=2)
            handle.write("\n")
        return InstalledRuntime(build, variant, binary, directory, version), reason

    def remove(self, name: str) -> InstalledRuntime:
        """Delete the installed build *name* (``<build>-<variant>``)."""
        for runtime in self.installed():
            if runtime.name == name:
                shutil.rmtree(runtime.directory)
                return runtime
        raise RuntimeMissingError(f"no installed runtime named {name!r} (see: fobis llm runtime list)")

    def resolve(self, runtime: str = "pinned", variant: str = "auto") -> str:
        """Path of the ``llama-server`` to run for the configured *runtime* and *variant*.

        ``pinned``: the installed pinned build (the requested variant; with ``auto``, the detected variant
        when installed, else any installed variant of the pinned build). ``PATH``: ``llama-server`` on PATH.
        Anything else: a path to the executable.

        Raises
        ------
        RuntimeMissingError
            Nothing suitable is installed or found; the message gives the command to run.
        """
        if runtime == "PATH":
            found = shutil.which("llama-server")
            if not found:
                raise RuntimeMissingError("runtime = PATH, but no llama-server is on PATH")
            return found
        if runtime not in ("", "pinned"):
            path = os.path.abspath(os.path.expanduser(runtime))
            if not (os.path.isfile(path) and os.access(path, os.X_OK)):
                raise RuntimeMissingError(f"runtime = {runtime}: not an executable file")
            return path
        pinned = [r for r in self.installed() if r.build == PINNED_BUILD and os.path.isfile(r.binary)]
        if variant not in ("", "auto"):
            pinned = [r for r in pinned if r.variant == variant]
        elif len(pinned) > 1:
            detected, _ = detect_variant(self.key, run=self.run)
            pinned.sort(key=lambda r: r.variant != detected)
        if not pinned:
            wanted = "" if variant in ("", "auto") else f" --variant {variant}"
            raise RuntimeMissingError(
                f"the llama.cpp runtime ({PINNED_BUILD}) is not installed: run 'fobis llm runtime install{wanted}'"
            )
        return pinned[0].binary
