"""The ready-queue scheduler (issue #218, phase 3)."""

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import threading
import time

import pytest

from fobis import scheduler
from fobis.fobis import run_fobis
from fobis.FoBiSConfig import FoBiSConfig
from fobis.utils import BuildFailed, dependency_closure

GFORTRAN = shutil.which("gfortran") is not None


class _File:
    """A fake parsed file (hashable, as ParsedFile)."""

    def __init__(self, name, deps=()):
        self.name = name
        self.pfile_dep = list(deps)
        self.include = False
        self.to_compile = True
        self.c_source = False
        self.pfile_dep_all = None


def _graph(size, seed):
    """A random DAG of fake parsed files: file i depends on some files j < i."""
    rng = random.Random(seed)
    files = []
    for index in range(size):
        deps = rng.sample(files, k=min(len(files), rng.randint(0, 3))) if files else []
        files.append(_File(f"f{index:03d}.f90", deps))
    for pfile in files:
        pfile.pfile_dep_all = dependency_closure(pfile)
    return files


class _Builder:
    def __init__(self, jobs, fail=()):
        self.jobs = jobs
        self.obj_dir = "/nonexistent"
        self.timings = None
        self.fail = set(fail)
        self.lock = threading.Lock()
        self.events = []  # (name, start, end)
        self.running = 0
        self.peak = 0
        self.lines = []

    def _compile_command(self, file_to_compile):
        return [(file_to_compile.name, None)]

    def print_n(self, text):
        self.lines.append(text)

    print_w = print_n


@pytest.fixture
def fake_compile(monkeypatch):
    def install(builder, delay=0.002):
        def run(steps):
            name = steps[0][0]
            with builder.lock:
                builder.running += 1
                builder.peak = max(builder.peak, builder.running)
            start = time.monotonic()
            time.sleep(delay)
            end = time.monotonic()
            with builder.lock:
                builder.running -= 1
                builder.events.append((name, start, end))
            return [1, f"error in {name}"] if name in builder.fail else [0, ""]

        monkeypatch.setattr(scheduler, "syswork_steps", run)

    return install


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("jobs", [1, 3, 8])
def test_order_and_concurrency_on_random_graphs(fake_compile, seed, jobs):
    files = _graph(40, seed)
    builder = _Builder(jobs)
    fake_compile(builder)
    result = scheduler.compile_queue(builder, [files[-1], *files[:5]], files[5:20])
    times = {name: (start, end) for name, start, end in builder.events}
    reachable = {p.name for root in [files[-1], *files[:20]] for p in root.pfile_dep_all}
    assert set(times) == reachable
    assert result.compiled == len(reachable)
    for pfile in files:
        if pfile.name not in times:
            continue
        for dep in pfile.pfile_dep:
            assert times[dep.name][1] <= times[pfile.name][0], (dep.name, pfile.name)
    assert builder.peak <= jobs
    assert all(not p.to_compile for p in files if p.name in reachable)


def test_up_to_date_files_are_not_compiled(fake_compile):
    files = _graph(10, 1)
    for pfile in files[:5]:
        pfile.to_compile = False
    builder = _Builder(2)
    fake_compile(builder)
    scheduler.compile_queue(builder, files, [])
    assert {name for name, _, _ in builder.events} == {p.name for p in files[5:]}


def test_a_required_failure_stops_new_compiles(fake_compile):
    # a chain a <- b <- c plus independent d: a fails, b and c never start, the build fails
    a, b, c, d = (_File(n) for n in "abcd")
    a.pfile_dep, b.pfile_dep, c.pfile_dep, d.pfile_dep = [], [a], [b], []
    for pfile in (a, b, c, d):
        pfile.pfile_dep_all = dependency_closure(pfile)
    builder = _Builder(1, fail={"a"})
    fake_compile(builder)
    with pytest.raises(BuildFailed):
        scheduler.compile_queue(builder, [c, d], [])
    started = [name for name, _, _ in builder.events]
    assert "b" not in started and "c" not in started
    assert a.to_compile  # compiled again by the next build


