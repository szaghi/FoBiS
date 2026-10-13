"""Tests for fobis.verification (phase V1 of PLAN-verification.md): probes on genuine outputs (text, JSON, a Fortran
unformatted file written by gfortran), case declarations, the runner on real programs (ok, missing quantity, error
stop, timeout, build failures, launcher, inputs, fresh run directory), provenance on real git repositories, and the
``fobis case`` / ``fobis provenance`` CLI."""

from __future__ import annotations

import json
import math
import os
import subprocess

import pytest

from fobis.fobis import run_fobis
from fobis.verification import CaseError, LocalRunner, ProbeError, RunOutput, extract, parse_probes
from fobis.verification.case import parse_case
from fobis.verification.probes import numbers, parse_h5dump, to_float
from fobis.verification.provenance import collect, dependency_pins, differences, git_state

SIM = """\
program sim
use iso_fortran_env, only: real64
implicit none
integer :: n, i, u
real(real64), allocatable :: x(:)
character(len=256) :: nml
namelist /params/ n
nml = 'input/sim.nml'
if (command_argument_count() > 0) call get_command_argument(1, nml)
open(newunit=u, file=trim(nml), status='old'); read(u, nml=params); close(u)
allocate(x(n))
x = [(1.0_real64 / i, i = 1, n)]
print '(a,es23.16)', 'total = ', sum(x)
open(newunit=u, file='state.bin', form='unformatted', status='replace')
write(u) n
write(u) x
close(u)
open(newunit=u, file='state.raw', access='stream', form='unformatted', status='replace')
write(u) x
close(u)
if (n > 100) error stop 3
end program sim
"""


def _git(repo, *args) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def gitenv(tmp_path, monkeypatch):
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text("[user]\n\tname = T\n\temail = t@t\n[commit]\n\tgpgsign = false\n[color]\n\tui = always\n")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))


@pytest.fixture
def project(tmp_path, gitenv, monkeypatch):
    repo = tmp_path / "proj"
    (repo / "src").mkdir(parents=True)
    (repo / "input" / "mesh").mkdir(parents=True)
    (repo / "src" / "sim.f90").write_text(SIM)
    (repo / "src" / "sleepy.f90").write_text("program sleepy\ncall execute_command_line('sleep 30')\nend program\n")
    (repo / "src" / "broken.f90").write_text("program broken\nuse nothere\nend program broken\n")
    (repo / "input" / "sim.nml").write_text("&params\nn = 4\n/\n")
    (repo / "input" / "big.nml").write_text("&params\nn = 200\n/\n")
    (repo / "input" / "mesh" / "grid.dat").write_text("1 2 3\n")
    (repo / "fobos").write_text(
        "[modes]\nmodes = gnu\n\n[gnu]\ncompiler = gnu\nsrc = ./src/\nbuild_dir = ./build/\ncflags = -c -O0\n"
        "$NML = input/sim.nml\n\n"
        "[case:sim]\ntarget = src/sim.f90\ninputs = $NML input/mesh\nthreads = 2\n"
        "quantities =\n    stdout\n    x : binary state.bin real64 [4] record 2\n    raw : binary state.raw real64 stream\n"
        "    n : binary state.bin int32\n    status : exit\n\n"
        "[case:missing]\ntarget = src/sim.f90\ninputs = $NML\nquantities =\n    nope : regex stdout 'absent (\\d+)'\n\n"
        "[case:big]\ntarget = src/sim.f90\ninputs = input/big.nml\nargs = input/big.nml\n\n"
        "[case:slow]\ntarget = src/sleepy.f90\ntimeout = 1\n\n"
        "[case:broken]\ntarget = src/broken.f90\n\n"
        "[case:script]\ncommand = /bin/sh -c 'echo answer = 42; echo ranks = $MPI_RANKS'\nranks = 3\n"
        "quantities = stdout\n\n"
        "[verification]\nlauncher = env MPI_RANKS={ranks}\n"
    )
    (repo / ".gitignore").write_text("build/\n.fobis/\n")
    _git(repo, "init", "-q", "-b", "master")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "feat: sim")
    monkeypatch.chdir(repo)
    return repo


