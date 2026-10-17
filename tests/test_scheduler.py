"""Tests for the scheduler runner (phase V10 of PLAN-verification.md): ``[scheduler]`` (user config then fobos),
the login-node guard, the Slurm job script, the submit/poll/collect cycle on an injected command runner (sbatch
failure, pending then running, no accounting, Ctrl-C cancels), and the commands for real with gfortran against a
FAKE Slurm on PATH (``sbatch`` runs the script synchronously in its ``--chdir``, ``squeue`` reports PENDING and
RUNNING a set number of times, ``sacct`` the recorded state, ``srun`` runs its command, a time limit kills the job):
``case run``, ``verify``, ``test`` and the guard. No real cluster is used: the plan's real exit criterion (one MPI
and one GPU case through a real Slurm) needs the user's cluster."""

from __future__ import annotations

import json
import os
import platform
import stat
import sys
from types import SimpleNamespace

import pytest

from fobis.fobis import run_fobis
from fobis.verification.scheduler import (
    Job,
    SchedulerConfig,
    SchedulerError,
    SlurmScheduler,
    guard_message,
    load_config,
    node_facts,
    on_login_node,
)

FAKE_SLURM = r"""
import os, re, subprocess, sys
state = os.environ["FAKE_SLURM_DIR"]
os.makedirs(state, exist_ok=True)
args = sys.argv[1:]
def path(*parts):
    return os.path.join(state, *parts)
if TOOL == "sbatch":
    script = args[-1]
    text = open(script).read()
    chdir = re.search(r"^#SBATCH --chdir=(.*)$", text, re.M).group(1)
    counter = path("counter")
    job = int(open(counter).read()) + 1 if os.path.exists(counter) else 1
    open(counter, "w").write(str(job))
    open(path(f"{job}.script"), "w").write(text)
    limit = float(os.environ.get("FAKE_SLURM_TIME_LIMIT", "0")) or None
    with open(os.path.join(chdir, f"slurm-{job}.out"), "w") as log:
        try:
            code = subprocess.run(["bash", script], cwd=chdir, stdout=log, stderr=log, timeout=limit).returncode
            result = "COMPLETED" if code == 0 else "FAILED"
        except subprocess.TimeoutExpired:
            log.write(f"slurmstepd: error: *** JOB {job} ON node01 CANCELLED DUE TO TIME LIMIT ***\n")
            code, result = 0, "TIMEOUT"
    open(path(f"{job}.state"), "w").write(f"{result}|{code}:0")
    open(path(f"{job}.polls"), "w").write(os.environ.get("FAKE_SLURM_PENDING", "0"))
    print(f"{job};cluster")
elif TOOL == "squeue":
    job = args[args.index("-j") + 1]
    polls = int(open(path(f"{job}.polls")).read())
    if polls > 0:
        open(path(f"{job}.polls"), "w").write(str(polls - 1))
        print("PENDING" if polls > 1 else "RUNNING")
elif TOOL == "sacct":
    if os.environ.get("FAKE_SLURM_NO_ACCOUNTING"):
        sys.exit("sacct: error: Slurm accounting storage is disabled")
    job = args[args.index("-j") + 1]
    print(open(path(f"{job}.state")).read())
elif TOOL == "scancel":
    open(path("cancelled"), "a").write(args[0] + "\n")
elif TOOL == "srun":
    os.execvp(args[0], args)
"""


