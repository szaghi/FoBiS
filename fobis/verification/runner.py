"""runner.py — build and run a case, extract its quantities, record its provenance.

`LocalRunner` builds the case's program with FoBiS (``fobis build --target --json`` in the project, with the
case's mode), runs it in a fresh run directory (``<runs_dir>/<case>/<variant>/``, the declared inputs copied in),
with the MPI launcher when the case has ranks, ``OMP_NUM_THREADS`` when it has threads, and a timeout that kills
the whole process group. The result (`RunResult`) holds the quantities, the probe errors, the tails of the output,
the build's diagnoses when it failed, and the provenance. A scheduler runner (Slurm, phase V10) implements the
same ``run(case, variant)``.
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

import contextlib
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from . import provenance as prov
from .case import DEFAULT_LAUNCHER, Case
from .probes import Quantity, RunOutput, extract

TAIL_LINES = 40
STATUSES = ("ok", "failed", "timeout", "build-failed", "probe-error", "error")
_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass
class RunResult:
    """The outcome of one run of a case.

    ``status``: ``ok`` (exit 0, every quantity found), ``probe-error`` (exit 0, some quantity missing), ``failed``
    (non-zero exit), ``timeout``, ``build-failed`` (with ``build``: the ``build --json`` document) or ``error``
    (the program could not be started, an input is missing).
    """

    case: str
    variant: str
    status: str
    exit_code: int | None = None
    elapsed: float = 0.0
    command: list[str] = field(default_factory=list)
    rundir: str = ""
    quantities: list[Quantity] = field(default_factory=list)
    probe_errors: dict[str, str] = field(default_factory=dict)
    stdout: str = ""
    stderr: str = ""
    build: dict | None = None
    provenance: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def quantity(self, name: str) -> Quantity | None:
        return next((q for q in self.quantities if q.name == name), None)

    def to_dict(self) -> dict:
        data = {
            "case": self.case,
            "variant": self.variant,
            "status": self.status,
            "exit_code": self.exit_code,
            "elapsed": round(self.elapsed, 3),
            "command": self.command,
            "rundir": self.rundir,
            "quantities": {q.name: q.to_dict() for q in self.quantities},
            "probe_errors": self.probe_errors,
            "stdout": _tail(self.stdout),
            "stderr": _tail(self.stderr),
            "provenance": self.provenance,
        }
        if self.build is not None:
            data["build"] = self.build
        return data


@dataclass(frozen=True)
class BuildVariant:
    """Flags appended to the mode's for one variant of an ensemble; its objects in their own directory."""

    name: str
    cflags: str = ""
    lflags: str = ""

    def args(self) -> list[str]:
        args = ["--variant", self.name]
        if self.cflags:
            args += ["--variant-cflags", self.cflags]
        if self.lflags:
            args += ["--variant-lflags", self.lflags]
        return args


def _tail(text: str) -> str:
    return "\n".join(text.splitlines()[-TAIL_LINES:])


def _parse_json(text: str) -> dict | None:
    start = text.find("{")
    if start < 0:
        return None
    try:
        data = json.loads(text[start:])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