def _cases(repo):
    from fobis.Fobos import Fobos
    from fobis.verification import load_cases

    class Args:
        fobos = str(repo / "fobos")
        fobos_case_insensitive = False
        mode = None
        varset = ""
        lmodes = False

    return load_cases(Fobos(cliargs=Args()))


# ── numbers and probes ─────────────────────────────────────────────────────────


def test_fortran_numbers():
    assert to_float("1.5D+03") == 1500.0 and to_float("-2.5d-1") == -0.25
    assert math.isnan(to_float("NaN")) and to_float("-Infinity") == -math.inf
    assert numbers("glued: 1.0000000000000000E+00-2.5000000000000000E-01") == [1.0, -0.25]
    assert numbers("banana information 3") == [3.0]  # no nan/inf inside words


def test_parse_probes():
    probes = parse_probes("stdout\n  mass : regex stdout 'mass = (\\S+)' last\n# comment\nn : exit\n")
    assert [(p.name, p.kind) for p in probes] == [("*", "stdout"), ("mass", "regex"), ("n", "exit")]
    assert probes[1].args == ("stdout", "mass = (\\S+)", "last")
    with pytest.raises(ProbeError, match="kind must be one of"):
        parse_probes("x : guess stdout")
    with pytest.raises(ProbeError, match="expected 'name : kind arguments'"):
        parse_probes("just words")


def test_text_and_json_probes(tmp_path):
    (tmp_path / "norms.dat").write_text("# step l1 l2\n1 1.0D0 2.0\n2 0.5 1.0\n! note\n3 0.25 nan\n")
    (tmp_path / "run.json").write_text('{"solver": {"res": [1e-3, 2e-3], "it": 7, "m": [[1, 2], [3, 4]]}}')
    output = RunOutput(str(tmp_path), stdout="mass = 1.5\nmass = 2.5\nE: -3.0D+00\n")
    spec = """
        all : regex stdout "mass = (\\S+)"
        last : regex stdout "mass = (\\S+)" last
        l1 : column norms.dat 2
        l2_row2 : column norms.dat 3 2
        l2_last : column norms.dat 3 last
        res : json run.json $.solver.res
        it : json run.json solver.it
        m : json run.json $.solver.m
        res1 : json run.json $.solver.res[1]
        nokey : json run.json $.solver.x
        nofile : column absent.dat 1
        nomatch : regex stdout "volume = (\\S+)"
    """
    quantities, errors = extract(parse_probes("stdout\n" + spec), output)
    found = {q.name: (q.values, q.shape) for q in quantities}
    assert found["mass"] == ([1.5, 2.5], None) and found["E"] == ([-3.0], None)  # the stdout short form
    assert found["all"] == ([1.5, 2.5], None) and found["last"] == ([2.5], None)
    assert found["l1"] == ([1.0, 0.5, 0.25], None) and found["l2_row2"] == ([1.0], None)
    assert math.isnan(found["l2_last"][0][0])
    assert found["res"] == ([1e-3, 2e-3], [2]) and found["it"] == ([7.0], None) and found["res1"] == ([2e-3], None)
    assert found["m"] == ([1.0, 2.0, 3.0, 4.0], [2, 2])
    assert errors == {
        "nokey": "nokey: key 'x' not found",
        "nofile": "file absent.dat not found in the run directory",
        "nomatch": "nomatch: no value found",
    }


def test_binary_probes_on_a_file_written_by_gfortran(tmp_path):
    program = tmp_path / "w.f90"
    program.write_text(
        "program w\nuse iso_fortran_env\ninteger :: u\n"
        "open(newunit=u, file='seq.bin', form='unformatted')\nwrite(u) 7_int32\n"
        "write(u) [1.5_real64, -2.0_real64, 0.25_real64]\nwrite(u) [1.0_real32, 2.0_real32]\nclose(u)\n"
        "open(newunit=u, file='raw.bin', access='stream', form='unformatted')\nwrite(u) [3_int64, 4_int64]\nclose(u)\n"
        "end program w\n"
    )
    subprocess.run(["gfortran", "-o", "w", str(program)], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["./w"], cwd=tmp_path, check=True)
    spec = """
        n : binary seq.bin int32
        x : binary seq.bin real64 [3] record 2
        y : binary seq.bin real32 record 3
        z : binary raw.bin int64 [2] stream
        bad_shape : binary seq.bin real64 [2,2] record 2
        no_record : binary seq.bin real64 record 9
        not_whole : binary seq.bin real64 record 1
    """
    quantities, errors = extract(parse_probes(spec), RunOutput(str(tmp_path)))
    found = {q.name: (q.values, q.shape) for q in quantities}
    assert found == {"n": ([7.0], None), "x": ([1.5, -2.0, 0.25], [3]), "y": ([1.0, 2.0], None), "z": ([3.0, 4.0], [2])}
    assert errors["bad_shape"] == "bad_shape: shape [2, 2] holds 4 values, the data 3"
    assert errors["no_record"] == "no_record: record 9 not found (3 records)"
    assert errors["not_whole"] == "not_whole: 4 bytes is not a whole number of real64 values"


