"""``fobis introspect --compiler`` reports what the build runs: the command (an MPI wrapper, ``fc``) and the flags with
the switches (OpenMP, coarrays, ...) applied, the preprocessor flags in their own field. It used to echo the mode's
keys, so the runner, provenance and matrix recorded ``binary: ""`` and flags without ``-fopenmp``. No compiler is
run."""

from __future__ import annotations

import json

import pytest

from fobis.fobis import run_fobis

FOBOS = """[modes]
modes = plain omp mpi named

[plain]
compiler = gnu
cflags   = -c -O2
preproc  = -DX

[omp]
compiler = gnu
cflags   = -c
openmp   = True

[mpi]
compiler = nvfortran
cflags   = -c
mpi      = True

[named]
compiler = gnu
fc       = gfortran-13
cflags   = -c
"""


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "fobos").write_text(FOBOS)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _compiler(mode, capsys) -> dict:
    run_fobis(fake_args=["introspect", "--compiler", "--mode", mode])
    return json.loads(capsys.readouterr().out)["compiler"]


def test_the_flags_as_written(project, capsys):
    compiler = _compiler("plain", capsys)
    assert (compiler["name"], compiler["binary"], compiler["cflags"]) == ("gnu", "gfortran", "-c -O2")
    assert (compiler["lflags"], compiler["preproc"]) == ("", "-DX")  # the defines in their own field only


def test_the_switches_reach_the_flags(project, capsys):
    compiler = _compiler("omp", capsys)
    assert compiler["cflags"].split() == ["-c", "-fopenmp"] and compiler["lflags"].split() == ["-fopenmp"]


def test_the_command_is_the_one_run(project, capsys):
    assert _compiler("mpi", capsys)["binary"] == "mpif90"
    assert _compiler("named", capsys)["binary"] == "gfortran-13"
