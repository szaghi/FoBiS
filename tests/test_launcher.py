"""``fobis run --launcher`` / ``fobis test --launcher``: the programs started through a launcher (an MPI launcher, a
debugger, a checker) with ``{ranks}`` replaced by ``--ranks``; the command line wins over the mode's ``launcher``
key, which wins over ``[test] launcher``; a launcher that is not on PATH, or ranks on a declared login node, stop
before anything is built; under ``--runner slurm`` the launcher goes into the job script. Real gfortran builds; a
stub launcher on PATH records how it was called; the real MPI test runs only when ``mpirun`` is on PATH."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys

import pytest

from fobis.fobis import run_fobis
from tests.test_scheduler import fake_slurm  # noqa: F401 (fixture)

pytestmark = pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran")

APP = (
    "program app\ncharacter(32) :: word\ncall get_command_argument(1, word)\nprint '(a)', 'app '//trim(word)\n"
    "if (word == 'fail') error stop 3\nend program app\n"
)
# records its arguments (one line per call) in $LAUNCHED, drops '-np N', then runs the program
STUB = (
    f"#!{sys.executable}\nimport os, sys\nargs = sys.argv[1:]\n"
    "open(os.environ['LAUNCHED'], 'a').write(os.path.basename(sys.argv[0]) + ' ' + ' '.join(args) + '\\n')\n"
    "while args[:1] == ['-np']:\n    args = args[2:]\nos.execv(args[0], args)\n"
)


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "test").mkdir()
    (tmp_path / "src" / "app.f90").write_text(APP)
    (tmp_path / "test" / "t_ok.f90").write_text("program t_ok\nprint *, 'ok'\nend program t_ok\n")
    (tmp_path / "fobos").write_text(
        "[modes]\nmodes = gnu\n\n[gnu]\ncompiler = gnu\nsrc = ./src/ ./test/\nbuild_dir = ./build/\n"
        "target = src/app.f90\n"
    )
    tools = tmp_path / "tools"
    tools.mkdir()
    for name in ("wrap", "other", "mpirun"):
        (tools / name).write_text(STUB)
        (tools / name).chmod(0o755)
    monkeypatch.setenv("PATH", f"{tools}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("LAUNCHED", str(tmp_path / "launched.txt"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _launched(project) -> list[str]:
    path = project / "launched.txt"
    return path.read_text().splitlines() if path.exists() else []


def _fobis(args, cwd) -> subprocess.CompletedProcess:
    """``fobis run`` replaces the process's exit status with the program's: run it as a subprocess."""
    return subprocess.run([sys.executable, "-m", "fobis", *args], cwd=cwd, capture_output=True, text=True)


def _run(args, capsys) -> tuple[int, str]:
    try:
        run_fobis(fake_args=args)
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def test_run_through_a_launcher_with_ranks_and_program_arguments(project):
    done = _fobis(["run", "--launcher", "wrap -np {ranks}", "--ranks", "3", "--", "hello"], project)
    assert done.returncode == 0 and "app hello" in done.stdout
    assert _launched(project) == ["wrap -np 3 build/app hello"]


def test_the_program_exit_status_passes_through_the_launcher(project):
    done = _fobis(["run", "--launcher", "wrap", "--", "fail"], project)
    assert done.returncode == 3 and _launched(project) == ["wrap build/app fail"]


def test_ranks_default_to_one_and_ranks_alone_use_mpirun(project):
    assert _fobis(["run", "--launcher", "wrap -np {ranks}"], project).returncode == 0
    assert _fobis(["run", "--ranks", "2"], project).returncode == 0
    assert _launched(project) == ["wrap -np 1 build/app", "mpirun -np 2 build/app"]


def test_dry_run_shows_the_launcher(project):
    done = _fobis(["run", "--dry-run", "--launcher", "wrap --args"], project)  # a stub: CI machines have no gdb
    assert "[run]    wrap --args build/app" in done.stdout + done.stderr


def test_a_launcher_not_on_path_stops_before_building(project, capsys):
    code, out = _run(["run", "--launcher", "nothere -x"], capsys)
    assert code == 2 and "'nothere'" in out and "not on PATH" in out
    assert not (project / "build").exists()
    code, out = _run(["test", "--launcher", "nothere"], capsys)
    assert code == 2 and not (project / "build").exists()


def test_test_programs_go_through_the_launcher(project, capsys):
    code, out = _run(["test", "--launcher", "wrap -np {ranks}", "--ranks", "2"], capsys)
    assert code == 0 and "1 passed" in out
    assert _launched(project) == ["wrap -np 2 build/test/t_ok"]


def test_precedence_command_line_then_mode_then_test_section(project, capsys):
    fobos = project / "fobos"
    fobos.write_text(fobos.read_text() + "launcher = other\n\n[test]\nlauncher = mpirun -np {ranks}\n")
    assert _run(["test"], capsys)[0] == 0  # the mode's key over [test]
    assert _run(["test", "--launcher", "wrap"], capsys)[0] == 0  # the command line over both
    fobos.write_text(fobos.read_text().replace("launcher = other\n", ""))
    assert _run(["test", "--json"], capsys)[0] == 0  # [test] when the mode has none
    assert _launched(project) == ["other build/test/t_ok", "wrap build/test/t_ok", "mpirun -np 1 build/test/t_ok"]


def test_ranks_on_a_login_node_are_refused(project, capsys):
    config = project / "xdg" / "fobis"
    config.mkdir(parents=True)
    (config / "config.ini").write_text(f"[scheduler]\nlogin_nodes = {platform.node()}\n")
    code, out = _run(["run", "--ranks", "2"], capsys)  # run has no --runner: it was told to use one
    assert code == 2 and "login node" in out and "run it on a compute node (inside salloc, or a batch job)" in out
    code, out = _run(["test", "--ranks", "2"], capsys)
    assert code == 2 and "run it through the scheduler with --runner slurm" in out
    assert _fobis(["run", "--launcher", "wrap"], project).returncode == 0  # no ranks: a debugger is fine


def test_slurm_jobs_carry_the_launcher(project, capsys, fake_slurm):  # noqa: F811
    fobos = project / "fobos"
    fobos.write_text(fobos.read_text() + "\n[scheduler]\npartition = debug\npoll = 0\n")
    code, out = _run(["test", "--runner", "slurm", "--launcher", "wrap"], capsys)
    assert code == 0, out
    script = (fake_slurm / "1.script").read_text()
    assert f"wrap {project}/build/test/t_ok" in script
    code, out = _run(["test", "--runner", "slurm", "--ranks", "2"], capsys)  # ranks alone: the scheduler's srun
    assert code == 0, out
    script = (fake_slurm / "2.script").read_text()
    assert "#SBATCH --ntasks=2" in script and f"srun {project}/build/test/t_ok" in script


@pytest.mark.skipif(shutil.which("mpirun") is None or shutil.which("mpif90") is None, reason="MPI")
def test_a_real_mpi_test(tmp_path, monkeypatch, capsys):
    (tmp_path / "test").mkdir()
    (tmp_path / "test" / "t_mpi.f90").write_text(
        "program t_mpi\nuse mpi\ninteger :: rank, size, ierr\ncall mpi_init(ierr)\n"
        "call mpi_comm_size(mpi_comm_world, size, ierr)\nif (size /= 2) error stop 1\ncall mpi_finalize(ierr)\n"
        "end program t_mpi\n"
    )
    (tmp_path / "fobos").write_text("[default]\ncompiler = gnu\nmpi = True\nsrc = ./test/\nbuild_dir = ./build/\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    code, out = _run(["test", "--launcher", "mpirun --oversubscribe -np {ranks}", "--ranks", "2"], capsys)
    assert code == 0, out
