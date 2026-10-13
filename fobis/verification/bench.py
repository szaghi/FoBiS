"""bench.py — performance as a measured fact (phase V8 of PLAN-verification.md).

A benchmark is a declared case run repeatedly: after warm-up runs, until the 95% confidence interval of the median
time is narrower than a target (or a maximum number of runs, or a time budget). The interval is distribution-free
(order statistics of the sample, valid from 6 runs), so no normality is assumed of timings, which are skewed by
nature. Two measurements are called different only when their intervals do not overlap; otherwise the answer is
"no measurable difference", whatever the medians say.
"""

from __future__ import annotations

import datetime
import json
import math
import os
import re
import resource
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from .case import CaseError

SECTION_PREFIX = "bench:"
_KEYS = {"warmup", "min_runs", "max_runs", "target", "max_time", "time", "work"}
CONFIDENCE = 0.95
SHORT_RUN = 0.01  # seconds: below it, a wall-timed run measures mostly the process start-up
_GPU_FLAG = re.compile(
    r"^(-f?openacc|-acc(=\S*)?|-cuda|-Mcuda\S*|-mp=gpu|-gpu=\S*|-fopenmp-targets=\S*|-foffload=\S*|-fopenmp-target\S*)$"
)
TIMING_SECTION = "hpc-practice:gpu-practice#gpu-benchmark-timing"
FP64_SECTION = "hpc-practice:gpu-practice#mixed-precision-on-consumer-gpus-the-fp64-trap"


class BenchError(CaseError):
    """A benchmark is declared incorrectly."""


@dataclass
class BenchSpec:
    """How to measure a case: ``[bench:CASE]`` (every key optional)."""

    case: str
    warmup: int = 1
    min_runs: int = 10
    max_runs: int = 50
    target: float = 0.02  # half-width of the median's 95% interval, relative to the median
    max_time: float = 600.0  # seconds of measuring per side
    time: str = "wall"  # or the name of a quantity of the case: a time the program reports, in seconds
    work: float | None = None  # work per run, for a throughput (work / time)
    unit: str = ""


def parse_spec(name: str, items: dict[str, str] | None) -> BenchSpec:
    """The ``[bench:NAME]`` section (None: the defaults)."""
    spec = BenchSpec(name)
    items = items or {}
    unknown = sorted(set(items) - _KEYS)
    if unknown:
        raise BenchError(f"[bench:{name}]: unknown key(s) {', '.join(unknown)} (known: {', '.join(sorted(_KEYS))})")
    try:
        spec.warmup = int(items.get("warmup", spec.warmup))
        spec.min_runs = int(items.get("min_runs", spec.min_runs))
        spec.max_runs = int(items.get("max_runs", spec.max_runs))
        spec.target = float(items.get("target", spec.target))
        spec.max_time = float(items.get("max_time", spec.max_time))
    except ValueError as exc:
        raise BenchError(f"[bench:{name}]: {exc}") from exc
    if spec.warmup < 0 or spec.min_runs < 1 or spec.max_runs < spec.min_runs or spec.target <= 0:
        raise BenchError(f"[bench:{name}]: need warmup >= 0, 1 <= min_runs <= max_runs, target > 0")
    spec.time = items.get("time", "wall").strip() or "wall"
    work = items.get("work", "").split(None, 1)
    if work:
        try:
            spec.work = float(work[0])
        except ValueError as exc:
            raise BenchError(f"[bench:{name}]: work {items['work']!r} is not 'NUMBER [unit]'") from exc
        spec.unit = work[1].strip() if len(work) > 1 else ""
    return spec


def load_spec(fobos: Any, name: str) -> BenchSpec:
    """The ``[bench:NAME]`` of a parsed fobos, or the defaults."""
    parser = getattr(fobos, "fobos", None)
    section = SECTION_PREFIX + name
    if parser is None or not parser.has_section(section):
        return parse_spec(name, None)
    return parse_spec(name, dict(parser.items(section)))