def test_an_optional_failure_blocks_its_dependents_only(fake_compile):
    # m (module) <- s1 (file without modules); t (target) independent: m fails, s1 is reported, t is built
    m, s1, t = (_File(n) for n in ("m", "s1", "t"))
    m.pfile_dep, s1.pfile_dep, t.pfile_dep = [], [m], []
    for pfile in (m, s1, t):
        pfile.pfile_dep_all = dependency_closure(pfile)
    builder = _Builder(2, fail={"m"})
    fake_compile(builder)
    result = scheduler.compile_queue(builder, [t], [s1])
    assert result.failed == {"m": ("m", "error in m"), "s1": ("m", "error in m")}
    assert {name for name, _, _ in builder.events} == {"m", "t"}


def test_priority_follows_the_longest_chain(fake_compile):
    # one job: the long chain's head (l0) starts before the lone file (z), whatever the names
    chain = []
    for index in range(4):
        chain.append(_File(f"l{index}", chain[-1:]))
    lone = _File("a_lone")
    for pfile in (*chain, lone):
        pfile.pfile_dep_all = dependency_closure(pfile)
    builder = _Builder(1)
    fake_compile(builder)
    scheduler.compile_queue(builder, [chain[-1], lone], [])
    assert builder.events[0][0] == "l0"


# --- jobs ---------------------------------------------------------------------------------------------------------


def _jobs(tmp_path, monkeypatch, fobos, *args):
    (tmp_path / "fobos").write_text(fobos)
    monkeypatch.chdir(tmp_path)
    return FoBiSConfig(fake_args=["build", *args]).cliargs.jobs


def test_command_line_jobs_win_over_the_mode(tmp_path, monkeypatch):
    fobos = "[default]\ncompiler = gnu\njobs = 4\n"
    assert _jobs(tmp_path, monkeypatch, fobos, "-j", "2") == 2
    assert _jobs(tmp_path, monkeypatch, fobos) == 4
    assert _jobs(tmp_path, monkeypatch, "[default]\ncompiler = gnu\n") is None


def test_available_cpus():
    assert scheduler.available_cpus() >= 1
    if hasattr(os, "sched_getaffinity"):
        assert scheduler.available_cpus() == len(os.sched_getaffinity(0))


# --- real builds --------------------------------------------------------------------------------------------------

SUBMODULES = {
    "shape.f90": "module shape\ninterface\nmodule subroutine area()\nend subroutine\n"
    "module subroutine perimeter()\nend subroutine\nend interface\nend module shape\n",
    "shape_area.f90": "submodule(shape) shape_area\ninteger :: shared = 3\ncontains\nmodule subroutine area()\n"
    "print *, 'area', shared\nend subroutine\nend submodule shape_area\n",
    "shape_perimeter.f90": "submodule(shape:shape_area) shape_perimeter\ncontains\n"
    "module subroutine perimeter()\nprint *, 'perimeter', shared\nend subroutine\nend submodule shape_perimeter\n",
    "main.f90": "program main\nuse shape\ncall area()\ncall perimeter()\nend program main\n",
}


@pytest.mark.skipif(not GFORTRAN, reason="gfortran not on PATH")
@pytest.mark.parametrize("scheduler_name", ["queue", "levels"])
def test_child_submodule_after_its_parent(tmp_path, monkeypatch, capsys, scheduler_name):
    src = tmp_path / "src"
    src.mkdir()
    for name, text in SUBMODULES.items():
        (src / name).write_text(text)
    monkeypatch.chdir(tmp_path)
    run_fobis(fake_args=["build", "--src", "src", "-j", "4", "--scheduler", scheduler_name])
    out = capsys.readouterr().out
    if scheduler_name == "queue":
        lines = [line for line in out.splitlines() if line.startswith("Compiling src/")]
        order = [line.split()[1] for line in lines]
        assert order.index("src/shape_area.f90") < order.index("src/shape_perimeter.f90")
        assert len(lines) == 4 and lines[-1].endswith("[4/4]")
    assert os.path.isfile(tmp_path / "main")


@pytest.mark.skipif(not GFORTRAN, reason="gfortran not on PATH")
def test_unknown_scheduler(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "p.f90").write_text("program p\nend program\n")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exit_info:
        run_fobis(fake_args=["build", "--src", "src", "--scheduler", "fast"])
    assert exit_info.value.code == 2


