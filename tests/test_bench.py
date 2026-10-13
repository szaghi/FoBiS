"""Tests for ``fobis bench`` (phase V8 of PLAN-verification.md): the median's distribution-free interval, the
declaration, the verdict (faster/slower only when the intervals do not overlap), the measuring loop (warm-up,
interleaving, stopping rules, failures, a program-reported time), the notes, the history, the compiler-feedback diff
on GENUINE logs (``tests/bench/``: gfortran 16.0.1 ``-fopt-info-vec-optimized -fopt-info-vec-missed`` and nvfortran
26.1 ``-fast -acc -Minfo=accel,mp,vect`` of ``kern_old.f90`` / ``kern_new.f90``, the second with a recurrence), and
the command for real with gfortran."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field

import pytest

from fobis.fobis import run_fobis
from fobis.lint import lint_files
from fobis.lint.feedback import parse_log
from fobis.verification import Quantity
from fobis.verification import bench as bm
from fobis.verification import feedback_diff as fd

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bench")
GIT = ["git", "-c", "user.name=T", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false"]


# ── statistics ─────────────────────────────────────────────────────────────────


def test_statistics():
    assert bm.median([3, 1, 2]) == 2 and bm.median([4, 1, 2, 3]) == 2.5
    assert bm.mad([1, 2, 3, 4, 100]) == 1
    assert bm.median_interval([1, 2, 3, 4, 5]) is None  # P(B=0) = 1/32 > 2.5%
    assert bm.median_interval([6, 5, 4, 3, 2, 1]) == (1, 6)  # n = 6: the extremes (coverage 96.9%)
    assert bm.median_interval(list(range(1, 21))) == (6, 15)  # n = 20: P(B <= 5) = 2.07% <= 2.5% < P(B <= 6)
    assert bm.median_interval(list(range(1, 101))) == (40, 61)  # n = 100: the classical k = 40


def _stats(median, low, high):
    return bm.Stats(10, median, 0.0, low, high, low, high)


def test_verdict():
    assert bm.verdict(_stats(2.0, 1.9, 2.1), _stats(1.0, 0.95, 1.05))["verdict"] == "faster"
    found = bm.verdict(_stats(1.0, 0.95, 1.05), _stats(2.0, 1.9, 2.1))
    assert found["verdict"] == "slower" and found["interval"] == pytest.approx([0.95 / 2.1, 1.05 / 1.9])
    same = bm.verdict(_stats(1.0, 0.9, 1.1), _stats(0.95, 0.85, 1.05))
    assert same["verdict"] == "indistinguishable" and same["speedup"] == pytest.approx(1.0 / 0.95)
    assert bm.verdict(_stats(1.0, None, None), _stats(1.0, 0.9, 1.1))["verdict"] == "unknown"
    assert "no measurable difference" in bm.describe_verdict(same)


def test_spec():
    spec = bm.parse_spec("c", {"warmup": "2", "max_runs": "20", "target": "0.05", "work": "1e6 cells", "time": "t"})
    assert (spec.warmup, spec.min_runs, spec.max_runs, spec.target) == (2, 10, 20, 0.05)
    assert (spec.work, spec.unit, spec.time) == (1e6, "cells", "t")
    assert bm.parse_spec("c", None).time == "wall"
    for items, message in (
        ({"runs": "3"}, "unknown key"),
        ({"min_runs": "x"}, "invalid literal"),
        ({"min_runs": "9", "max_runs": "3"}, "min_runs <= max_runs"),
        ({"work": "lots"}, "is not 'NUMBER"),
    ):
        with pytest.raises(bm.BenchError, match=message):
            bm.parse_spec("c", items)


# ── measuring ──────────────────────────────────────────────────────────────────


@dataclass
class FakeResult:
    elapsed: float
    status: str = "ok"
    quantities: list = field(default_factory=list)
    stderr: str = ""

    @property
    def ok(self):
        return self.status == "ok"

    def quantity(self, name):
        return next((q for q in self.quantities if q.name == name), None)


def _runs(times, order=None, name=""):
    values = iter(times)

    def run():
        if order is not None:
            order.append(name)
        value = next(values)
        return value if isinstance(value, FakeResult) else FakeResult(value)

    return run


def test_measure():
    spec = bm.BenchSpec("c", warmup=1, min_runs=6, max_runs=12, target=0.05)
    order = []
    sides = {"old": _runs([9.0] + [2.0] * 20, order, "old"), "new": _runs([9.0] + [1.0] * 20, order, "new")}
    samples = bm.measure(sides, spec)
    assert len(samples["old"]) == len(samples["new"]) == 6  # identical times: the interval is exact at n = 6
    assert order[:6] == ["old", "new", "old", "new", "old", "new"]  # warm-ups, then interleaved
    assert all(s.time == 2.0 for s in samples["old"])  # the warm-up (9.0) is discarded
    noisy = [1.0, 2.0, 1.5, 3.0, 1.2, 2.5, 1.1, 2.9, 1.3, 2.2, 1.4, 2.7, 1.6, 2.1]
    assert len(bm.measure({"x": _runs([0.0, *noisy])}, spec)["x"]) == 12  # never narrow enough: max_runs
    clock = iter(range(0, 1000, 100))
    capped = bm.BenchSpec("c", warmup=0, min_runs=6, max_runs=50, max_time=250)
    assert len(bm.measure({"x": _runs(noisy)}, capped, clock=lambda: next(clock))["x"]) == 3  # 100 s per run
    with pytest.raises(bm.RunFailedError, match="run failed"):
        bm.measure({"x": _runs([FakeResult(1.0, "failed", stderr="boom")])}, spec)
    reported = bm.BenchSpec("c", warmup=0, min_runs=6, max_runs=6, time="kernel")
    results = [FakeResult(5.0, quantities=[Quantity("kernel", [0.25])]) for _ in range(6)]
    taken = bm.measure({"x": _runs(results)}, reported)["x"]
    assert {s.time for s in taken} == {0.25} and {s.wall for s in taken} == {5.0}
    with pytest.raises(bm.RunFailedError, match="time quantity 'kernel' was not found"):
        bm.measure({"x": _runs([FakeResult(1.0)])}, reported)


def test_summary_and_notes():
    spec = bm.BenchSpec("c", work=2e6, unit="cells")
    samples = [bm.Sample(t, t, 2 * t, 1.0) for t in (0.5, 0.5, 0.5, 0.5, 0.5, 0.5)]
    stats = bm.summarise(samples, spec)
    assert (stats.median, stats.low, stats.high, stats.cpu_ratio) == (0.5, 0.5, 0.5, 2.0)
    assert stats.throughput == 4e6 and stats.unit == "cells/s"
    machine = {"machine": {"cores": 4, "gpus": ["GPU 0: NVIDIA GeForce RTX 4070 (UUID: GPU-1234)"]}}
    found = bm.notes(spec, bm.Stats(5, 0.002, 0, None, None, 0.001, 0.003, load_max=3.5), "-c -fast -acc", machine)
    assert "5 runs give no 95% interval" in found[0]
    assert any("mostly process start-up" in n for n in found)
    assert any("load average up to 3.5 on 4 cores" in n for n in found)
    assert any(bm.TIMING_SECTION in n for n in found)
    assert any("NVIDIA GeForce RTX 4070)" in n and "UUID" not in n and bm.FP64_SECTION in n for n in found)
    assert bm.notes(spec, stats, "-c -O3", {"machine": {"cores": 4}}) == []


def test_history(tmp_path):
    provenance = {
        "git": {"commit": "abc", "dirty": False},
        "compiler": {"name": "gnu", "version": "16", "cflags": "-O3"},
        "machine": {"cpu": "x", "cores": 4, "gpus": ["GPU 0: A (UUID: GPU-9)"]},
    }
    path = bm.history_path(str(tmp_path / "bench"), "c")
    entry = bm.record("c", "gnu", _stats(1.0, 0.9, 1.1), provenance)
    assert entry["key"]["gpus"] == ["GPU 0: A"]  # serial numbers are not recorded
    bm.append_history(path, entry)
    with open(path, "a") as handle:
        handle.write("not json\n")
    other = dict(provenance, compiler={"name": "gnu", "version": "15"})
    bm.append_history(path, bm.record("c", "gnu", _stats(2.0, 1.9, 2.1), other))
    entries = bm.read_history(path)
    assert len(entries) == 2
    found = bm.latest_comparable(entries, bm.machine_key(provenance), "gnu")
    assert bm.stats_from(found["stats"]).median == 1.0  # the other compiler version is not comparable
    assert bm.latest_comparable(entries, bm.machine_key(provenance), "other") is None


# ── compiler feedback ──────────────────────────────────────────────────────────


def _events(compiler, side):
    source = os.path.join(HERE, f"kern_{side}.f90")
    analysed = lint_files([source], [])
    with open(os.path.join(HERE, f"{compiler}-{side}.txt")) as handle:
        return fd.events(handle.read(), analysed.units, analysed.project, HERE)


def test_feedback_gfortran():
    old, new = _events("gfortran", "old"), _events("gfortran", "new")
    assert [(e.procedure, e.category, e.line) for e in old] == [("axpy", fd.VECTORIZED, 10)]
    assert [(e.procedure, e.category, e.line) for e in new] == [("axpy", fd.NOT_VECTORIZED, 10)]
    changes = fd.diff(old, new, {"axpy"}, {"axpy"})
    assert [(c.category, c.old, c.new, c.regression) for c in changes] == [
        (fd.NOT_VECTORIZED, 0, 1, True),
        (fd.VECTORIZED, 1, 0, True),
    ]
    assert changes[1].text() == "REGRESSION: axpy: vectorized loop 1 -> 0 was at kern_old.f90:10"
    added = fd.diff([], new, set(), {"axpy"})
    assert added[0].scope == "added" and not added[0].regression and added[0].text().startswith("added procedure")


def test_feedback_nvfortran():
    old, new = _events("nvfortran", "old"), _events("nvfortran", "new")
    assert {(e.category, e.detail) for e in old} == {
        (fd.VECTORIZED, ""),
        (fd.IMPLICIT_COPY, "x"),
        (fd.IMPLICIT_COPY, "y"),
    }
    changes = {(c.category, c.detail): c for c in fd.diff(old, new, {"axpy"}, {"axpy"})}
    assert set(changes) == {(fd.VECTORIZED, ""), (fd.NOT_VECTORIZED, ""), (fd.SEQUENTIAL, "")}  # copies: same data
    assert all(c.regression for c in changes.values()) and changes[(fd.SEQUENTIAL, "")].lines == ["kern_new.f90:10"]


def test_feedback_ansi_log():
    """A log captured from FoBiS's coloured output: the colour codes must not become part of the file name."""
    line = "\x1b[1;31msrc/a.f90:12:6: missed: couldn't vectorize loop\x1b[0m"
    assert [(m.path, m.line, m.kind) for m in parse_log(line)] == [("src/a.f90", 12, "missed")]


