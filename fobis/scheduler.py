"""One ready queue for the compiles of a whole build (issue #218, phase 3).

FoBiS used to compile in levels: a file's level was the number of files depending on it, and a level started only
when the previous one had ended. Two independent modules with three and four dependents never compiled together, and
every file without modules, every submodule and the target were separate builds with separate levels. Measured on a
216-file target: 57 levels where the dependency graph is 30 deep.

Here every file the build compiles is a node of one graph; a file starts as soon as the files it depends on have
compiled, on one of ``jobs`` workers, the longest remaining chain first (weighted by the compile times recorded by the
last ``--timings`` build when there are some, else by file size). Each file's compiler output is printed when it
ends, as one block.

Failure semantics are those of the level scheduler:

- a file the targets (or the submodules) need that does not compile stops the build: nothing new starts, the
  compiles running finish, then the build fails with the failed compiles' output;
- a file needed only by files without modules (``optional``) that does not compile is reported for every such file
  that depends on it, which is then not compiled nor linked; nothing else stops.
"""

from __future__ import annotations

import contextlib
import heapq
import json
import os
import shutil
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from typing import Any

from .timings import TIMINGS_FILE, run_steps_measured
from .utils import check_results, syswork_steps

SCHEDULERS = ("queue", "levels")


def available_cpus() -> int:
    """The CPUs this process may run on (its affinity, e.g. a Slurm allocation), else the machine's."""
    try:
        return max(1, len(os.sched_getaffinity(0)))
    except (AttributeError, OSError):
        return max(1, os.cpu_count() or 1)


def _closure(pfile: Any) -> list[Any]:
    return [p for p in (pfile.pfile_dep_all or [pfile]) if not p.include]


def compiled_deps(pfile: Any, nodes: dict[int, Any]) -> list[Any]:
    """The files of *nodes* that *pfile* depends on directly, an include standing for what it includes."""
    found = []
    stack = list(pfile.pfile_dep or [])
    seen = set()
    while stack:
        dep = stack.pop()
        if id(dep) in seen or dep is pfile:
            continue
        seen.add(id(dep))
        if dep.include:
            stack.extend(dep.pfile_dep or [])
        elif id(dep) in nodes:
            found.append(dep)
    return found


def recorded_costs(obj_dir: str) -> dict[str, float]:
    """{file: seconds} of the compiles recorded by the last ``--timings`` build in *obj_dir* (empty without one)."""
    try:
        with open(os.path.join(obj_dir, TIMINGS_FILE), encoding="utf-8") as handle:
            records = json.load(handle).get("records", [])
    except (OSError, ValueError, AttributeError):
        return {}
    costs: dict[str, float] = {}
    for record in records:
        if isinstance(record, dict) and record.get("kind") == "compile" and record.get("status") == 0:
            costs[str(record.get("file"))] = float(record.get("seconds") or 0.0)
    return costs


@dataclass
class QueueResult:
    """What the queue did: files compiled, and the optional files not compiled with the reason."""

    compiled: int = 0
    # file not compiled -> (the file that failed: itself or one it depends on, that file's compiler output)
    failed: dict[str, tuple[str, str]] = field(default_factory=dict)


SYNTAX_ONLY = {
    "gnu": "-fsyntax-only",
    "opencoarrays-gnu": "-fsyntax-only",
    "nvfortran": "-Msyntax-only",
    "pgi": "-Msyntax-only",
}
OBJECT_MODS_DIR = ".fobis-object-mods"


@dataclass
class _Job:
    pfile: Any
    kind: str  # "full" (one compile), "interface" (module files only), "object" (the object, module files aside)