class LocalRunner:
    """Run cases on this machine.

    Parameters
    ----------
    root : str
        Project root (where the fobos is).
    fobos_args : list of str
        ``-f FILE`` / ``--fci`` to pass to the nested ``fobis`` commands.
    runs_dir : str
        Where run directories and built programs go (relative to *root*).
    launcher : str
        MPI launcher, ``{ranks}`` replaced (used when a case has ranks).
    deps_dir : str
        Fetched dependencies directory (provenance pins).
    run : callable
        ``subprocess.run`` (replaceable in tests) for the nested ``fobis`` commands.
    shadow : str or None
        Build the cases' programs as this shadow of their mode (``checks``, ``sanitize``, ``strict``).
    env : dict or None
        Environment of the builds and runs (default: FoBiS's own), e.g. after a ``module load``.
    variant : BuildVariant or None
        Flags appended to the mode's, objects in the variant's directory (``fobis assess``).
    """

    def __init__(
        self,
        root: str = ".",
        fobos_args: list[str] | None = None,
        runs_dir: str = ".fobis/runs",
        launcher: str = DEFAULT_LAUNCHER,
        deps_dir: str = ".fobis_deps",
        run=subprocess.run,
        shadow: str | None = None,
        env: dict | None = None,
        variant: BuildVariant | None = None,
    ) -> None:
        self.root = os.path.abspath(root)
        self.fobos_args = list(fobos_args or [])
        self.runs_dir = os.path.join(self.root, runs_dir)
        self.launcher = launcher
        self.deps_dir = deps_dir
        self._run = run
        self.shadow = shadow
        self.env = env
        self.variant = variant
        self._compilers: dict[str, dict] = {}

    def _fobis(self, args: list[str], timeout: float = 3600) -> subprocess.CompletedProcess:
        from ..mcp_server import fobis_command

        return self._run(
            [*fobis_command(), *args, *self.fobos_args],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=self.env,
        )

    def _mode_args(self, mode: str | None) -> list[str]:
        args = (["--mode", mode] if mode else []) + (["--shadow", self.shadow] if self.shadow else [])
        return args + (self.variant.args() if self.variant else [])

    def introspect(self, mode: str | None) -> dict:
        """``fobis introspect --compiler --buildoptions`` of *mode* (memoised): the effective mode included."""
        key = mode or ""
        if key not in self._compilers:
            try:
                done = self._fobis(["introspect", "--compiler", "--buildoptions", *self._mode_args(mode)], timeout=120)
                self._compilers[key] = _parse_json(done.stdout) or {}
            except (OSError, subprocess.TimeoutExpired):
                self._compilers[key] = {}
        return self._compilers[key]

    def provenance(self, case: Case, mode: str | None) -> dict:
        facts = self.introspect(mode) if case.target else {}
        effective = facts.get("buildoptions", {}).get("mode") or mode
        data = prov.collect(
            self.root, facts.get("compiler", {}), effective, self.deps_dir, mpi=case.ranks > 0, env=self.env
        )
        if self.shadow:
            data["shadow"] = self.shadow
        if self.variant:
            data["variant"] = {"name": self.variant.name, "cflags": self.variant.cflags, "lflags": self.variant.lflags}
        return data

    def signature(self, mode: str | None) -> dict:
        """What the objects of *mode* must have been built with: resolved compiler, its version, the flags."""
        compiler = dict(self.introspect(mode).get("compiler", {}))
        command = compiler.get("binary") or prov.COMPILER_COMMANDS.get(compiler.get("name", ""), "")
        path = (self.env if self.env is not None else os.environ).get("PATH")
        compiler["path"] = shutil.which(command, path=path) or command if command else ""
        compiler["version"] = prov.compiler_version(command, self.env) if command else ""
        return compiler

    def _objects_state(self, mode: str | None) -> str:
        """A digest of the mode's object files (names, sizes, times): another build in between changes it."""
        options = self.introspect(mode).get("buildoptions", {})
        obj_dir = os.path.join(self.root, options.get("build_dir", "./"), options.get("obj_dir", "./obj/"))
        digest = hashlib.sha256()
        for folder, _, files in sorted(os.walk(obj_dir)):
            for name in sorted(files):
                with contextlib.suppress(OSError):
                    info = os.stat(os.path.join(folder, name))
                    digest.update(f"{folder}/{name}:{info.st_size}:{info.st_mtime_ns}\n".encode())
        return digest.hexdigest()

    def build(self, case: Case, mode: str | None) -> tuple[str | None, dict]:
        """Build the case's target: (path of the program or None, the ``build --json`` document).

        The objects are recompiled from scratch (``--force-compile``) when the runner has no record of how they were
        built, when the compiler or the flags changed since (a ``module load`` of another compiler with the same
        command name included: FoBiS's timestamps would keep the old objects), or when another build touched the
        object directory in between. The reason is in the document's ``rebuilt_because``.
        """
        if not os.path.isfile(os.path.join(self.root, case.target)):
            return None, {"status": "error", "errors": [f"target {case.target} does not exist"]}
        name = f"{case.name}-{mode or 'default'}" + (f"-{self.shadow}" if self.shadow else "")
        name += f"-{self.variant.name}" if self.variant else ""
        binary = os.path.join(self.runs_dir, "bin", _SAFE.sub("_", name))
        os.makedirs(os.path.dirname(binary), exist_ok=True)
        record_path = binary + ".signature.json"
        signature = self.signature(mode)
        record = {}
        with contextlib.suppress(OSError, ValueError), open(record_path, encoding="utf-8") as handle:
            record = json.load(handle)
        reason = ""
        if not record:
            reason = "no record of how the objects were built"
        elif record.get("signature") != signature:
            changed = sorted(
                k
                for k in set(signature) | set(record.get("signature", {}))
                if signature.get(k) != record.get("signature", {}).get(k)
            )
            reason = "the compiler or its flags changed (" + ", ".join(changed) + ")"
        elif record.get("objects") != self._objects_state(mode):
            reason = "another build changed the objects since"
        args = ["build", "--json", "--target", case.target, "--output", binary, *self._mode_args(mode)]
        if reason:
            args.append("--force-compile")
        try:
            done = self._fobis(args)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return None, {"status": "error", "errors": [str(exc)]}
        report = _parse_json(done.stdout) or {"status": "error", "errors": (done.stdout + done.stderr).splitlines()}
        if reason:
            report["rebuilt_because"] = reason
        if done.returncode != 0 or not os.path.isfile(binary):
            report["status"] = "error"
            if not report.get("errors") and not report.get("diagnostics"):
                report["errors"] = [f"{case.target} was not built (is it among the mode's sources?)"]
            with contextlib.suppress(OSError):
                os.remove(record_path)  # the objects are in an unknown state
            return None, report
        with open(record_path, "w", encoding="utf-8") as handle:
            json.dump({"signature": signature, "objects": self._objects_state(mode)}, handle, indent=1)
        return binary, report

    def _rundir(self, case: Case, variant: str) -> str:
        rundir = os.path.join(self.runs_dir, _SAFE.sub("_", case.name), _SAFE.sub("_", variant))
        if os.path.isdir(rundir):
            shutil.rmtree(rundir)  # FoBiS's own run directory, recreated for every run
        os.makedirs(rundir)
        for item in case.inputs:
            source = os.path.normpath(os.path.join(self.root, item))
            relative = os.path.relpath(source, self.root)
            if relative.startswith(os.pardir):  # outside the project: copied by its name
                relative = os.path.basename(source)
            target = os.path.join(rundir, relative)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            if os.path.isdir(source):
                shutil.copytree(source, target, symlinks=True)
            elif os.path.isfile(source):
                shutil.copy2(source, target)
            else:
                raise FileNotFoundError(f"input {item} of case {case.name} not found")
        return rundir

    def command(self, case: Case, program: list[str]) -> list[str]:
        launcher = shlex.split(self.launcher.replace("{ranks}", str(case.ranks))) if case.ranks else []
        return [*launcher, *program, *case.args]

    def run(
        self,
        case: Case,
        variant: str = "default",
        mode: str | None = None,
        binary: str | None = None,
        prepare: Callable[[str], None] | None = None,
        provenance: dict | None = None,
    ) -> RunResult:
        """Build (for a target) and run *case*; *mode* overrides the case's own mode.

        *binary*: a program already built for this case (no build); *prepare*: called with the run directory once
        the inputs are copied (an ensemble edits them there); *provenance*: the provenance to record (collected
        when None).
        """
        mode = mode or case.mode
        recorded = dict(provenance) if provenance is not None else self.provenance(case, mode)
        result = RunResult(case.name, variant, "error", provenance=recorded)
        if binary:
            program = [binary]
        elif case.target:
            binary, report = self.build(case, mode)
            if binary is None:
                result.status, result.build = "build-failed", report
                return result
            program = [binary]
            if report.get("rebuilt_because"):
                result.provenance["rebuilt_because"] = report["rebuilt_because"]
        else:
            program = list(case.command)
            if program and os.sep in program[0] and not os.path.isabs(program[0]):
                program[0] = os.path.join(self.root, program[0])  # a project script, relative to the root
        try:
            result.rundir = self._rundir(case, variant)
            if prepare is not None:
                prepare(result.rundir)
        except (OSError, ValueError) as exc:
            result.stderr = str(exc)
            return result
        result.command = self.command(case, program)
        env = {**(self.env if self.env is not None else os.environ), **case.env}
        if case.threads:
            env["OMP_NUM_THREADS"] = str(case.threads)
        output = self._execute(result, env, case.timeout)
        with open(os.path.join(result.rundir, "stdout.txt"), "w", encoding="utf-8") as handle:
            handle.write(result.stdout)
        with open(os.path.join(result.rundir, "stderr.txt"), "w", encoding="utf-8") as handle:
            handle.write(result.stderr)
        if output is None:
            return result
        result.quantities, result.probe_errors = extract(case.probes, output)
        if result.exit_code != 0:
            result.status = "failed"
        else:
            result.status = "probe-error" if result.probe_errors else "ok"
        return result

    @staticmethod
    def _execute(result: RunResult, env: dict, timeout: float) -> RunOutput | None:
        start = time.monotonic()
        try:
            proc = subprocess.Popen(
                result.command,
                cwd=result.rundir,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                errors="replace",
                start_new_session=True,  # its own process group: a timeout kills the launcher's children too
            )
        except OSError as exc:
            result.status, result.stderr = "error", f"cannot start {result.command[0]}: {exc}"
            return None
        try:
            stdout, stderr = proc.communicate(timeout=timeout or None)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            stdout, stderr = proc.communicate()
            result.elapsed = time.monotonic() - start
            result.status, result.stdout, result.stderr = "timeout", stdout, stderr + f"\nTIMEOUT after {timeout:g} s"
            return None
        result.elapsed = time.monotonic() - start
        result.exit_code, result.stdout, result.stderr = proc.returncode, stdout, stderr
        return RunOutput(result.rundir, stdout, stderr, proc.returncode)