# ── statistics ─────────────────────────────────────────────────────────────────


def median(values: list[float]) -> float:
    ordered = sorted(values)
    n = len(ordered)
    return ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2


def mad(values: list[float]) -> float:
    """Median absolute deviation from the median (unscaled)."""
    centre = median(values)
    return median([abs(v - centre) for v in values])


def median_interval(values: list[float], confidence: float = CONFIDENCE) -> tuple[float, float] | None:
    """Distribution-free confidence interval of the median: order statistics ``[x_(k), x_(n+1-k)]`` with the largest
    k such that ``P(Binomial(n, 1/2) < k) <= (1 - confidence) / 2``. None when n is too small (n < 6 at 95%)."""
    n = len(values)
    alpha = (1 - confidence) / 2
    k, cumulative = 0, 0.0
    while k < n:
        cumulative += math.comb(n, k) / 2**n  # P(B = k)
        if cumulative > alpha:
            break
        k += 1
    if k == 0:
        return None
    ordered = sorted(values)
    return ordered[k - 1], ordered[n - k]


@dataclass
class Stats:
    """A measured sample of run times (seconds)."""

    n: int
    median: float
    mad: float
    low: float | None
    high: float | None
    min: float
    max: float
    cpu_ratio: float | None = None  # median of CPU time / wall time: the cores the program kept busy
    load_max: float = 0.0  # largest 1-minute load average seen before a run
    throughput: float | None = None
    unit: str = ""

    @property
    def halfwidth(self) -> float | None:
        if self.low is None or self.high is None or self.median <= 0:
            return None
        return (self.high - self.low) / 2 / self.median

    def to_dict(self) -> dict:
        data = asdict(self)
        data["halfwidth"] = self.halfwidth
        return data


@dataclass
class Sample:
    time: float
    wall: float
    cpu: float | None  # None: not measurable (a scheduler job)
    load: float


def summarise(samples: list[Sample], spec: BenchSpec) -> Stats:
    times = [s.time for s in samples]
    interval = median_interval(times)
    centre = median(times)
    ratios = [s.cpu / s.wall for s in samples if s.wall > 0 and s.cpu is not None]
    return Stats(
        n=len(times),
        median=centre,
        mad=mad(times),
        low=interval[0] if interval else None,
        high=interval[1] if interval else None,
        min=min(times),
        max=max(times),
        cpu_ratio=median(ratios) if ratios else None,
        load_max=max(s.load for s in samples),
        throughput=spec.work / centre if spec.work and centre > 0 else None,
        unit=f"{spec.unit}/s" if spec.work and spec.unit else ("1/s" if spec.work else ""),
    )


def verdict(old: Stats, new: Stats) -> dict:
    """Speedup of *new* over *old* (old time / new time) with a conservative interval from the two medians'
    intervals: ``faster``/``slower`` only when the intervals do not overlap, else ``indistinguishable``."""
    speedup = old.median / new.median if new.median > 0 else None
    if None in (old.low, old.high, new.low, new.high) or not new.low:
        return {"speedup": speedup, "interval": None, "verdict": "unknown"}
    interval = [old.low / new.high, old.high / new.low]
    if new.high < old.low:
        found = "faster"
    elif new.low > old.high:
        found = "slower"
    else:
        found = "indistinguishable"
    return {"speedup": speedup, "interval": interval, "verdict": found}


# ── measuring ──────────────────────────────────────────────────────────────────


class RunFailedError(Exception):
    """A benchmark run did not succeed (its result is in ``result``)."""

    def __init__(self, message: str, result: Any = None) -> None:
        super().__init__(message)
        self.result = result