def compile_queue(
    builder: Any,
    required: list[Any],
    optional: list[Any],
    *,
    verbose: bool = False,
    log: bool = False,
    quiet: bool = False,
    cutoff: Any = None,
    external_mods: dict[str, float] | None = None,
    interfaces_first: str | None = None,
    ancestors: set[str] | None = None,
) -> QueueResult:
    """Compile what the closures of *required* and *optional* files need (``to_compile``), in one ready queue.

    A file compiled successfully gets ``to_compile = False``, so the builds that follow (submodules, targets) find
    nothing left to compile and link. Raises `utils.BuildFailed` when a required file does not compile.

    With *cutoff* (`interfaces.InterfaceCutoff`), a file to compile only because a file it depends on changed is
    compiled when that changed a module interface of its closure, else skipped (`interfaces`).

    With *interfaces_first* (the compiler's family, phase 6), a module that other files of this build use is compiled
    twice: its module files first with the compiler's syntax-only switch, which the files using it wait for, then its
    object, which nothing waits for (its module files written to a directory of its own and compared with the first
    ones: a difference fails the build). Not for submodules nor the modules that have submodules (*ancestors*).
    """
    result = QueueResult()
    required_ids: set[int] = set()
    for pfile in required:
        required_ids.update(id(p) for p in _closure(pfile))
    files: dict[int, Any] = {}
    for pfile in [*required, *optional]:
        for member in _closure(pfile):
            if member.to_compile and id(member) not in files:
                files[id(member)] = member
    if not files:
        return result
    file_order = {key: index for index, key in enumerate(sorted(files, key=lambda k: files[k].name))}
    file_deps = {key: [id(d) for d in compiled_deps(pfile, files)] for key, pfile in files.items()}
    file_dependents: dict[int, list[int]] = {key: [] for key in files}
    for key, below in file_deps.items():
        for dep in below:
            file_dependents[dep].append(key)

    # the jobs: one per file, two for a module split by interfaces_first
    switch = SYNTAX_ONLY.get(interfaces_first or "")
    module_switch = builder.compiler.modsw + builder.mod_dir + " -I" + builder.mod_dir if switch else ""
    jobs_of: dict[int, dict[str, int]] = {}
    job_list: list[_Job] = []
    for key in sorted(files, key=lambda k: file_order[k]):
        pfile = files[key]
        split = (
            switch is not None
            and pfile.module
            and not pfile.submodule
            and not pfile.c_source
            and file_dependents[key]
            and not ({n.lower() for n in pfile.module_names or []} & (ancestors or set()))
            and module_switch in builder.cmd_comp
        )
        if split:
            jobs_of[key] = {"interface": len(job_list), "object": len(job_list) + 1}
            job_list += [_Job(pfile, "interface"), _Job(pfile, "object")]
        else:
            jobs_of[key] = {"full": len(job_list)}
            job_list.append(_Job(pfile, "full"))

    def provider(key: int) -> int:
        return jobs_of[key].get("interface", jobs_of[key].get("full"))

    deps: dict[int, list[int]] = {}
    for key, kinds in jobs_of.items():
        below = [provider(dep) for dep in file_deps[key]]
        for kind, job in kinds.items():
            deps[job] = below + ([kinds["interface"]] if kind == "object" else [])
    dependents: dict[int, list[int]] = {job: [] for job in deps}
    for job, below in deps.items():
        for dep in below:
            dependents[dep].append(job)
    order = {job: (file_order[id(spec.pfile)], spec.kind != "interface") for job, spec in enumerate(job_list)}
    costs = recorded_costs(builder.obj_dir)

    def cost(job: int) -> float:
        spec = job_list[job]
        name = spec.pfile.name
        if name in costs:
            seconds = costs[name]
        else:
            try:
                seconds = os.path.getsize(name) / 1.0e4  # ~ seconds per 10 kB: only the ratios matter
            except OSError:
                seconds = 1.0
        return seconds * 0.4 if spec.kind == "interface" else seconds  # measured on PENF: 2.09 s against 4.92 s

    rank: dict[int, float] = {}
    for job in sorted(deps, key=lambda j: -len(_closure(job_list[j].pfile))):  # dependents first: short stacks
        stack = [job]
        while stack:
            current = stack[-1]
            if current in rank:
                stack.pop()
                continue
            pending = [d for d in dependents[current] if d not in rank]
            if pending:
                stack.extend(pending)
                continue
            stack.pop()
            rank[current] = cost(current) + max((rank[d] for d in dependents[current]), default=0.0)

    candidates: set[int] = set()
    if cutoff is not None:
        from .interfaces import changed_itself

        force = bool(getattr(getattr(builder, "cliargs", None), "force_compile", False))
        candidates = {
            key
            for key, pfile in files.items()
            if not changed_itself(pfile, builder.obj_dir, force, external_mods or {})
        }
    waiting = {job: len(deps[job]) for job in deps}
    ready = [(-rank[job], order[job], job) for job in deps if waiting[job] == 0]
    heapq.heapify(ready)
    blocked: set[int] = set()
    skipped: set[int] = set()
    fatal: list[list[Any]] = []
    mismatched: list[str] = []
    total = len(files)
    done = 0
    workers = max(1, int(builder.jobs or 1))
    run = run_steps_measured if builder.timings is not None else None

    def fail_dependents(key: int, culprit: str, output: str) -> None:
        """The files depending on file *key* are not linked: those not started are never compiled."""
        stack = list(file_dependents[key])
        seen = set()
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            result.failed[files[current].name] = (culprit, output)
            blocked.update(jobs_of[current].values())
            stack.extend(file_dependents[current])

    def private_dir(pfile: Any) -> str:
        return os.path.join(builder.obj_dir, OBJECT_MODS_DIR, pfile.obj_name)

    def steps_of(spec: _Job) -> list[tuple[str, str | None]]:
        steps = builder._compile_command(file_to_compile=spec.pfile)
        if spec.kind == "full":
            return steps
        *first, (cmd, cleanup) = steps
        if spec.kind == "interface":
            return [*first, (cmd + " " + switch, cleanup)]
        moved = builder.compiler.modsw + private_dir(spec.pfile) + " -I" + builder.mod_dir
        return [*first, (cmd.replace(module_switch, moved, 1), cleanup)]

    def task(spec: _Job) -> tuple[list[Any], dict[str, Any] | None]:
        if spec.kind == "object":
            os.makedirs(private_dir(spec.pfile), exist_ok=True)
        steps = steps_of(spec)
        if run is not None:
            return run(steps)
        return syswork_steps(steps), None

    def release(job: int) -> None:
        for dependent in dependents[job]:
            waiting[dependent] -= 1
            if waiting[dependent] == 0 and dependent not in blocked:
                heapq.heappush(ready, (-rank[dependent], order[dependent], dependent))

    def check_interfaces(pfile: Any) -> None:
        """The module files of the object compile must be those of the syntax-only compile the dependents read."""
        from .interfaces import module_digest

        family = "nvfortran" if switch == "-Msyntax-only" else "gnu"
        for name in pfile.module_names or []:
            shared = os.path.join(builder.mod_dir, name.lower() + ".mod")
            own = os.path.join(private_dir(pfile), name.lower() + ".mod")
            if module_digest(shared, family) != module_digest(own, family):
                mismatched.append(f"{pfile.name} ({name})")
                shutil.copyfile(own, shared)  # the full compile's module file is the reference

    running: dict[Future, int] = {}
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            while ready or running:
                while ready and len(running) < workers and not fatal:
                    _, _, job = heapq.heappop(ready)
                    if job in blocked or job in skipped:
                        continue
                    spec = job_list[job]
                    key = id(spec.pfile)
                    if spec.kind != "object" and key in candidates and not cutoff.must_compile(spec.pfile):
                        # only a file it depends on changed, and no module interface of its closure: not compiled
                        spec.pfile.to_compile = False
                        cutoff.skipped += 1
                        total -= 1
                        if verbose and not quiet:
                            builder.print_n(f"Not compiled {spec.pfile.name}: the interfaces it reads did not change")
                        skipped.update(jobs_of[key].values())
                        for other in jobs_of[key].values():
                            release(other)
                        continue
                    if verbose and not quiet:
                        builder.print_n("Executing: " + str(steps_of(spec)))
                    running[pool.submit(task, spec)] = job
                if not running:
                    break
                finished, _ = wait(list(running), return_when=FIRST_COMPLETED)
                for future in sorted(finished, key=lambda f: order[running[f]]):
                    job = running.pop(future)
                    spec = job_list[job]
                    pfile = spec.pfile
                    key = id(pfile)
                    (status, output), measure = future.result()
                    if measure is not None:
                        builder.timings.add(
                            pfile.name, "interface" if spec.kind == "interface" else "compile", status, measure
                        )
                    if status == 0:
                        if spec.kind == "interface":
                            if cutoff is not None:
                                cutoff.compiled(pfile)
                            if output.strip():
                                builder.print_w(output.rstrip("\n"))
                            release(job)
                            continue
                        done += 1
                        result.compiled += 1
                        pfile.to_compile = False
                        if spec.kind == "object":
                            check_interfaces(pfile)
                        elif cutoff is not None:
                            cutoff.compiled(pfile)
                        if not quiet:
                            builder.print_n(f"Compiling {pfile.name} [{done}/{total}]")
                        if output.strip():
                            builder.print_w(output.rstrip("\n"))  # warnings, -Minfo: as the level scheduler did
                        release(job)
                        continue
                    done += 1
                    if key in required_ids or pfile.c_source:
                        fatal.append([status, output])
                        if not quiet:
                            builder.print_n(f"Compiling {pfile.name} [{done}/{total}] failed")
                    else:
                        result.failed[pfile.name] = (pfile.name, output)
                        blocked.update(jobs_of[key].values())
                        fail_dependents(key, pfile.name, output)
                        if not quiet:
                            builder.print_n(
                                f"Compiling {pfile.name} [{done}/{total}] failed (not needed by the target)"
                            )
    finally:
        if cutoff is not None:
            cutoff.save()
    if mismatched:
        # the files compiled against the syntax-only module files are compiled again by the next build
        for spec in job_list:
            if spec.kind != "interface":
                with contextlib.suppress(OSError):
                    os.remove(os.path.join(builder.obj_dir, spec.pfile.obj_name + ".o"))
        fatal.append(
            [
                1,
                "interfaces_first: the module files written by the syntax-only compile differ from the full compile's "
                "for " + ", ".join(mismatched) + ": this compiler and these flags cannot use interfaces_first (the "
                "objects of this build were removed: build again without it)\n",
            ]
        )
    if fatal:
        check_results(results=fatal, log="building-errors.log" if log else None, print_w=builder.print_w)
    return result
