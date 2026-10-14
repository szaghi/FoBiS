"""provenance.py — what produced a result: code, dependencies, compiler, flags, environment, machine.

Attached to every run result, so a difference between two results can be explained ("the compiler changed"),
and printed alone by ``fobis provenance``. Every probe of the environment is best effort: a missing tool gives an
empty field, never an error.
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

import configparser
import contextlib
import datetime
import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys

from .. import __version__

COMPILER_COMMANDS = {
    "gnu": "gfortran",
    "opencoarrays-gnu": "caf",
    "intel": "ifort",
    "intel_nextgen": "ifx",
    "nvfortran": "nvfortran",
    "pgi": "pgfortran",
    "lfortran": "lfortran",
    "amd": "amdflang",
    "nag": "nagfor",
    "ibm": "xlf2008_r",
    "g95": "g95",
}


def _run(args: list[str], cwd: str | None = None, timeout: float = 20, env: dict | None = None) -> tuple[int, str]:
    try:
        done = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout, errors="replace", env=env)
    except (OSError, subprocess.TimeoutExpired):
        return -1, ""
    return done.returncode, done.stdout + done.stderr


def compiler_version(command: str, env: dict | None = None) -> str:
    """The first line of ``COMMAND --version`` in *env* ('' when it cannot run)."""
    return _first_line([command, "--version"], env)


def _first_line(args: list[str], env: dict | None = None) -> str:
    """The first non-empty line printed by *args* in *env* ('' when the tool is missing or fails)."""
    path = (env if env is not None else os.environ).get("PATH")
    if not args or shutil.which(args[0], path=path) is None:
        return ""
    code, out = _run(args, env=env)
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    return lines[0] if code == 0 and lines else ""


SOURCE_EXTENSIONS = (".f", ".for", ".fpp", ".f77", ".f90", ".f95", ".f03", ".f08", ".inc", ".h", ".fi", ".cuf")


def _is_source(path: str) -> bool:
    name = os.path.basename(path).lower()
    return name.endswith(SOURCE_EXTENSIONS) or name.startswith("fobos")


def git_state(root: str) -> dict:
    """Commit, branch, dirty flag and a hash of the uncommitted change (empty outside a repository).

    Dirty means a tracked file changed or an untracked SOURCE exists (FoBiS compiles untracked sources, so they
    change results); untracked outputs (run directories, build products) do not count.
    """
    code, commit = _run(["git", "-C", root, "rev-parse", "HEAD"])
    if code != 0:
        return {}
    _, branch = _run(["git", "-C", root, "rev-parse", "--abbrev-ref", "HEAD"])
    _, status = _run(["git", "-C", root, "-c", "core.quotepath=off", "status", "--porcelain", "--untracked-files=all"])
    tracked = [line for line in status.splitlines() if line and not line.startswith("??")]
    untracked = sorted(line[3:] for line in status.splitlines() if line.startswith("??") and _is_source(line[3:]))
    state = {"commit": commit.strip(), "branch": branch.strip(), "dirty": bool(tracked or untracked)}
    if untracked:
        state["untracked_sources"] = untracked
    if state["dirty"]:
        digest = hashlib.sha256()
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            diff = ["git", "-C", root, "diff", "HEAD", "--no-color", "--no-ext-diff"]
            digest.update(subprocess.run(diff, capture_output=True, timeout=60).stdout)
        for path in untracked:
            try:
                with open(os.path.join(root, path), "rb") as handle:
                    digest.update(path.encode() + b"\0" + handle.read())
            except OSError:
                continue
        state["diff_sha256"] = digest.hexdigest()
    return state


def dependency_pins(lock_path: str) -> dict:
    """``name -> commit`` from a ``fobos.lock`` (empty when there is none)."""
    if not os.path.isfile(lock_path):
        return {}
    parser = configparser.RawConfigParser()
    try:
        parser.read(lock_path)
    except configparser.Error:
        return {}
    return {name: parser.get(name, "commit", fallback="") for name in parser.sections()}


def _cpu() -> str:
    try:
        with open("/proc/cpuinfo", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor()


def _gpus() -> list[str]:
    if shutil.which("nvidia-smi") is None:
        return []
    code, out = _run(["nvidia-smi", "-L"])
    return [line.strip() for line in out.splitlines() if line.strip().startswith("GPU")] if code == 0 else []


def collect(
    root: str,
    compiler: dict | None = None,
    mode: str | None = None,
    deps_dir: str = ".fobis_deps",
    mpi: bool = False,
    env: dict | None = None,
) -> dict:
    """The provenance of a result produced in the project at *root*.

    Parameters
    ----------
    root : str
        Project root.
    compiler : dict or None
        ``fobis introspect --compiler`` of the mode: name, binary, cflags, lflags, preproc.
    mode : str or None
        The fobos mode.
    deps_dir : str
        Fetched dependencies directory (its ``fobos.lock`` gives the pins).
    mpi : bool
        Also record the MPI launcher's version.
    env : dict or None
        The environment the program is built and run in (default: FoBiS's own).
    """
    environ = env if env is not None else os.environ
    compiler = dict(compiler or {})
    command = compiler.get("binary") or COMPILER_COMMANDS.get(compiler.get("name", ""), "")
    if command:
        compiler["command"] = command
        compiler["version"] = compiler_version(command, env)
        compiler["path"] = shutil.which(command, path=environ.get("PATH")) or command
    data = {
        "fobis": __version__,
        "date": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "git": git_state(root),
        "dependencies": dependency_pins(os.path.join(root, deps_dir, "fobos.lock")),
        "mode": mode or "",
        "compiler": compiler,
        "environment": {
            "modules": [m for m in environ.get("LOADEDMODULES", "").split(":") if m],
            "omp_num_threads": environ.get("OMP_NUM_THREADS", ""),
        },
        "machine": {
            "host": platform.node(),
            "os": f"{platform.system()} {platform.release()}",
            "cpu": _cpu(),
            "cores": os.cpu_count() or 0,
            "gpus": _gpus(),
            "python": sys.version.split()[0],
        },
    }
    if mpi:
        data["environment"]["mpi"] = _first_line(["mpirun", "--version"], env)
    return data


def _gpu_models(gpus: list) -> list:
    return [re.sub(r"\s*\(UUID:[^)]*\)", "", str(g)) for g in gpus]


def differences(old: dict, new: dict, prefix: str = "") -> list[str]:
    """What changed between two provenances that can change results (dates, hosts and job ids aside; GPUs by model,
    not by serial number): ``key: old -> new``."""
    ignored = {
        "date",
        "machine.host",
        "git.branch",
        "fobis",
        "rebuilt_because",
        "scheduler.job",
        "scheduler.node",
        "scheduler.state",
    }
    found = []
    for key in sorted(set(old) | set(new)):
        path = f"{prefix}{key}"
        if path in ignored:
            continue
        a, b = old.get(key), new.get(key)
        if path == "machine.gpus" and isinstance(a, list) and isinstance(b, list):
            a, b = _gpu_models(a), _gpu_models(b)
        if isinstance(a, dict | None) and isinstance(b, dict | None) and (a or b):  # a section on one side only:
            found += differences(a or {}, b or {}, f"{path}.")  # compared key by key
        elif a != b:
            found.append(f"{path}: {a!r} -> {b!r}")
    return found
