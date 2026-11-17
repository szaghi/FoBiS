"""Compile and link timings of a build (``fobis build --timings``, issue #218).

Every compiler and linker call of the build is measured (wall time and, where the platform reports it, the peak
resident memory of the process): the records are written to ``<obj_dir>/.fobis-timings.json`` and summarised at
the end of the build. The summary separates what the compilers cost (the serial sum) from how well the build used
the jobs (the makespan against the critical path of the dependency graph): a makespan far above both
``serial / jobs`` and the critical path is time lost by the scheduler, not by the compilers.
"""

from __future__ import annotations

import contextlib
import json
import os
import shlex
import subprocess
import threading
import time
from typing import Any

TIMINGS_FILE = ".fobis-timings.json"
SCHEMA = 1


def run_measured(cmd: str | list[str]) -> tuple[int, str, int | None]:
    """Run *cmd* as `utils.syswork` does and return (exit status, output, peak resident memory in KiB or None).

    The peak memory is the child's own (``wait4``), not the maximum over every child of FoBiS: unavailable on
    platforms without ``os.wait4``, where it is None.
    """
    args = shlex.split(cmd) if isinstance(cmd, str) else cmd
    try:
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except FileNotFoundError:
        return 127, f"{args[0]}: command not found (is its toolchain loaded?)\n", None
    assert proc.stdout is not None
    output = proc.stdout.read()
    proc.stdout.close()
    rss = None
    if hasattr(os, "wait4"):
        try:
            _, status, usage = os.wait4(proc.pid, 0)
            proc.returncode = os.waitstatus_to_exitcode(status)
            rss = int(usage.ru_maxrss)  # KiB on Linux
        except ChildProcessError:
            proc.wait()
    else:
        proc.wait()
    return proc.returncode, str(output, encoding="UTF-8", errors="replace"), rss


def run_steps_measured(steps: list[tuple[str, str | None]]) -> tuple[list[Any], dict[str, Any]]:
    """`utils.syswork_steps` with a measure: ([status, output], {start, end, peak_rss_kib}).

    Module-level so that a ``multiprocessing`` pool can pickle it.
    """
    start = time.time()
    combined = ""
    rss_max = None
    status = 0
    for cmd, cleanup in steps:
        status, output, rss = run_measured(cmd)
        combined += output
        if rss is not None:
            rss_max = max(rss_max or 0, rss)
        if cleanup:
            with contextlib.suppress(OSError):
                os.remove(cleanup)
        if status:
            break
    return [status, combined], {"start": start, "end": time.time(), "peak_rss_kib": rss_max}


class Timings:
    """The records of one build: one per compile or link, appended from any thread."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []
        self.started = time.time()
        self._lock = threading.Lock()

    def add(self, file: str, kind: str, status: int, measure: dict[str, Any]) -> None:
        """Record one call: *kind* is ``compile`` or ``link``."""
        with self._lock:
            self.records.append(
                {
                    "file": file,
                    "kind": kind,
                    "status": status,
                    "start": round(measure["start"] - self.started, 4),
                    "seconds": round(measure["end"] - measure["start"], 4),
                    "peak_rss_kib": measure.get("peak_rss_kib"),
                }
            )


def compiled_dependencies(pfiles: list[Any]) -> dict[str, list[str]]:
    """{file: the compiled files it depends on directly}, an include standing for what it includes in turn."""
    graph = {}
    for pfile in pfiles:
        deps: list[str] = []
        stack = list(pfile.pfile_dep or [])
        seen = set()
        while stack:
            dep = stack.pop()
            if id(dep) in seen or dep is pfile:
                continue
            seen.add(id(dep))
            if dep.include:
                stack.extend(dep.pfile_dep or [])
            else:
                deps.append(dep.name)
        graph[pfile.name] = deps
    return graph


def summarise(records: list[dict[str, Any]], graph: dict[str, list[str]], jobs: int) -> dict[str, Any]:
    """The figures of a build: serial sum, makespan, critical path (over the files compiled by this build: a file
    not compiled costs nothing), efficiency and the slowest files."""
    compiles = [r for r in records if r["kind"] == "compile"]
    links = [r for r in records if r["kind"] == "link"]
    cost: dict[str, float] = {}
    for record in compiles:
        cost[record["file"]] = cost.get(record["file"], 0.0) + record["seconds"]
    memo: dict[str, float] = {}

    def path(name: str, active: frozenset[str] = frozenset()) -> float:
        if name in memo:
            return memo[name]
        if name in active:  # a cycle would have stopped the build: never loop here
            return 0.0
        below = [path(dep, active | {name}) for dep in graph.get(name, [])]
        memo[name] = cost.get(name, 0.0) + max(below, default=0.0)
        return memo[name]

    critical = max((path(name) for name in cost), default=0.0)
    serial = sum(cost.values())
    if compiles:
        first = min(r["start"] for r in compiles)
        makespan = max(r["start"] + r["seconds"] for r in compiles) - first
    else:
        makespan = 0.0
    jobs = max(1, jobs)
    bound = max(critical, serial / jobs)
    peaks = [r["peak_rss_kib"] for r in records if r.get("peak_rss_kib")]
    return {
        "jobs": jobs,
        "compiles": len(compiles),
        "failed_compiles": sum(1 for r in compiles if r["status"] != 0),
        "serial_seconds": round(serial, 3),
        "makespan_seconds": round(makespan, 3),
        "critical_path_seconds": round(critical, 3),
        "lower_bound_seconds": round(bound, 3),
        "efficiency": round(serial / (makespan * jobs), 3) if makespan > 0 else None,
        "link_seconds": round(sum(r["seconds"] for r in links), 3),
        "peak_rss_kib": max(peaks) if peaks else None,
        "slowest": [
            {"file": name, "seconds": round(seconds, 3)}
            for name, seconds in sorted(cost.items(), key=lambda item: -item[1])[:10]
        ],
    }


def write(obj_dir: str, timings: Timings, summary: dict[str, Any]) -> str:
    """Write ``<obj_dir>/.fobis-timings.json`` and return its path."""
    os.makedirs(obj_dir, exist_ok=True)
    path = os.path.join(obj_dir, TIMINGS_FILE)
    document = {"schema": SCHEMA, "summary": summary, "records": timings.records}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=1)
        handle.write("\n")
    os.replace(tmp, path)
    return path


def render(summary: dict[str, Any], path: str) -> str:
    """The closing summary printed by ``fobis build --timings``."""
    lines = [
        f"Timings ({summary['compiles']} compiles, {summary['failed_compiles']} failed, -j {summary['jobs']}): {path}",
        f"  compile makespan {summary['makespan_seconds']:.1f} s, serial sum {summary['serial_seconds']:.1f} s, "
        f"critical path {summary['critical_path_seconds']:.1f} s, lower bound {summary['lower_bound_seconds']:.1f} s"
        + (f", efficiency {summary['efficiency']:.0%}" if summary["efficiency"] is not None else ""),
        f"  link {summary['link_seconds']:.1f} s"
        + (f", peak memory {summary['peak_rss_kib'] / 1024:.0f} MiB" if summary["peak_rss_kib"] else ""),
    ]
    if summary["slowest"]:
        lines.append("  slowest: " + ", ".join(f"{s['file']} {s['seconds']:.1f} s" for s in summary["slowest"][:5]))
    return "\n".join(lines)
