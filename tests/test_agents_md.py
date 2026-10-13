"""Tests for ``fobis agents-md`` (phase V7 of PLAN-verification.md): the facts of a project (modes through templates,
variables and build profiles; kinds as written with their modules; units without implicit none, include files
excluded; OpenMP/OpenACC/MPI; doctests; cases with references and budgets; lint; setup; dependencies; rules), only
the repository's files (ignored files and the dependencies directory left out), the block between its markers (the
user's text kept, appended to a file without one), ``--check`` and ``--print``, the CLI's exit statuses."""

from __future__ import annotations

import json
import subprocess

import pytest

from fobis.ai.agents_md import BEGIN, END, AgentsMdError, current_block, updated
from fobis.ai.crash import optimisation
from fobis.fobis import run_fobis

FOBOS = """\
[project]
name    = demo
summary = A demonstration project

[modes]
modes = gnu-release gnu-debug nvf-gpu lib

[common-variables]
$OPT = -O3

[template-gnu]
compiler = gnu
src      = ./src/

[gnu-release]
template = template-gnu
cflags   = -c $OPT -fopenmp
preproc  = -DUSE_MPI
mpi      = True
target   = src/app.F90
output   = app

[gnu-debug]
template = template-gnu
cflags   = -c -O0 -g -fcheck=all

[nvf-gpu]
compiler = nvfortran
cflags   = -c -fast -acc -gpu=cc80
src      = ./src/

[lib]
compiler = intel
cflags   = -c -debug all -O0
src      = ./src/
target   = src/m.f90
output   = libm.a
mklib    = static

[dependencies]
deps_dir = src/third
penf     = https://github.com/szaghi/PENF :: tag=v1.5.0

[lint]
ignore = STY

[verification]
setup = nvfortran: module load nvhpc/26

[case:sum]
target      = src/app.F90
mode        = gnu-release
ranks       = 2
quantities  = stdout
tolerance   = total: rel 1e-12
description = the sum

[assess:sum]
families = rounding
budget   = total: digits >= 10

[case:other]
command    = ./x
quantities =
    a : regex stdout "a=(\\S+)"

[rule-docs]
help = Build the docs
rule = echo docs
"""
SOURCES = {
    "src/kinds.f90": "module kinds\nimplicit none\ninteger, parameter :: RK = selected_real_kind(15, 307)\nend module kinds\n",
    "src/m.f90": (
        "module m\n"
        "!< The m module.\n"
        "!<```fortran\n"
        "!< print *, 1\n"
        "!<```\n"
        "!=> 1 <<<\n"
        "use kinds, only: RK\n"
        "use mpi\n"
        "implicit none\n"
        "real(RK) :: a(10)\n"
        "real(kind=RK) :: b\n"
        "integer :: n\n"
        "!$acc declare create(a)\n"
        "contains\n"
        "subroutine s()\n"
        "integer :: i, ierr\n"
        "!$omp parallel do\n"
        "do i = 1, 10\n"
        "  a(i) = 0\n"
        "end do\n"
        "call mpi_barrier(1, ierr)\n"
        "end subroutine s\n"
        "include 'body.inc'\n"
        "end module m\n"
    ),
    "src/body.inc": "subroutine inc_sub(x)\nreal(RK) :: x\nx = 1\nend subroutine inc_sub\n",
    "src/app.F90": "program app\nuse m\nimplicit none\ninteger :: ierr\ncall mpi_init(ierr)\nend program app\n",
    "src/legacy.f90": "subroutine old(x)\nreal*8 :: x\ndouble precision :: y\nx = y\nend subroutine old\n",
    "src/scratch.f90": "program scratch\nend program scratch\n",  # ignored by git
    "src/third/p.f90": "module p\nreal(8) :: z\nend module p\n",  # the dependencies directory
    "test/test_one.f90": "program test_one\nimplicit none\nend program test_one\n",
    "verification/references/sum.json": "{}\n",
}


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "demo"
    for path, text in {**SOURCES, "fobos": FOBOS, ".gitignore": "src/scratch.f90\n"}.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    monkeypatch.chdir(root)
    return root


def _run(args, capsys):
    try:
        run_fobis(fake_args=args)
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _facts(capsys, *args):
    code, out, _ = _run(["agents-md", "--print", "--json", *args], capsys)
    assert code == 0
    return json.loads(out)