@pytest.mark.skipif(not GFORTRAN, reason="gfortran not on PATH")
def test_pre_build_runs_before_any_compile(tmp_path, monkeypatch):
    # tests/build-test2's pattern: a pre_build rule compiles a module the target uses (the queue compiled first)
    (tmp_path / "src").mkdir()
    (tmp_path / "ext").mkdir()
    (tmp_path / "ext" / "dep.f90").write_text("module dep\ninteger, parameter :: k = 3\nend module dep\n")
    (tmp_path / "src" / "main.f90").write_text("program main\nuse dep\nprint *, k\nend program main\n")
    (tmp_path / "fobos").write_text(
        "[default]\ncompiler = gnu\nsrc = ./src/\ntarget = main.f90\ninclude = ./pre/\nlibs = ./pre/dep.o\n"
        "pre_build = precompile\n\n[rule-precompile]\nrule_1 = mkdir -p pre\n"
        "rule_2 = gfortran -c ext/dep.f90 -J pre -o pre/dep.o\n"
    )
    monkeypatch.chdir(tmp_path)
    run_fobis(fake_args=["build"])
    assert os.path.isfile(tmp_path / "main")


# --- interfaces first (phase 6) ------------------------------------------------------------------------------------

SLOW = (
    "module slow\nimplicit none\ninteger, parameter :: n = 3\ncontains\nfunction work() result(r)\ninteger :: r\n"
    "r = n\nend function work\nend module slow\n"
)
USER = "module user\nuse slow, only : n\ninteger, parameter :: m = 2 * n\nend module user\n"
MAIN = "program main\nuse slow, only : work\nuse user, only : m\nprint *, work() + m\nend program main\n"


def _interfaces_project(root):
    src = root / "src"
    src.mkdir()
    for name, text in {"slow.f90": SLOW, "user.f90": USER, "main.f90": MAIN}.items():
        (src / name).write_text(text)


@pytest.mark.parametrize(
    "compiler",
    [
        pytest.param("gnu", marks=pytest.mark.skipif(not GFORTRAN, reason="no gfortran")),
        pytest.param("nvfortran", marks=pytest.mark.skipif(not shutil.which("nvfortran"), reason="no nvfortran")),
    ],
)
def test_interfaces_first_builds_the_same_program(tmp_path, monkeypatch, capsys, compiler):
    _interfaces_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    args = ["build", "--src", "src", "--target", "main.f90", "--compiler", compiler, "-j", "4"]
    run_fobis(fake_args=[*args, "--interfaces-first", "--timings"])
    assert subprocess.run([str(tmp_path / "main")], capture_output=True, text=True).stdout.split() == ["9"]
    records = json.loads((tmp_path / "obj" / ".fobis-timings.json").read_text())["records"]
    by = {(r["kind"], r["file"]): r for r in records}
    interface_end = by[("interface", "src/slow.f90")]["start"] + by[("interface", "src/slow.f90")]["seconds"]
    # the files using slow wait for its module files only; its object waits for them too
    for kind, name in (("interface", "src/user.f90"), ("compile", "src/main.f90"), ("compile", "src/slow.f90")):
        assert by[(kind, name)]["start"] >= interface_end - 1e-3
    assert ("interface", "src/main.f90") not in by  # a program, nothing uses it: compiled once
    assert sorted(os.listdir(tmp_path / "obj" / ".fobis-object-mods")) == ["slow", "user"]
    capsys.readouterr()


@pytest.mark.skipif(not GFORTRAN, reason="no gfortran")
def test_interfaces_first_refuses_differing_module_files(tmp_path, monkeypatch, capsys):
    # a compiler whose syntax-only module files differ from its full compile's: the build fails, objects removed
    real = shutil.which("gfortran")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    wrapper = bindir / "gfortran"
    wrapper.write_text(
        "#!/bin/bash\n"
        f'"{real}" "$@" || exit $?\n'
        'if [[ " $* " == *" -fsyntax-only "* ]]; then for f in mod/*.mod; do echo x >> "$f"; done; fi\n'
    )
    wrapper.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
    _interfaces_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        run_fobis(fake_args=["build", "--src", "src", "--target", "main.f90", "--interfaces-first", "-j", "2"])
    out = capsys.readouterr().out
    assert "interfaces_first: the module files written by the syntax-only compile differ" in out
    assert not [name for name in os.listdir(tmp_path / "obj") if name.endswith(".o")]
    run_fobis(fake_args=["build", "--src", "src", "--target", "main.f90", "-j", "2"])  # without it: builds
    assert subprocess.run([str(tmp_path / "main")], capture_output=True, text=True).stdout.split() == ["9"]
