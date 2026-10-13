"""case.py — runnable cases declared in the fobos: ``[case:NAME]`` sections.

A case says how to run something and what it produces::

    [case:sod]
    target     = src/app/sod.f90      ; built with the mode, then run (or: command = ./tools/run.sh --fast)
    mode       = gnu-release           ; default: the fobos default mode
    args       = input/sod.nml
    inputs     = input/sod.nml input/mesh.dat   ; copied into the run directory (files or directories)
    ranks      = 4                     ; MPI ranks (launcher in [verification], default "mpirun -np {ranks}")
    threads    = 2                     ; OMP_NUM_THREADS
    timeout    = 600                   ; seconds
    env        = SOD_DEBUG=0           ; more environment variables, one per line or space separated
    quantities =
        mass : regex stdout "total mass\\s*=\\s*(\\S+)"
        rho  : hdf5 output/sol.h5 /fields/rho

``$variables`` of the fobos are substituted as in the modes. ``[verification]`` holds project-wide settings:
``launcher`` (``{ranks}`` is replaced) and ``runs_dir`` (default ``.fobis/runs``).
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

import re
import shlex
from dataclasses import dataclass, field
from typing import Any

from .probes import Probe, ProbeError, parse_probes

SECTION_PREFIX = "case:"
DEFAULT_LAUNCHER = "mpirun -np {ranks}"
DEFAULT_RUNS_DIR = ".fobis/runs"
DEFAULT_TIMEOUT = 600.0
_KEYS = {
    "target",
    "command",
    "mode",
    "args",
    "inputs",
    "ranks",
    "threads",
    "timeout",
    "env",
    "quantities",
    "description",
}


class CaseError(Exception):
    """A case is declared incorrectly."""


@dataclass
class Case:
    """A runnable case: what to build or run, how, and the quantities it produces."""

    name: str
    target: str | None = None
    command: list[str] = field(default_factory=list)
    mode: str | None = None
    args: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    ranks: int = 0
    threads: int = 0
    timeout: float = DEFAULT_TIMEOUT
    env: dict[str, str] = field(default_factory=dict)
    probes: list[Probe] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "target": self.target,
            "command": self.command,
            "mode": self.mode,
            "args": self.args,
            "inputs": self.inputs,
            "ranks": self.ranks,
            "threads": self.threads,
            "timeout": self.timeout,
            "env": self.env,
            "quantities": [p.text for p in self.probes],
        }


@dataclass
class Settings:
    """Project-wide ``[verification]`` settings."""

    launcher: str = DEFAULT_LAUNCHER
    runs_dir: str = DEFAULT_RUNS_DIR


def _substitute(value: str, variables: dict[str, str]) -> str:
    for key, val in sorted(variables.items(), key=lambda kv: -len(kv[0])):
        value = re.sub(re.escape(key) + r"(?![A-Za-z0-9_])", lambda _m, v=val: v, value)
    return value


def _env(text: str, name: str) -> dict[str, str]:
    env = {}
    for item in shlex.split(text):
        key, sep, value = item.partition("=")
        if not sep or not key:
            raise CaseError(f"case {name}: env entry '{item}' is not KEY=VALUE")
        env[key] = value
    return env


def _number(text: str, name: str, key: str, kind=int):
    try:
        value = kind(text)
    except ValueError:
        raise CaseError(f"case {name}: {key} must be a number, not '{text}'") from None
    if value < 0:
        raise CaseError(f"case {name}: {key} must not be negative")
    return value


def parse_case(name: str, options: dict[str, str], variables: dict[str, str] | None = None) -> Case:
    """The case *name* from its section's *options*.

    Raises
    ------
    CaseError
        Unknown option, neither or both of target/command, a bad number, a bad quantity.
    """
    options = {k: _substitute(v, variables or {}) for k, v in options.items() if not k.startswith("$")}
    unknown = sorted(set(options) - _KEYS)
    if unknown:
        raise CaseError(f"case {name}: unknown option(s) {', '.join(unknown)} (known: {', '.join(sorted(_KEYS))})")
    if bool(options.get("target", "").strip()) == bool(options.get("command", "").strip()):
        raise CaseError(f"case {name}: give exactly one of target (a program to build) or command")
    try:
        probes = parse_probes(options.get("quantities", ""))
    except ProbeError as exc:
        raise CaseError(f"case {name}: {exc}") from exc
    try:
        command = shlex.split(options.get("command", ""))
        args = shlex.split(options.get("args", ""))
    except ValueError as exc:
        raise CaseError(f"case {name}: {exc}") from exc
    return Case(
        name=name,
        target=options.get("target", "").strip() or None,
        command=command,
        mode=options.get("mode", "").strip() or None,
        args=args,
        inputs=options.get("inputs", "").split(),
        ranks=_number(options.get("ranks", "0") or "0", name, "ranks"),
        threads=_number(options.get("threads", "0") or "0", name, "threads"),
        timeout=_number(options.get("timeout", str(DEFAULT_TIMEOUT)) or str(DEFAULT_TIMEOUT), name, "timeout", float),
        env=_env(options.get("env", ""), name),
        probes=probes,
        description=" ".join(options.get("description", "").split()),
    )


def load_cases(fobos: Any) -> dict[str, Case]:
    """Every ``[case:NAME]`` of a parsed `fobis.Fobos.Fobos` (its ``$variables`` substituted), by name.

    Raises
    ------
    CaseError
        A case is declared incorrectly.
    """
    parser = getattr(fobos, "fobos", None)
    if parser is None:
        return {}
    variables = getattr(fobos, "local_variables", {}) or {}
    cases = {}
    for section in parser.sections():
        if section.startswith(SECTION_PREFIX):
            name = section[len(SECTION_PREFIX) :].strip()
            cases[name] = parse_case(name, dict(parser.items(section)), variables)
    return cases


def load_settings(fobos: Any) -> Settings:
    """The ``[verification]`` settings of a parsed fobos (defaults when absent)."""
    parser = getattr(fobos, "fobos", None)
    settings = Settings()
    if parser is not None and parser.has_section("verification"):
        settings.launcher = parser.get("verification", "launcher", fallback=settings.launcher).strip()
        settings.runs_dir = parser.get("verification", "runs_dir", fallback=settings.runs_dir).strip()
    return settings