def test_facts(project, capsys):
    data = _facts(capsys)
    facts, block = data["facts"], data["block"]
    modes = {m["name"]: m for m in facts["modes"]}
    release = modes["gnu-release"]
    assert release["compiler"] == "gnu" and release["optimisation"] == 3  # $OPT substituted, template applied
    assert release["parallel"] == ["OpenMP", "MPI"] and release["defines"] == ["-DUSE_MPI"]
    assert release["builds"] == "program `app` from `src/app.F90`"
    debug = modes["gnu-debug"]
    assert (debug["optimisation"], debug["debug"], debug["checks"]) == (0, True, True)
    assert modes["nvf-gpu"]["parallel"] == ["OpenACC"] and modes["nvf-gpu"]["optimisation"] == 3
    assert modes["lib"]["debug"] and modes["lib"]["builds"] == "static library `libm.a` from `src/m.f90`"
    assert facts["default_mode"] == "gnu-release" and facts["analysed_mode"] == "gnu-release"
    # only the repository's own files: neither the ignored scratch program nor the dependencies directory
    assert facts["files"] == {".F90": 1, ".f90": 3, ".inc": 1}
    assert facts["modules"] == ["kinds", "m"] and facts["programs"] == ["src/app.F90 (app)"]
    assert facts["no_implicit_none"] == ["src/legacy.f90: subroutine old"]  # body.inc is m's, not a unit
    kinds = {k["type"]: k for k in facts["kinds"]}
    assert kinds["real"]["counts"] == {"RK": 3, "*8": 1, "double precision": 1}  # as written in the sources
    assert kinds["real"]["origins"] == {"RK": "kinds"} and kinds["real"]["digits"] == {"RK": 15}
    assert kinds["integer"]["counts"] == {"default": 4}
    assert (facts["openmp_files"], facts["openacc_files"], facts["device_variables"]) == (1, 1, 1)
    assert facts["mpi"] == {"mpi": 1} and facts["mpi_calls"] == 2
    assert facts["doctest_modules"] == ["src/m.f90"]
    assert facts["tests"] == ["test/test_one.f90"]
    cases = {c["name"]: c for c in facts["cases"]}
    assert cases["sum"]["reference"] and not cases["other"]["reference"]
    assert cases["sum"]["budgets"] == ["total: digits >= 10"] and cases["sum"]["tolerance"] == {"total": "rel 1e-12"}
    assert facts["setup"] == {"nvfortran": "module load nvhpc/26"} and facts["lint"] == {"ignore": ["STY"]}
    assert facts["rules"] == {"docs": "Build the docs"} and facts["deps_dir"] == "src/third"
    # the rendered block
    assert block.startswith(BEGIN) and block.endswith(END + "\n")
    assert "| `gnu-debug` | gnu | every program in the sources | -O0, debug info, runtime checks | - | - |" in block
    assert "- `nvfortran`: `module load nvhpc/26`" in block
    assert (
        "| `sum` | `src/app.F90` (mode `gnu-release`, 2 ranks) | every `name = value` line | total: rel 1e-12 | yes |"
        in block
    )
    assert "| `other` | `./x` | a | exact | **missing** | - |" in block
    assert "`fobis assess sum`: rounding (budgets: total: digits >= 10)" in block
    assert "`RK` 3 (15 digits, from `kinds`)" in block and "- Doctests (in the comments of 1 file)" in block
    assert "MPI through `mpi` in 1 file (2 MPI calls" in block
    assert "The fobos `[lint]` section sets: ignore STY." in block
    assert _facts(capsys)["block"] == block  # deterministic
    assert _facts(capsys, "--mode", "nvf-gpu")["facts"]["analysed_mode"] == "nvf-gpu"


def test_optimisation_debug_flags():
    assert optimisation("intel", "-c -debug all") == (2, True, False)  # -debug: debug info, default level kept
    assert optimisation("intel", "-c -g") == (0, True, False)
    assert optimisation("ibm", "-qdbg=level=9 -qcheck=all")[1:] == (True, True)


def test_markers():
    block = f"{BEGIN}\nnew\n{END}\n"
    assert updated(None, block, "demo") == f"# demo\n\n{block}"
    assert updated("# Mine\n\nnotes\n", block, "demo") == f"# Mine\n\nnotes\n\n{block}"
    text = f"# Mine\n\nbefore\n\n{BEGIN}\nold\n{END}\n\nafter\n"
    assert updated(text, block, "demo") == f"# Mine\n\nbefore\n\n{block}\nafter\n"
    assert current_block(text) == f"{BEGIN}\nold\n{END}\n" and current_block("plain") is None
    for broken in (f"{END}\n{BEGIN}\n", f"{BEGIN}\n{BEGIN}\n{END}\n", f"{BEGIN}\nonly\n"):
        with pytest.raises(AgentsMdError):
            current_block(broken)


def test_cli(project, capsys):
    code, out, err = _run(["agents-md", "--check"], capsys)
    assert code == 1 and "AGENTS.md: missing: run fobis agents-md" in out + err
    code, out, _ = _run(["agents-md"], capsys)
    assert code == 0 and "AGENTS.md: created" in out
    text = (project / "AGENTS.md").read_text()
    assert text.startswith("# demo\n\n" + BEGIN)
    (project / "AGENTS.md").write_text("# Demo\n\nOur own rules.\n\n" + text.split("\n\n", 1)[1] + "\nMore rules.\n")
    assert _run(["agents-md", "--check"], capsys)[0] == 0
    assert "AGENTS.md: unchanged" in _run(["agents-md"], capsys)[1]
    (project / "src" / "new.f90").write_text("module extra\nimplicit none\nend module extra\n")
    code, out, err = _run(["agents-md", "--check"], capsys)
    assert code == 1 and "AGENTS.md: stale" in out + err and "+- Sources (mode `gnu-release`)" in out + err
    code, out, _ = _run(["agents-md", "--check", "--json"], capsys)
    assert code == 1 and json.loads(out)["files"][0]["status"] == "stale"
    assert "AGENTS.md: updated" in _run(["agents-md"], capsys)[1]
    text = (project / "AGENTS.md").read_text()
    assert text.startswith("# Demo\n\nOur own rules.\n\n") and text.endswith(END + "\n\nMore rules.\n")
    assert "3 modules" in text and "6 files" in text
    (project / "CLAUDE.md").write_text("# Claude\n")
    assert _run(["agents-md", "--output", "CLAUDE.md", "--check"], capsys)[0] == 1  # no block yet
    assert "CLAUDE.md: appended" in _run(["agents-md", "-o", "CLAUDE.md"], capsys)[1]
    assert (project / "CLAUDE.md").read_text().startswith("# Claude\n\n" + BEGIN)
    code, out, _ = _run(["agents-md", "--print"], capsys)
    assert code == 0 and out == current_block((project / "AGENTS.md").read_text())
    (project / "AGENTS.md").write_text(f"{BEGIN}\n")
    code, out, err = _run(["agents-md"], capsys)
    assert code == 2 and "unbalanced" in out + err
    (project / "fobos").write_text(FOBOS.replace("families = rounding", "families = magic"))
    assert _run(["agents-md", "--print"], capsys)[0] == 2