def timed(run: Callable[[], Any], spec: BenchSpec) -> Sample:
    """One run through *run* (a `LocalRunner.run` bound to the case): its time, CPU time of the children, load."""
    load = os.getloadavg()[0]
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    result = run()
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    if not result.ok:
        detail = (result.stderr or "").strip().splitlines()[-1:] or [result.status]
        raise RunFailedError(f"run {result.status}: {detail[0]}", result)
    cpu = (after.ru_utime - before.ru_utime) + (after.ru_stime - before.ru_stime)
    if "scheduler" in getattr(
        result, "provenance", {}
    ):  # a batch job: this host's children are sbatch/squeue, its load is not
        cpu, load = None, 0.0  # the job's (the program's own exit-file timing is still measured)
    if spec.time == "wall":
        measured = result.elapsed
    else:
        quantity = result.quantity(spec.time)
        if quantity is None or not quantity.values:
            raise RunFailedError(f"the time quantity {spec.time!r} was not found in the run's output", result)
        measured = float(quantity.values[0])
    return Sample(measured, result.elapsed, cpu, load)


def measure(
    sides: dict[str, Callable[[], Any]],
    spec: BenchSpec,
    progress: Callable[[str], None] = lambda _m: None,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, list[Sample]]:
    """Run every side ``warmup`` times (discarded), then round-robin — interleaved, so a drift of the machine
    affects every side alike — until each side has ``min_runs`` and its interval is within ``target``, or
    ``max_runs``, or ``max_time`` seconds of measuring per side have passed."""
    for name, run in sides.items():
        for k in range(spec.warmup):
            progress(f"{name}: warm-up {k + 1}/{spec.warmup}")
            timed(run, spec)
    samples: dict[str, list[Sample]] = {name: [] for name in sides}
    spent = dict.fromkeys(sides, 0.0)

    def done(name: str) -> bool:
        taken = samples[name]
        if len(taken) >= spec.max_runs or spent[name] >= spec.max_time:
            return True
        if len(taken) < spec.min_runs:
            return False
        width = summarise(taken, spec).halfwidth
        return width is not None and width <= spec.target

    while not all(done(name) for name in sides):
        for name, run in sides.items():
            if done(name):
                continue
            start = clock()
            samples[name].append(timed(run, spec))
            spent[name] += clock() - start
            stats = summarise(samples[name], spec)
            width = f", +-{stats.halfwidth:.1%}" if stats.halfwidth is not None else ""
            progress(f"{name}: run {len(samples[name])}, median {stats.median:.4g} s{width}")
    return samples


# ── notes ──────────────────────────────────────────────────────────────────────


def notes(spec: BenchSpec, stats: Stats, cflags: str, provenance: dict) -> list[str]:
    """Facts about how far the measurement can be trusted."""
    found = []
    if stats.low is None:
        found.append(f"{stats.n} runs give no 95% interval of the median (6 at least): no comparison is possible")
    elif stats.halfwidth is not None and stats.halfwidth > spec.target:
        found.append(
            f"the interval is +-{stats.halfwidth:.1%}, wider than the target {spec.target:.1%}: the runs stopped at "
            "max_runs or max_time"
        )
    if spec.time == "wall" and stats.median < SHORT_RUN:
        found.append(
            f"a median run of {stats.median * 1000:.3g} ms: wall time this short is mostly process start-up; "
            "enlarge the case or declare a time the program measures itself (`time = NAME`)"
        )
    cores = provenance.get("machine", {}).get("cores") or os.cpu_count() or 1
    if stats.load_max > cores / 2:
        found.append(
            f"the machine was busy: 1-minute load average up to {stats.load_max:.1f} on {cores} cores while "
            "measuring (the benchmark's own runs included)"
        )
    gpu = any(_GPU_FLAG.match(flag) for flag in cflags.split())
    if gpu and spec.time == "wall":
        found.append(
            "a device build timed by wall time: start-up, device initialisation and transfers are included; "
            "for kernel time print a wait-bracketed system_clock time and declare it as `time = NAME` "
            f"({TIMING_SECTION})"
        )
    gpus = machine_key(provenance)["gpus"]
    if gpu and any("geforce" in g.lower() for g in gpus):
        found.append(f"consumer GPU ({gpus[0]}): its FP64 throughput is 1/64 of FP32 ({FP64_SECTION})")
    return found


