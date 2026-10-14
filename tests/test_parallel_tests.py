"""``fobis test -j N``: test programs built one after the other, then run up to N at a time, reported in the same
order and with the same statuses as a serial run; a test started with ranks takes as many slots; ``[test] jobs``
sets the default; ``--no-build`` runs the programs a previous ``fobis test`` built. Real gfortran builds; the
programs sleep one second, so the bounds on the elapsed time have a wide margin."""

from __future__ import annotations

import json
import os
import shutil
import sys
import time

import pytest

from fobis.fobis import run_fobis

pytestmark = pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran")

SLEEPER = "program {name}\ncall execute_command_line('sleep 1')\nend program {name}\n"
STUB = f"#!{sys.executable}\nimport os, sys\nargs = sys.argv[1:]\nwhile args[:1] == ['-np']:\n    args = args[2:]\nos.execv(args[0], args)\n"


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "test").mkdir()
    for index in range(1, 5):
        (tmp_path / "test" / f"t_sleep{index}.f90").write_text(SLEEPER.format(name=f"t_sleep{index}"))
    (tmp_path / "fobos").write_text("[default]\ncompiler = gnu\nsrc = ./test/\nbuild_dir = ./build/\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    return tmp_path


def _test(args, capsys) -> tuple[int, str, float]:
    start = time.monotonic()
    try:
        run_fobis(fake_args=["test", "--no-build", *args])
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    elapsed = time.monotonic() - start
    return code, capsys.readouterr().out, elapsed


@pytest.fixture
def built(project, capsys):
    """The test programs built once; the timed runs use --no-build."""
    run_fobis(fake_args=["test", "--quiet"])
    capsys.readouterr()
    return project


def test_parallel_runs_are_faster_and_report_like_serial_ones(built, capsys):
    code, serial, elapsed_serial = _test([], capsys)
    assert code == 0 and elapsed_serial > 4.0
    code, parallel, elapsed_parallel = _test(["-j", "4"], capsys)
    assert code == 0 and elapsed_parallel < 2.5
    names = [line.split()[1] for line in parallel.splitlines() if line.strip().startswith(("PASS", "FAIL"))]
    assert names == ["t_sleep1", "t_sleep2", "t_sleep3", "t_sleep4"]  # discovery order, not completion order
    assert "elapsed with -j 4" in parallel and "elapsed" not in serial


def test_json_keeps_the_order_and_tells_the_elapsed_time(built, capsys):
    code, out, _ = _test(["-j", "4", "--json"], capsys)
    data = json.loads(out)
    assert code == 0 and [r["name"] for r in data["results"]] == ["t_sleep1", "t_sleep2", "t_sleep3", "t_sleep4"]
    assert data["jobs"] == 4 and 0.9 < data["elapsed"] < 2.5


def test_failures_and_timeouts_in_parallel(project, capsys):
    (project / "test" / "t_bad.f90").write_text("program t_bad\nerror stop 3\nend program t_bad\n")
    with pytest.raises(SystemExit):  # builds it, and the test fails
        run_fobis(fake_args=["test", "--quiet", "--filter", "t_bad"])
    capsys.readouterr()
    run_fobis(fake_args=["test", "--quiet", "--filter", "t_sleep*"])
    capsys.readouterr()
    code, out, _ = _test(["-j", "4", "--timeout", "0.5", "--json"], capsys)
    results = {r["name"]: r for r in json.loads(out)["results"]}
    assert code == 1 and results["t_bad"]["exit_code"] == 3
    assert all(results[f"t_sleep{i}"]["status"] == "timeout" for i in range(1, 5))


def test_a_test_with_ranks_takes_as_many_slots(built, capsys, monkeypatch, tmp_path):
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "wrap").write_text(STUB)
    (tools / "wrap").chmod(0o755)
    monkeypatch.setenv("PATH", f"{tools}{os.pathsep}{os.environ['PATH']}")
    code, _, elapsed = _test(["-j", "4", "--launcher", "wrap -np {ranks}", "--ranks", "2"], capsys)
    assert code == 0 and 1.9 < elapsed < 3.5  # 4 tests x 2 ranks on 4 slots: two at a time


def test_the_test_section_sets_the_default(built, capsys):
    fobos = built / "fobos"
    fobos.write_text(fobos.read_text() + "\n[test]\njobs = 4\n")
    code, out, elapsed = _test([], capsys)
    assert code == 0 and elapsed < 2.5 and "with -j 4" in out
    code, _, elapsed = _test(["-j", "1"], capsys)  # the command line wins
    assert code == 0 and elapsed > 4.0


def test_no_build_runs_what_a_previous_test_built(built, capsys):
    code, out, _ = _test(["--filter", "t_sleep1"], capsys)
    assert code == 0 and "1 passed" in out and "binary not found" not in out