@pytest.fixture
def fake_slurm(tmp_path, monkeypatch):
    bin_dir = tmp_path / "fake-slurm-bin"
    bin_dir.mkdir()
    for tool in ("sbatch", "squeue", "sacct", "scancel", "srun"):
        launcher = bin_dir / tool
        launcher.write_text(f"#!{sys.executable}\nTOOL = {tool!r}\n{FAKE_SLURM}")
        launcher.chmod(launcher.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_SLURM_DIR", str(tmp_path / "fake-slurm-state"))
    return tmp_path / "fake-slurm-state"


# ── configuration, guard, script ───────────────────────────────────────────────


class FakeFobos:
    def __init__(self, text):
        import configparser

        self.fobos = configparser.RawConfigParser()
        self.fobos.read_string(text)


def test_config(tmp_path):
    user = tmp_path / "config.ini"
    user.write_text("[scheduler]\npartition = cpu\naccount = proj1\nlogin_nodes = login*, frontend\n")
    config = load_config(FakeFobos("[scheduler]\npartition = gpu\noptions = --exclusive\n  --mem=8G\n"), str(user))
    assert (config.partition, config.account, config.options) == ("gpu", "proj1", ["--exclusive", "--mem=8G"])
    assert config.login_nodes == ["login*", "frontend"] and config.launcher == "srun"
    assert on_login_node(config, "login02.cluster.org") == "login02.cluster.org"
    assert on_login_node(config, "frontend.cluster.org") and not on_login_node(config, "node017")
    assert "--runner slurm" in guard_message("login02")
    with pytest.raises(SchedulerError, match="unknown key"):
        load_config(FakeFobos("[scheduler]\nqueue = x\n"), str(tmp_path / "none.ini"))
    with pytest.raises(SchedulerError, match="kind 'pbs' is not supported"):
        load_config(FakeFobos("[scheduler]\nkind = pbs\n"), str(tmp_path / "none.ini"))


def test_a_percent_in_the_user_config_is_literal(tmp_path):
    """The user config was read with interpolation: a lone % (Slurm's %j, 50%) raised InterpolationSyntaxError."""
    user = tmp_path / "config.ini"
    user.write_text("[scheduler]\noptions = --comment=50%\n  --output=slurm-%j.out\n")
    config = load_config(None, str(user))
    assert config.options == ["--comment=50%", "--output=slurm-%j.out"]


def test_script():
    config = SchedulerConfig(partition="gpu", account="p1", options=["--exclusive"], setup=["module load nvhpc/26"])
    job = Job(
        "sod",
        ["srun", "./sod", "in put.nml"],
        "/scratch/run",
        ranks=4,
        threads=2,
        gpus=1,
        timeout=90,
        env={"OMP_NUM_THREADS": "2", "MSG": "a b"},
    )
    script = SlurmScheduler(config).script(job)
    for line in (
        "#SBATCH --job-name=fobis-sod",
        "#SBATCH --chdir=/scratch/run",
        "#SBATCH --ntasks=4",
        "#SBATCH --cpus-per-task=2",
        "#SBATCH --time=4",  # 90 s rounded up to minutes, plus 2 for the setup lines
        "#SBATCH --gpus=1",
        "#SBATCH --partition=gpu",
        "#SBATCH --account=p1",
        "#SBATCH --exclusive",
        "module load nvhpc/26",
        "export MSG='a b'",
        "srun ./sod 'in put.nml' > fobis-stdout.txt 2> fobis-stderr.txt",
    ):
        assert line in script.splitlines(), line
    assert "--gpus" not in SlurmScheduler(SchedulerConfig()).script(Job("t", ["./t"], "/r"))


# ── submit / poll / collect on an injected runner ──────────────────────────────


def _reply(stdout="", code=0, stderr=""):
    return SimpleNamespace(returncode=code, stdout=stdout, stderr=stderr)


def test_submit_cycle(tmp_path):
    calls = []
    replies = {
        "sbatch": [_reply("42;cluster\n")],
        "squeue": [_reply("PENDING\n"), _reply("RUNNING\n"), _reply("")],
        "sacct": [_reply(code=1, stderr="accounting disabled")],
    }

    def run(args, **_kw):
        calls.append(args[0])
        if args[0] == "sbatch":  # the job "ran": its files are there
            (tmp_path / "fobis-exit.txt").write_text("3 100.0 101.5\n")
            (tmp_path / "fobis-stdout.txt").write_text("x = 1\n")
        return replies[args[0]].pop(0)

    seen = []
    scheduler = SlurmScheduler(SchedulerConfig(poll=0), run=run, sleep=lambda s: None, progress=seen.append)
    done = scheduler.submit(Job("c", ["./c"], str(tmp_path)))
    assert (done.job_id, done.state, done.exit_code, done.elapsed, done.stdout) == ("42", "FAILED", 3, 1.5, "x = 1\n")
    assert calls == ["sbatch", "squeue", "squeue", "squeue", "sacct"]
    assert seen == ["job 42 submitted (c)", "job 42: pending", "job 42: running"]
    refused = SlurmScheduler(
        SchedulerConfig(), run=lambda a, **k: _reply(code=1, stderr="sbatch: error: invalid partition")
    )
    with pytest.raises(SchedulerError, match="invalid partition"):
        refused.submit(Job("c", ["./c"], str(tmp_path)))
    cancelled = []

    def interrupted(args, **_kw):
        if args[0] == "sbatch":
            return _reply("7\n")
        if args[0] == "scancel":
            cancelled.append(args[1])
            return _reply()
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        SlurmScheduler(SchedulerConfig(), run=interrupted).submit(Job("c", ["./c"], str(tmp_path)))
    assert cancelled == ["7"]  # Ctrl-C does not leave the job in the queue


# ── the commands, for real, against the fake Slurm ─────────────────────────────

PROGRAM = """\
program app
implicit none
character(len=32) :: arg
integer :: n
call get_command_argument(1, arg)
read(arg, *) n
call execute_command_line('sleep ' // trim(arg), wait=.true.)
print '(a,i0)', 'value = ', 2 * n
end program app
"""


@pytest.fixture
def project(tmp_path, monkeypatch, fake_slurm):
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "test").mkdir()
    (root / "src" / "app.f90").write_text(PROGRAM)
    (root / "test" / "t_ok.f90").write_text("program t_ok\nprint *, 'fine'\nend program t_ok\n")
    (root / "test" / "t_bad.f90").write_text("program t_bad\nerror stop 3\nend program t_bad\n")
    (root / "fobos").write_text(
        "[modes]\nmodes = gnu\n\n[gnu]\ncompiler = gnu\nsrc = ./src/ ./test/\nbuild_dir = ./build/\n\n"
        "[scheduler]\npartition = debug\npoll = 0\n\n"
        "[case:app]\ntarget = src/app.f90\nargs = 0\nquantities = stdout\n\n"
        "[case:mpi]\ntarget = src/app.f90\nargs = 0\nranks = 2\nthreads = 3\nquantities = stdout\n\n"
        "[case:slow]\ntarget = src/app.f90\nargs = 5\nquantities = stdout\n"
    )
    monkeypatch.chdir(root)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    return root