# ── history ────────────────────────────────────────────────────────────────────


def machine_key(provenance: dict) -> dict:
    """What must be equal for two measurements to be comparable: the machine and the compiler."""
    machine = provenance.get("machine", {})
    compiler = provenance.get("compiler", {})
    return {
        "cpu": machine.get("cpu", ""),
        "cores": machine.get("cores", 0),
        "gpus": [re.sub(r"\s*\(UUID:[^)]*\)", "", g) for g in machine.get("gpus", [])],  # models, not serials
        "compiler": compiler.get("name", ""),
        "version": compiler.get("version", ""),
    }


def record(case: str, mode: str, stats: Stats, provenance: dict) -> dict:
    git = provenance.get("git", {})
    return {
        "date": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "case": case,
        "mode": mode,
        "commit": git.get("commit", ""),
        "dirty": git.get("dirty", False),
        "cflags": provenance.get("compiler", {}).get("cflags", ""),
        "key": machine_key(provenance),
        "stats": stats.to_dict(),
    }


def history_path(bench_dir: str, case: str) -> str:
    return os.path.join(bench_dir, f"{case}.jsonl")


def read_history(path: str) -> list[dict]:
    entries = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    try:
                        entries.append(json.loads(line))
                    except ValueError:
                        continue
    return entries


def append_history(path: str, entry: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def latest_comparable(entries: list[dict], key: dict, mode: str) -> dict | None:
    """The newest history entry measured on the same machine with the same compiler and mode."""
    same = [e for e in entries if e.get("key") == key and e.get("mode") == mode]
    return same[-1] if same else None


def stats_from(data: dict) -> Stats:
    known = {k: v for k, v in data.items() if k in Stats.__dataclass_fields__}
    return Stats(**known)


# ── report ─────────────────────────────────────────────────────────────────────


def _seconds(value: float | None) -> str:
    return "-" if value is None else f"{value:.4g} s"


def describe(stats: Stats) -> str:
    interval = f" [{stats.low:.4g}, {stats.high:.4g}] 95%" if stats.low is not None else ""
    line = f"median {_seconds(stats.median)}{interval}, MAD {_seconds(stats.mad)}, min {_seconds(stats.min)}"
    line += f", {stats.n} runs"
    if stats.cpu_ratio is not None:
        line += f", CPU/wall {stats.cpu_ratio:.2f}"
    if stats.throughput is not None:
        line += f"; throughput {stats.throughput:.4g} {stats.unit}"
    return line


def describe_verdict(found: dict) -> str:
    if found["speedup"] is None:
        return "no comparison"
    text = f"speedup {found['speedup']:.3f}"
    if found["interval"]:
        text += f" [{found['interval'][0]:.3f}, {found['interval'][1]:.3f}]"
    return (
        text
        + {
            "faster": ": faster",
            "slower": ": slower",
            "indistinguishable": ": no measurable difference (the intervals overlap)",
            "unknown": ": not decidable (too few runs for an interval)",
        }[found["verdict"]]
    )


@dataclass
class BenchResult:
    """One benchmarked case: its measurement(s), comparison, notes, compiler-feedback changes."""

    case: str
    mode: str
    time: str
    status: str = "ok"  # ok, error
    error: str = ""
    stats: dict[str, Stats] = field(default_factory=dict)  # side -> stats ("new" alone without --compare)
    comparison: dict | None = None  # verdict() + against (history commit, or the revision)
    notes: list[str] = field(default_factory=list)
    feedback: list[dict] = field(default_factory=list)
    recorded: str = ""

    def to_dict(self) -> dict:
        return {
            "case": self.case,
            "mode": self.mode,
            "time": self.time,
            "status": self.status,
            "error": self.error,
            "stats": {side: s.to_dict() for side, s in self.stats.items()},
            "comparison": self.comparison,
            "notes": self.notes,
            "feedback": self.feedback,
            "recorded": self.recorded,
        }
