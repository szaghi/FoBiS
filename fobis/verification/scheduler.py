"""scheduler.py — running cases and tests through a batch scheduler (phase V10 of PLAN-verification.md).

On a cluster, programs are built on the login node and run on compute nodes. `SlurmRunner` is a `LocalRunner`
whose runs are Slurm jobs: a job script written into the case's run directory (resources from the case — ranks,
threads, GPUs, timeout — and from ``[scheduler]``), ``sbatch``, ``squeue`` until the job leaves the queue, ``sacct``
for its final state, then the same probes on the same files: the result is the same `RunResult`. The job script
records the command's own exit status and wall time, so the result does not depend on the accounting database.
The run directory must be on a file system the compute nodes share (the project's own, usually).

The login-node guard: a host matching ``[scheduler] login_nodes`` refuses to run an MPI or GPU case itself.
"""

from __future__ import annotations

import configparser
import contextlib
import fnmatch
import math
import os
import platform
import shlex
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .case import Case, CaseError
from .probes import RunOutput
from .runner import LocalRunner, RunResult

KINDS = ("slurm",)
_KEYS = {"kind", "partition", "account", "qos", "options", "launcher", "setup", "poll", "login_nodes"}
EXIT_FILE, STDOUT_FILE, STDERR_FILE, HOST_FILE, SCRIPT_FILE = (
    "fobis-exit.txt",
    "fobis-stdout.txt",
    "fobis-stderr.txt",
    "fobis-host.txt",
    "fobis-job.sh",
)


class SchedulerError(CaseError):
    """The scheduler is declared incorrectly, or a job could not be submitted."""


@dataclass
class SchedulerConfig:
    """``[scheduler]`` of the user config, then of the fobos (the project's keys win)."""

    kind: str = "slurm"
    partition: str = ""
    account: str = ""
    qos: str = ""
    options: list[str] = field(default_factory=list)  # more ``#SBATCH`` options, one per line
    launcher: str = "srun"  # how a ranked case is launched inside the job ({ranks} replaced)
    setup: list[str] = field(default_factory=list)  # shell lines run in the job before the program
    poll: float = 10.0
    login_nodes: list[str] = field(default_factory=list)  # host name patterns


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def load_config(fobos: Any = None, user_config: str | None = None) -> SchedulerConfig:
    """The scheduler settings: the user config's ``[scheduler]`` (machine-wide: partition, account, login nodes),
    then the fobos's (project-specific), key by key."""
    from ..UserConfig import default_config_path

    items: dict[str, str] = {}
    user = configparser.ConfigParser()
    with contextlib.suppress(configparser.Error):
        user.read(user_config or default_config_path())
    if user.has_section("scheduler"):
        items.update(user.items("scheduler"))
    parser = getattr(fobos, "fobos", None)
    if parser is not None and parser.has_section("scheduler"):
        items.update(parser.items("scheduler"))
    unknown = sorted(set(items) - _KEYS)
    if unknown:
        raise SchedulerError(f"[scheduler]: unknown key(s) {', '.join(unknown)} (known: {', '.join(sorted(_KEYS))})")
    config = SchedulerConfig()
    config.kind = items.get("kind", config.kind).strip().lower()
    if config.kind not in KINDS:
        raise SchedulerError(f"[scheduler] kind {config.kind!r} is not supported (supported: {', '.join(KINDS)})")
    for key in ("partition", "account", "qos"):
        setattr(config, key, items.get(key, "").strip())
    config.launcher = items.get("launcher", config.launcher).strip() or config.launcher
    config.options = _lines(items.get("options", ""))
    config.setup = _lines(items.get("setup", ""))
    config.login_nodes = items.get("login_nodes", "").replace(",", " ").split()
    try:
        config.poll = float(items.get("poll", config.poll))
    except ValueError as exc:
        raise SchedulerError(f"[scheduler] poll: {exc}") from exc
    return config


def on_login_node(config: SchedulerConfig, host: str | None = None) -> str:
    """The host name when it matches a declared login-node pattern, else ''."""
    host = host or platform.node()
    short = host.split(".")[0]
    return host if any(fnmatch.fnmatch(h, p) for p in config.login_nodes for h in (host, short)) else ""


def guard_message(host: str) -> str:
    return (
        f"refusing to run an MPI or GPU case on the login node {host} ([scheduler] login_nodes): "
        "run it through the scheduler with --runner slurm"
    )


# ── jobs ───────────────────────────────────────────────────────────────────────