def test_hdf5_probe(tmp_path, monkeypatch):
    # SYNTHETIC text in the documented layout of `h5dump -d DATASET -y -w 0` (no HDF5 tool on the test machine)
    text = 'HDF5 "sol.h5" {\nDATASET "/fields/rho" {\n   DATATYPE  H5T_IEEE_F64LE\n'
    text += "   DATASPACE  SIMPLE { ( 2, 3 ) / ( 2, 3 ) }\n   DATA {\n   1, 2.5, 3,\n   4, 5, 6e-1\n   }\n}\n}\n"
    quantity = parse_h5dump("rho", text)
    assert (quantity.values, quantity.shape) == ([1.0, 2.5, 3.0, 4.0, 5.0, 0.6], [2, 3])
    (tmp_path / "sol.h5").write_bytes(b"\x89HDF")
    monkeypatch.setitem(__import__("sys").modules, "h5py", None)  # import h5py fails
    monkeypatch.setattr("shutil.which", lambda name: None)
    _, errors = extract(parse_probes("rho : hdf5 sol.h5 /fields/rho"), RunOutput(str(tmp_path)))
    assert errors == {"rho": "rho: reading HDF5 needs h5py or the h5dump tool"}


# ── cases ──────────────────────────────────────────────────────────────────────


def test_parse_case():
    case = parse_case(
        "c",
        {"command": "./run.sh --fast", "ranks": "4", "env": "A=1 B=two", "quantities": "stdout", "args": "-x 'a b'"},
    )
    assert (case.command, case.ranks, case.env) == (["./run.sh", "--fast"], 4, {"A": "1", "B": "two"})
    assert case.args == ["-x", "a b"]
    with pytest.raises(CaseError, match="exactly one of target"):
        parse_case("c", {"quantities": "stdout"})
    with pytest.raises(CaseError, match="exactly one of target"):
        parse_case("c", {"target": "a.f90", "command": "b"})
    with pytest.raises(CaseError, match="unknown option"):
        parse_case("c", {"target": "a.f90", "rank": "2"})
    with pytest.raises(CaseError, match="ranks must be a number"):
        parse_case("c", {"target": "a.f90", "ranks": "four"})
    with pytest.raises(CaseError, match="env entry 'X' is not KEY=VALUE"):
        parse_case("c", {"target": "a.f90", "env": "X"})
    with pytest.raises(CaseError, match="kind must be one of"):
        parse_case("c", {"target": "a.f90", "quantities": "x : nope"})


def test_load_cases_substitutes_variables(project):
    cases = _cases(project)
    assert sorted(cases) == ["big", "broken", "missing", "script", "sim", "slow"]
    assert cases["sim"].inputs == ["input/sim.nml", "input/mesh"] and cases["sim"].threads == 2


# ── the runner ─────────────────────────────────────────────────────────────────


