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

import heapq
import json
import os
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


def compile_queue(
    builder: Any,
    required: list[Any],
    optional: list[Any],
    *,
    verbose: bool = False,
    log: bool = False,
    quiet: bool = False,
) -> QueueResult:
    """Compile what the closures of *required* and *optional* files need (``to_compile``), in one ready queue.

    A file compiled successfully gets ``to_compile = False``, so the builds that follow (submodules, targets) find
    nothing left to compile and link. Raises `utils.BuildFailed` when a required file does not compile.
    """
    result = QueueResult()
    required_ids: set[int] = set()
    for pfile in required:
        required_ids.update(id(p) for p in _closure(pfile))
    nodes: dict[int, Any] = {}
    for pfile in [*required, *optional]:
        for member in _closure(pfile):
            if member.to_compile and id(member) not in nodes:
                nodes[id(member)] = member
    if not nodes:
        return result
    order = {key: index for index, key in enumerate(sorted(nodes, key=lambda k: nodes[k].name))}
    deps = {key: [id(d) for d in compiled_deps(pfile, nodes)] for key, pfile in nodes.items()}
    dependents: dict[int, list[int]] = {key: [] for key in nodes}
    for key, below in deps.items():
        for dep in below:
            dependents[dep].append(key)
    costs = recorded_costs(builder.obj_dir)

    def cost(key: int) -> float:
        name = nodes[key].name
        if name in costs:
            return costs[name]
        try:
            return os.path.getsize(name) / 1.0e4  # ~ seconds per 10 kB: only the ratios matter
        except OSError:
            return 1.0

    rank: dict[int, float] = {}
    for key in sorted(nodes, key=lambda k: -len(_closure(nodes[k]))):  # roughly dependents first: short stacks
        stack = [key]
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

    waiting = {key: len(deps[key]) for key in nodes}
    ready = [(-rank[key], order[key], key) for key in nodes if waiting[key] == 0]
    heapq.heapify(ready)
    blocked: set[int] = set()
    fatal: list[list[Any]] = []
    total = len(nodes)
    done = 0
    jobs = max(1, int(builder.jobs or 1))
    run = run_steps_measured if builder.timings is not None else None

    def block(key: int, culprit: str, output: str) -> None:
        stack = list(dependents[key])
        while stack:
            current = stack.pop()
            if current in blocked:
                continue
            blocked.add(current)
            result.failed[nodes[current].name] = (culprit, output)
            stack.extend(dependents[current])

    def task(pfile: Any) -> tuple[list[Any], dict[str, Any] | None]:
        steps = builder._compile_command(file_to_compile=pfile)
        if run is not None:
            return run(steps)
        return syswork_steps(steps), None

    running: dict[Future, int] = {}
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        while ready or running:
            while ready and len(running) < jobs and not fatal:
                _, _, key = heapq.heappop(ready)
                if key in blocked:
                    continue
                if verbose and not quiet:
                    builder.print_n("Executing: " + str(builder._compile_command(file_to_compile=nodes[key])))
                running[pool.submit(task, nodes[key])] = key
            if not running:
                break
            finished, _ = wait(list(running), return_when=FIRST_COMPLETED)
            for future in sorted(finished, key=lambda f: order[running[f]]):
                key = running.pop(future)
                pfile = nodes[key]
                (status, output), measure = future.result()
                done += 1
                if measure is not None:
                    builder.timings.add(pfile.name, "compile", status, measure)
                if status == 0:
                    result.compiled += 1
                    pfile.to_compile = False
                    if not quiet:
                        builder.print_n(f"Compiling {pfile.name} [{done}/{total}]")
                    if output.strip():
                        builder.print_w(output.rstrip("\n"))  # warnings, -Minfo: as the level scheduler did
                    for dependent in dependents[key]:
                        waiting[dependent] -= 1
                        if waiting[dependent] == 0 and dependent not in blocked:
                            heapq.heappush(ready, (-rank[dependent], order[dependent], dependent))
                elif key in required_ids or pfile.c_source:
                    fatal.append([status, output])
                    if not quiet:
                        builder.print_n(f"Compiling {pfile.name} [{done}/{total}] failed")
                else:
                    result.failed[pfile.name] = (pfile.name, output)
                    block(key, pfile.name, output)
                    if not quiet:
                        builder.print_n(f"Compiling {pfile.name} [{done}/{total}] failed (not needed by the target)")
    if fatal:
        check_results(results=fatal, log="building-errors.log" if log else None, print_w=builder.print_w)
    return result