def _run(args, capsys):
    try:
        run_fobis(fake_args=args)
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_node_facts():
    text = "host=gnode01\nos=Linux 4.18\ncpu=Intel Xeon Gold 6338\ncores=8\ngpu=GPU 0: NVIDIA A30 (UUID: GPU-1)\n"
    assert node_facts(text) == {
        "host": "gnode01",
        "os": "Linux 4.18",
        "cpu": "Intel Xeon Gold 6338",
        "cores": 8,
        "gpus": ["GPU 0: NVIDIA A30 (UUID: GPU-1)"],
    }
    no_gpu = "host=gnode01\ncores=1\ngpu=No devices found.\n"  # nvidia-smi -L in a job given no GPU (real)
    assert node_facts(no_gpu) == {"host": "gnode01", "cores": 1, "gpus": []}
    assert node_facts("gnode02\n") == {"host": "gnode02"}  # a host file of an older FoBiS
    assert node_facts("") == {}


def test_case_run_through_slurm(project, fake_slurm, capsys, monkeypatch):
    monkeypatch.setenv("FAKE_SLURM_PENDING", "2")
    code, out, err = _run(["case", "run", "app", "mpi", "--runner", "slurm", "--json"], capsys)
    results = {r["case"]: r for r in json.loads(out)["results"]}
    assert code == 0 and results["app"]["status"] == "ok" and results["app"]["quantities"]["value"]["values"] == [0]
    scheduler = results["mpi"]["provenance"]["scheduler"]
    assert scheduler["partition"] == "debug" and scheduler["state"] == "COMPLETED"
    assert scheduler["node"] == platform.node() and scheduler["job"] == "2"
    machine = results["mpi"]["provenance"]["machine"]  # written by the job on its node (here: this host)
    assert machine["host"] == platform.node() and machine["cores"] >= 1 and isinstance(machine["gpus"], list)
    script = (fake_slurm / "2.script").read_text()
    assert "#SBATCH --ntasks=2" in script and "#SBATCH --cpus-per-task=3" in script
    assert "export OMP_NUM_THREADS=3" in script and "\nsrun " in script  # the scheduler's launcher, not mpirun
    assert "job 1 submitted (app)" in err and "job 1: pending" in err and "job 1: running" in err
    monkeypatch.setenv("FAKE_SLURM_TIME_LIMIT", "1")
    code, out, _ = _run(["case", "run", "slow", "--runner", "slurm", "--json"], capsys)
    slow = json.loads(out)["results"][0]
    assert code == 1 and slow["status"] == "timeout" and "CANCELLED DUE TO TIME LIMIT" in slow["stderr"]
    monkeypatch.delenv("FAKE_SLURM_TIME_LIMIT")
    monkeypatch.setenv("FAKE_SLURM_NO_ACCOUNTING", "1")
    assert _run(["verify", "app", "--update", "--runner", "slurm"], capsys)[0] == 0
    code, out, _ = _run(["verify", "app", "--runner", "slurm", "--json"], capsys)
    assert code == 0 and json.loads(out)["cases"][0]["status"] == "pass"  # no accounting: the job's own exit file


def test_test_through_slurm(project, capsys):
    code, out, err = _run(["test", "--runner", "slurm", "--json"], capsys)
    results = {r["name"]: r for r in json.loads(out)["results"]}
    assert code == 1 and results["t_ok"]["status"] == "passed" and results["t_bad"]["status"] == "failed"
    assert results["t_bad"]["exit_code"] == 3 and "submitted (t_ok)" in err
    assert (project / ".fobis" / "runs" / "test-jobs" / "t_ok" / "fobis-job.sh").is_file()


def test_login_node_guard(project, capsys):
    xdg = os.environ["XDG_CONFIG_HOME"]
    os.makedirs(os.path.join(xdg, "fobis"))
    with open(os.path.join(xdg, "fobis", "config.ini"), "w") as handle:
        handle.write(f"[scheduler]\nlogin_nodes = {platform.node()}\n")
    code, out, _ = _run(["case", "run", "app", "mpi", "--json"], capsys)
    results = {r["case"]: r for r in json.loads(out)["results"]}
    assert code == 1 and results["app"]["status"] == "ok"  # a serial case may run on the login node
    assert results["mpi"]["status"] == "error" and "refusing to run an MPI or GPU case" in results["mpi"]["stderr"]
    code, out, err = _run(["case", "run", "mpi"], capsys)
    assert code == 1 and "  error\n" in out + err and "exit None" not in out + err  # never started: no exit status
    assert _run(["case", "run", "mpi", "--runner", "slurm"], capsys)[0] == 0
    assert _run(["case", "run", "app", "--runner", "pbs"], capsys)[0] == 2