def test_runner_on_real_programs(project):
    cases = _cases(project)
    runner = LocalRunner(".", launcher="env MPI_RANKS={ranks}")
    result = runner.run(cases["sim"])
    assert result.status == "ok", result.to_dict()
    found = {q.name: q.values for q in result.quantities}
    assert found["total"] == [2.083333333333333] and found["x"] == [1.0, 0.5, 1 / 3, 0.25]
    assert found["raw"] == found["x"] and found["n"] == [4.0] and found["status"] == [0.0]
    assert os.path.isfile(os.path.join(result.rundir, "input", "mesh", "grid.dat"))  # inputs, directories too
    with open(os.path.join(result.rundir, "stdout.txt")) as handle:
        assert handle.read().startswith("total = ")
    stale = os.path.join(result.rundir, "stale.txt")
    open(stale, "w").close()
    assert runner.run(cases["sim"]).ok and not os.path.exists(stale)  # a fresh run directory every run
    assert result.provenance["mode"] == "gnu" and result.provenance["compiler"]["command"] == "gfortran"
    assert runner.run(cases["missing"]).status == "probe-error"
    big = runner.run(cases["big"])
    assert big.status == "failed" and big.exit_code == 3
    slow = runner.run(cases["slow"])
    assert slow.status == "timeout" and "TIMEOUT after 1 s" in slow.stderr and slow.elapsed < 10
    broken = runner.run(cases["broken"])
    assert broken.status == "build-failed" and broken.build["diagnoses"][0]["kind"] == "missing-module"
    script = runner.run(cases["script"])
    assert script.command[:2] == ["env", "MPI_RANKS=3"] and script.quantity("ranks").values == [3.0]
    assert script.quantity("answer").values == [42.0]
    data = json.loads(json.dumps(result.to_dict()))
    assert data["quantities"]["x"] == {"values": [1.0, 0.5, 1 / 3, 0.25], "shape": [4]}


# ── provenance ─────────────────────────────────────────────────────────────────


def test_git_state_and_pins(project):
    clean = git_state(str(project))
    assert clean["dirty"] is False and len(clean["commit"]) == 40
    (project / "out.dat").write_text("1\n")  # an untracked output: still clean
    assert git_state(str(project))["dirty"] is False
    (project / "src" / "new.f90").write_text("module new\nend module new\n")
    dirty = git_state(str(project))
    assert dirty["dirty"] and dirty["untracked_sources"] == ["src/new.f90"] and len(dirty["diff_sha256"]) == 64
    (project / "src" / "new.f90").write_text("module new\n! changed\nend module new\n")
    assert git_state(str(project))["diff_sha256"] != dirty["diff_sha256"]
    lock = project / "fobos.lock"
    lock.write_text("[penf]\nurl = https://x/penf\ncommit = abc123\n")
    assert dependency_pins(str(lock)) == {"penf": "abc123"} and dependency_pins(str(project / "none")) == {}
    assert git_state(str(project.parent)) == {}  # not a repository


def test_collect_and_differences(project):
    data = collect(str(project), {"name": "gnu", "cflags": "-O2"}, "gnu")
    assert data["compiler"]["command"] == "gfortran" and data["compiler"]["version"].startswith("GNU Fortran")
    assert data["mode"] == "gnu" and data["machine"]["cores"] > 0
    other = json.loads(json.dumps(data))
    other["compiler"]["cflags"], other["date"], other["machine"]["host"] = "-O3", "later", "elsewhere"
    assert differences(data, other) == ["compiler.cflags: '-O2' -> '-O3'"]


# ── CLI ────────────────────────────────────────────────────────────────────────


def _run(args, capsys):
    try:
        run_fobis(fake_args=args)
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_cli(project, capsys):
    code, out, _ = _run(["case", "list", "--json"], capsys)
    assert code == 0 and [c["name"] for c in json.loads(out)["cases"]][:2] == ["sim", "missing"]
    code, out, _ = _run(["case", "run", "sim", "script", "--json"], capsys)
    data = json.loads(out)["results"]
    assert code == 0 and [r["status"] for r in data] == ["ok", "ok"]
    code, out, _ = _run(["case", "run", "sim", "big"], capsys)
    assert code == 1 and "total = 2.083333333333333" in out and "failed (exit 3" in out
    code, _, _ = _run(["case", "run", "nope"], capsys)
    assert code == 2
    code, out, _ = _run(["provenance", "--json"], capsys)
    assert code == 0 and json.loads(out)["mode"] == "gnu"
    (project / "fobos").write_text((project / "fobos").read_text() + "\n[case:bad]\ntarget = a.f90\nrank = 2\n")
    code, _, _ = _run(["case", "list"], capsys)
    assert code == 2


def test_cli_gitignore_note(project, capsys):
    (project / ".gitignore").write_text("build/\n")
    _, out, err = _run(["case", "run", "script"], capsys)
    assert "Note: add .fobis/runs/ to .gitignore" in out + err