@dataclass
class Job:
    """What to run in a job: the command (launcher included) in a run directory, and its resources."""

    name: str
    command: list[str]
    rundir: str
    ranks: int = 0
    threads: int = 0
    gpus: int = 0
    timeout: float = 0.0
    env: dict[str, str] = field(default_factory=dict)  # exported in the script (case env, OMP_NUM_THREADS)


# the job records the facts of the node it ran on (the provenance of a run is otherwise collected on the submitting
# host: a login node without the job's GPUs, with another CPU); `cores` = processors available to the job
NODE_FACTS = (
    f"{{ echo host=$(hostname); echo os=$(uname -sr); grep -m1 '^model name' /proc/cpuinfo | sed 's/^[^:]*: */cpu=/';"
    f" echo cores=$(nproc); nvidia-smi -L 2>/dev/null | sed 's/^/gpu=/'; }} > {HOST_FILE}",
)


def node_facts(text: str) -> dict:
    """The machine facts of the host file written by the job (a file holding only a host name gives the host)."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines and "=" not in lines[0]:
        return {"host": lines[0]}
    facts: dict = {}
    for line in lines:
        key, _, value = line.partition("=")
        if key == "gpu":  # nvidia-smi -L lines; on a node without a GPU given to the job: "No devices found."
            if value.strip().startswith("GPU"):
                facts.setdefault("gpus", []).append(value.strip())
        elif key == "cores":
            with contextlib.suppress(ValueError):
                facts["cores"] = int(value)
        elif key in ("host", "os", "cpu"):
            facts[key] = value.strip()
    if "host" in facts:
        facts.setdefault("gpus", [])
    return facts


@dataclass
class JobResult:
    job_id: str
    state: str  # Slurm's final state: COMPLETED, FAILED, TIMEOUT, CANCELLED, OUT_OF_MEMORY, ... or UNKNOWN
    exit_code: int | None  # the command's own exit status (None when it did not finish)
    elapsed: float
    stdout: str
    stderr: str
    node: str = ""
    machine: dict = field(default_factory=dict)  # the node's facts (`node_facts`)


def _read(path: str) -> str:
    with contextlib.suppress(OSError), open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()
    return ""


class SlurmScheduler:
    """Submits `Job`s with ``sbatch`` and waits for them (``squeue``, ``sacct``); *run* and *sleep* replaceable."""

    def __init__(
        self,
        config: SchedulerConfig,
        run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        sleep: Callable[[float], None] = time.sleep,
        progress: Callable[[str], None] = lambda _m: None,
    ) -> None:
        self.config = config
        self._run = run
        self._sleep = sleep
        self.progress = progress

    def script(self, job: Job) -> str:
        """The job script: ``#SBATCH`` resources, setup lines, the command with its output, exit status and time
        recorded in the run directory."""
        directives = [
            f"--job-name=fobis-{job.name}",
            f"--chdir={job.rundir}",
            f"--output={os.path.join(job.rundir, 'slurm-%j.out')}",
            f"--ntasks={max(job.ranks, 1)}",
            f"--cpus-per-task={max(job.threads, 1)}",
        ]
        if job.timeout:
            directives.append(f"--time={max(1, math.ceil(job.timeout / 60))}")
        if job.gpus:
            directives.append(f"--gpus={job.gpus}")
        for key in ("partition", "account", "qos"):
            if getattr(self.config, key):
                directives.append(f"--{key}={getattr(self.config, key)}")
        lines = ["#!/bin/bash", *(f"#SBATCH {d}" for d in directives)]
        lines += [o if o.startswith("#SBATCH") else f"#SBATCH {o}" for o in self.config.options]
        lines += ["", "# generated by fobis: do not edit", *self.config.setup]
        lines += [f"export {k}={shlex.quote(v)}" for k, v in sorted(job.env.items())]
        lines += [
            *NODE_FACTS,
            "start=$(date +%s.%N)",
            f"{shlex.join(job.command)} > {STDOUT_FILE} 2> {STDERR_FILE}",
            "code=$?",
            "end=$(date +%s.%N)",
            f'echo "$code $start $end" > {EXIT_FILE}',
            "exit $code",
        ]
        return "\n".join(lines) + "\n"

    def _command(self, args: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
        return self._run(args, capture_output=True, text=True, env=env)

    def submit(self, job: Job, env: dict | None = None) -> JobResult:
        """Submit *job* (the submitting environment *env* is exported to it), wait for it, collect its outputs."""
        os.makedirs(job.rundir, exist_ok=True)
        for name in (EXIT_FILE, STDOUT_FILE, STDERR_FILE, HOST_FILE):
            with contextlib.suppress(OSError):
                os.remove(os.path.join(job.rundir, name))
        script = os.path.join(job.rundir, SCRIPT_FILE)
        with open(script, "w", encoding="utf-8") as handle:
            handle.write(self.script(job))
        try:
            done = self._command(["sbatch", "--parsable", script], env)
        except OSError as exc:
            raise SchedulerError(f"cannot run sbatch: {exc}") from exc
        if done.returncode != 0:
            raise SchedulerError(f"sbatch failed: {(done.stderr or done.stdout).strip()}")
        job_id = done.stdout.strip().split(";")[0]
        self.progress(f"job {job_id} submitted ({job.name})")
        try:
            last = ""
            while True:
                queued = self._command(["squeue", "-h", "-j", job_id, "-o", "%T"])
                state = queued.stdout.strip() if queued.returncode == 0 else ""
                if not state:
                    break
                if state != last:
                    self.progress(f"job {job_id}: {state.lower()}")
                    last = state
                self._sleep(self.config.poll)
        except KeyboardInterrupt:
            self._command(["scancel", job_id])
            raise
        return self._collect(job, job_id)

    def _collect(self, job: Job, job_id: str) -> JobResult:
        state = "UNKNOWN"
        with contextlib.suppress(OSError):
            done = self._command(["sacct", "-n", "-P", "-X", "-j", job_id, "-o", "State,ExitCode"])
            if done.returncode == 0 and done.stdout.strip():
                state = done.stdout.strip().splitlines()[0].split("|")[0].split()[0]
        exit_code, elapsed = None, 0.0
        recorded = _read(os.path.join(job.rundir, EXIT_FILE)).split()
        if len(recorded) == 3:
            with contextlib.suppress(ValueError):
                exit_code, elapsed = int(recorded[0]), float(recorded[2]) - float(recorded[1])
                if state == "UNKNOWN":
                    state = "COMPLETED" if exit_code == 0 else "FAILED"
        stderr = _read(os.path.join(job.rundir, STDERR_FILE))
        if exit_code is None:  # killed by the scheduler (time limit, memory, cancelled): its own log says why
            log = _read(os.path.join(job.rundir, f"slurm-{job_id}.out")).strip()
            stderr += f"\nslurm job {job_id} ended {state}" + (f": {log.splitlines()[-1]}" if log else "")
        machine = node_facts(_read(os.path.join(job.rundir, HOST_FILE)))
        return JobResult(
            job_id,
            state,
            exit_code,
            elapsed,
            _read(os.path.join(job.rundir, STDOUT_FILE)),
            stderr,
            machine.get("host", ""),
            machine,
        )


# ── the runner ─────────────────────────────────────────────────────────────────


class SlurmRunner(LocalRunner):
    """A `LocalRunner` whose runs are Slurm jobs (builds stay on the submitting host)."""

    def __init__(self, *args: Any, scheduler: SlurmScheduler, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.scheduler = scheduler
        self.launcher = scheduler.config.launcher
        self._case: Case | None = None

    def run(self, case: Case, *args: Any, **kwargs: Any) -> RunResult:
        self._case = case
        return super().run(case, *args, **kwargs)

    def provenance(self, case: Case, mode: str | None) -> dict:
        data = super().provenance(case, mode)
        config = self.scheduler.config
        data["scheduler"] = {"kind": config.kind, "partition": config.partition, "account": config.account}
        return data

    def _execute(self, result: RunResult, env: dict, timeout: float) -> RunOutput | None:  # type: ignore[override]
        case = self._case
        exports = dict(case.env) if case else {}
        if case and case.threads:
            exports["OMP_NUM_THREADS"] = str(case.threads)
        job = Job(
            name=result.case,
            command=result.command,
            rundir=result.rundir,
            ranks=case.ranks if case else 0,
            threads=case.threads if case else 0,
            gpus=case.gpus if case else 0,
            timeout=timeout,
            env=exports,
        )
        try:
            done = self.scheduler.submit(job, env)
        except SchedulerError as exc:
            result.status, result.stderr = "error", str(exc)
            return None
        result.provenance.setdefault("scheduler", {}).update(job=done.job_id, state=done.state, node=done.node)
        if done.machine:  # the run's machine is the node, not the submitting host
            result.provenance.setdefault("machine", {}).update(done.machine)
        result.stdout, result.stderr, result.elapsed = done.stdout, done.stderr, done.elapsed
        if done.exit_code is None:
            result.status = "timeout" if done.state == "TIMEOUT" else "failed"
            result.exit_code = -1
            return None
        result.exit_code = done.exit_code
        return RunOutput(result.rundir, done.stdout, done.stderr, done.exit_code)