# ── the command, for real ──────────────────────────────────────────────────────

KERNEL = """\
module kern
implicit none
contains
subroutine axpy(n, a, x, y)
integer, intent(in) :: n
real(8), intent(in) :: a, x(n)
real(8), intent(inout) :: y(n)
integer :: i
do i = 1, n
  y(i) = y(i) + a * x(i)
end do
end subroutine axpy
end module kern
"""
PROGRAM = """\
program app
use kern
implicit none
real(8), allocatable :: x(:), y(:)
integer :: step
allocate(x(100000), y(100000))
x = 1.0d0
y = 0.0d0
do step = 1, 20
  call axpy(size(x), 1.0d-3, x, y)
end do
print '(a,es24.16)', 'total = ', sum(y)
end program app
"""


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "kern.f90").write_text(KERNEL)
    (root / "src" / "app.f90").write_text(PROGRAM)
    (root / "fobos").write_text(
        "[modes]\nmodes = gnu\n\n[gnu]\ncompiler = gnu\nsrc = ./src/\nbuild_dir = ./build/\ncflags = -c -O3\n\n"
        "[case:axpy]\ntarget = src/app.f90\nquantities = stdout\n\n"
        "[bench:axpy]\nwarmup = 1\nmin_runs = 6\nmax_runs = 8\nwork = 2e6 updates\n\n"
        "[case:other]\ncommand = true\n"
    )
    (root / ".gitignore").write_text("build/\n.fobis/\n")
    for args in (
        ["init", "-q", "-b", "master"],
        ["add", "."],
        ["commit", "-qm", "feat: axpy"],
        ["tag", "-a", "v1", "-m", "v1"],
    ):
        subprocess.run([*GIT, *args], cwd=root, check=True, capture_output=True)
    monkeypatch.chdir(root)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr("tempfile.tempdir", str(scratch))
    return root


def _run(args, capsys):
    try:
        run_fobis(fake_args=args)
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_bench(project, capsys, tmp_path):
    code, out, err = _run(["bench", "--json", "--record"], capsys)
    data = json.loads(out)
    case = data["cases"][0]
    assert len(data["cases"]) == 1 and case["case"] == "axpy"  # only the declared benchmark
    assert case["status"] == "ok" and case["mode"] == "gnu" and 6 <= case["stats"]["new"]["n"] <= 8
    assert case["stats"]["new"]["unit"] == "updates/s" and case["recorded"] == "verification/bench/axpy.jsonl"
    assert "warm-up 1/1" in err and code == 0
    code, out, _ = _run(["bench", "axpy", "--runs", "6"], capsys)
    assert "vs recorded " in out and "speedup" in out and "6 runs" in out
    (project / "src" / "kern.f90").write_text(
        KERNEL.replace("do i = 1, n", "do i = 2, n").replace("a * x(i)", "a * x(i) + 1.0d-30 * y(i-1)")
    )
    code, out, _ = _run(["bench", "--compare", "v1", "--feedback", "--json", "--runs", "6"], capsys)
    case = json.loads(out)["cases"][0]
    assert set(case["stats"]) == {"old", "new"} and case["comparison"]["against"] == "v1"
    regressions = {(f["procedure"], f["category"]) for f in case["feedback"] if f["regression"]}
    assert regressions == {("axpy", fd.VECTORIZED), ("axpy", fd.NOT_VECTORIZED)}
    assert os.listdir(tmp_path / "scratch") == []  # scratch copies removed
    for args, message in (
        (["bench", "--feedback"], "--feedback needs --compare"),
        (["bench", "--compare", "v1", "--record"], "--record records the working tree alone"),
        (["bench", "nope"], "unknown case"),
        (["bench", "--compare", "nope"], "'nope' is not a revision"),
    ):
        code, out, err = _run(args, capsys)
        assert code == 2 and message in out + err
    (project / "src" / "kern.f90").write_text("module kern\nthis is not fortran\nend module kern\n")
    code, out, _ = _run(["bench", "--json"], capsys)
    assert code == 1 and json.loads(out)["cases"][0]["error"].startswith("new side: build failed")
