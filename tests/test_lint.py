"""Tests for fobis.lint — rules (positive and negative cases), engine, reports, CLI."""

from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path

import pytest

from fobis.fobis import run_fobis
from fobis.lint import (
    RULES,
    LintResult,
    apply_baseline,
    discover_files,
    lint_files,
    lint_text,
    load_baseline,
    render,
    select_rules,
    write_baseline,
)


def _lines(rule_id: str, code: str, path: str = "t.f90", **kwargs) -> list[int]:
    """Lines where *rule_id* fires on *code*."""
    findings = lint_text(code, path, [RULES[rule_id]], **kwargs)  # no dedent: fixed form needs its columns
    return [f.line for f in findings if f.rule == rule_id]


# Each case: rule id, Fortran code, lines expected to be reported (empty: the rule must stay silent).
CASES = [
    # COR001 implicit-typing
    ("COR001", "module m\ncontains\nend module m\n", [1]),
    ("COR001", "program p\nimplicit none\nend program p\n", []),
    ("COR001", "subroutine s()\nend subroutine s\n", [1]),
    (
        "COR001",
        "module m\nimplicit none\ncontains\nsubroutine s()\nimplicit real(a-h)\nend subroutine\nend module\n",
        [5],
    ),
    ("COR001", "submodule (p) c\nend submodule c\n", []),
    # COR002 interface-implicit-typing
    (
        "COR002",
        "module m\nimplicit none\ninterface\nsubroutine cb(x)\nreal :: x\nend subroutine\nend interface\nend module\n",
        [4],
    ),
    (
        "COR002",
        "module m\nimplicit none\ninterface\nsubroutine cb(x)\nimplicit none\nreal :: x\nend subroutine\nend interface\nend module\n",
        [],
    ),
    # COR003 implicit-external-procedures (opt-in)
    ("COR003", "program p\nimplicit none\nend program\n", [1]),
    ("COR003", "program p\nimplicit none (type, external)\nend program\n", []),
    # COR010 missing-intent
    ("COR010", "subroutine s(a, b)\nreal :: a\nreal, intent(in) :: b\nend subroutine\n", [2]),
    ("COR010", "subroutine s(a)\nend subroutine\n", [1]),  # undeclared: reported at the header
    ("COR010", "subroutine s(f, g, v)\nexternal f\nprocedure(iface) :: g\ninteger, value :: v\nend subroutine\n", []),
    (
        "COR010",
        "subroutine s(cb)\ninterface\nsubroutine cb(x)\nreal, intent(in) :: x\nend subroutine\nend interface\nend subroutine\n",
        [],
    ),
    ("COR010", "subroutine s(a)\nreal :: a\nintent(inout) :: a\nend subroutine\n", []),
    # COR011 assumed-size
    ("COR011", "subroutine s(a, b)\nreal, intent(in) :: a(*), b(3, *)\nend subroutine\n", [2, 2]),
    ("COR011", "subroutine s(a, c)\nreal, intent(in) :: a(:)\ncharacter(len=*), intent(in) :: c\nend subroutine\n", []),
    ("COR011", "function f(s) bind(c)\ncharacter(kind=c_char), intent(in) :: s(*)\nend function\n", []),
    # COR020 initialisation-in-declaration
    ("COR020", "subroutine s()\ninteger :: n = 0\nend subroutine\n", [2]),
    ("COR020", "subroutine s()\ninteger, save :: n = 0\ninteger, parameter :: m = 1\nend subroutine\n", []),
    ("COR020", "subroutine s()\nsave\ninteger :: n = 0\nend subroutine\n", []),
    ("COR020", "module m\ninteger :: n = 0\nend module\n", []),  # module variables are saved anyway
    ("COR020", "program p\ninteger :: n = 0\nend program\n", []),
    ("COR020", "module m\ntype :: t\ninteger :: n = 0\nend type\nend module\n", []),  # default initialisation
    # COR021 pointer-initialisation-in-declaration
    ("COR021", "subroutine s()\nreal, pointer :: p(:) => null()\nend subroutine\n", [2]),
    ("COR021", "subroutine s()\nreal, pointer :: p(:)\nnullify(p)\nend subroutine\n", []),
    # COR030 external-procedure
    ("COR030", "subroutine s()\nexternal :: solve\nreal, external :: f\nend subroutine\n", [2, 3]),
    ("COR030", "subroutine s()\nend subroutine\n", []),
    # COR031 procedure-not-in-module
    ("COR031", "subroutine s()\nend subroutine\nfunction f()\nend function\n", [1, 3]),
    (
        "COR031",
        "module m\ncontains\nsubroutine s()\nend subroutine\nend module\n"
        "program p\ncontains\nsubroutine q()\nend subroutine\nend program\n",
        [],
    ),
    # COR040 use-all
    ("COR040", "module m\nuse penf\nuse, intrinsic :: iso_fortran_env\nend module\n", [2, 3]),
    ("COR040", "module m\nuse penf, only: R8P\nend module\n", []),
    # COR041 missing-intrinsic
    ("COR041", "module m\nuse iso_fortran_env, only: real64\nuse :: iso_c_binding\nend module\n", [2, 3]),
    ("COR041", "module m\nuse, intrinsic :: iso_fortran_env, only: real64\nuse penf, only: R8P\nend module\n", []),
    # COR050 missing-accessibility-statement
    ("COR050", "module m\nimplicit none\nend module\n", [1]),
    ("COR050", "module m\nimplicit none\nprivate\nend module\n", []),
    ("COR050", "module m\npublic\nend module\n", []),
    # COR060 unchecked-stat
    ("COR060", "subroutine s(n)\nallocate(a(n), stat=ierr)\na = 0\nend subroutine\n", [2]),
    ("COR060", "subroutine s(n)\nallocate(a(n), stat=ierr)\nif (ierr /= 0) stop\nend subroutine\n", []),
    ("COR060", "subroutine s(n)\nallocate(a(n))\nend subroutine\n", []),
    # COR061 multiple-allocations-with-stat
    ("COR061", "subroutine s(n)\nallocate(a(n), b(n), stat=ierr)\nif (ierr /= 0) stop\nend subroutine\n", [2]),
    ("COR061", "subroutine s(n)\nallocate(a(n), b(n))\nallocate(c(n), stat=ierr, errmsg=msg)\nend subroutine\n", []),
    ("COR061", "subroutine s(n)\nallocate(real :: a(n), stat=ierr)\nend subroutine\n", []),
    # OBS001 common-block
    ("OBS001", "subroutine s()\ncommon /blk/ a, b\ncommon x\nend subroutine\n", [2, 3]),
    ("OBS001", "subroutine s()\ncommon = 1\nprint *, 'common /x/'\nend subroutine\n", []),
    # OBS002 equivalence-statement
    ("OBS002", "subroutine s()\nequivalence (a, b)\nend subroutine\n", [2]),
    # OBS003 block-data
    ("OBS003", "block data init\ncommon /c/ x\nend block data init\n", [1]),
    ("OBS003", "module m\nend module\n", []),
    # OBS004 entry-statement
    ("OBS004", "subroutine s(x)\nentry t(x)\nend subroutine\n", [2]),
    ("OBS004", "subroutine s()\nentry = 1\nend subroutine\n", []),
    # OBS005 specific-intrinsic-name
    ("OBS005", "subroutine s()\ny = dsqrt(x) + float(n) + amax1(a, b)\nend subroutine\n", [2, 2, 2]),
    ("OBS005", "subroutine s()\ny = sqrt(x) + real(n)\nend subroutine\n", []),
    ("OBS005", "subroutine s()\nreal :: dabs(3)\ny = dabs(1)\nend subroutine\n", []),  # a local array named dabs
    # OBS006 computed-go-to
    ("OBS006", "subroutine s(i)\ngo to (10, 20) i\ngoto (10) i\n10 continue\n20 continue\nend subroutine\n", [2, 3]),
    ("OBS006", "subroutine s()\ngo to 10\n10 continue\nend subroutine\n", []),
    # OBS007 pause-statement
    ("OBS007", "program p\npause\npause 'wait'\nend program\n", [2, 3]),
    ("OBS007", "program p\npause = 1\nend program\n", []),
    # OBS008 deprecated-character-syntax
    ("OBS008", "subroutine s()\ncharacter*20 :: a\ncharacter * (*) b\nend subroutine\n", [2, 3]),
    ("OBS008", "subroutine s()\ncharacter(len=20) :: a\nend subroutine\n", []),
    # OBS009 forall
    (
        "OBS009",
        "subroutine s()\nforall (i = 1:n) a(i) = 0\nlbl: forall (i = 1:n)\na(i) = 1\nend forall lbl\nend subroutine\n",
        [2, 3],
    ),
    ("OBS009", "subroutine s()\ndo concurrent (i = 1:n)\nend do\nend subroutine\n", []),
    # OBS010 arithmetic-if
    ("OBS010", "subroutine s()\nif (x - 1.0) 10, 20, 30\n10 continue\n20 continue\n30 continue\nend subroutine\n", [2]),
    ("OBS010", "subroutine s()\nif (x > 0) y = 1\nif (f(x, 2)) then\nend if\nend subroutine\n", []),
    # OBS011 labelled-do-loop
    ("OBS011", "subroutine s()\ndo 10 i = 1, n\n10 continue\ndo 20, j = 1, n\n20 continue\nend subroutine\n", [2, 4]),
    ("OBS011", "subroutine s()\ndo i = 1, n\nend do\nend subroutine\n", []),
    # OBS012 shared-do-termination
    ("OBS012", "subroutine s()\ndo 10 i = 1, n\ndo 10 j = 1, n\n10 continue\nend subroutine\n", [3]),
    ("OBS012", "subroutine s()\ndo 10 i = 1, n\n10 continue\ndo 20 j = 1, n\n20 continue\nend subroutine\n", []),
    # OBS013 bad-do-termination
    ("OBS013", "subroutine s()\ndo 10 i = 1, n\n10 a(i) = 0\nend subroutine\n", [2]),
    ("OBS013", "subroutine s()\ndo 10 i = 1, n\n10 end do\nend subroutine\n", []),
    # OBS020 deprecated-mpi-include
    ("OBS020", "subroutine s()\ninclude 'mpif.h'\nend subroutine\n", [2]),
    ("OBS020", "subroutine s()\nuse mpi_f08\nend subroutine\n", []),
    # OBS021 deprecated-omp-include
    ("OBS021", 'subroutine s()\ninclude "omp_lib.h"\nend subroutine\n', [2]),
]


# ── wave A2: Fortran practice, OpenMP, OpenACC, MPI; wave G3: modernisation, portability ──
_DRIVER = "subroutine drv(n)\ninteger, intent(in) :: n\n!$omp parallel do\ndo i = 1, n\ncall work(i)\nend do\nend subroutine\n"
_PLOOP = "subroutine s(a, b, n)\ninteger, intent(in) :: n\nreal, intent(in) :: a(n)\nreal, intent(out) :: b(n)\nreal :: tmp, s\n"
CASES += [
    # FOR001 saved-local-in-parallel-procedure
    (
        "FOR001",
        "module m\ncontains\nsubroutine k(q)\n!$acc routine seq\nreal, intent(inout) :: q\nreal :: w = 1.0\nq = q * w\n"
        "end subroutine\nend module\n",
        [6],
    ),
    (
        "FOR001",
        _DRIVER + "subroutine work(i)\ninteger, intent(in) :: i\ninteger, save :: calls\ncalls = i\nend subroutine\n",
        [10],
    ),
    ("FOR001", "subroutine work(i)\ninteger, intent(in) :: i\ninteger, save :: calls\ncalls = i\nend subroutine\n", []),
    # FOR004 function-result-component
    (
        "FOR004",
        "module m\ncontains\nfunction g() result(r)\ntype(t) :: r\nend function\nsubroutine s()\nn = g()%ni\nend subroutine\nend module\n",
        [7],
    ),
    ("FOR004", "subroutine s()\ntype(t) :: a(3)\nn = a(1)%x\nend subroutine\n", []),
    # FOR005 cpu-time-for-wall-clock
    ("FOR005", "subroutine s()\n!$omp parallel\n!$omp end parallel\ncall cpu_time(t)\nend subroutine\n", [4]),
    ("FOR005", "subroutine s()\ncall cpu_time(t)\nend subroutine\n", []),
    # OMP001 shared-scalar-written-in-parallel-region
    (
        "OMP001",
        _PLOOP + "!$omp parallel do\ndo i = 1, n\ntmp = a(i) * 2\nb(i) = tmp\nend do\nend subroutine\n",
        [8],
    ),
    (
        "OMP001",
        _PLOOP + "!$omp parallel do private(tmp)\ndo i = 1, n\ntmp = a(i)\nb(i) = tmp\nend do\nend subroutine\n",
        [],
    ),
    ("OMP001", _PLOOP + "!$omp parallel do default(private)\ndo i = 1, n\ntmp = a(i)\nend do\nend subroutine\n", []),
    (  # a thread-number guard: one thread writes (a false positive before)
        "OMP001",
        _PLOOP + "!$omp parallel\nif (omp_get_thread_num() == 0) tmp = 1.0\nit = omp_get_thread_num()\n"
        "if (it .eq. 0) then\ns = 2.0\nend if\n!$omp end parallel\nend subroutine\n",
        [],
    ),
    (  # the else branch of the guard runs on every other thread
        "OMP001",
        _PLOOP + "!$omp parallel\nif (omp_get_thread_num() == 0) then\ntmp = 1.0\nelse\ns = 2.0\nend if\n"
        "!$omp end parallel\nend subroutine\n",
        [10],
    ),
    (
        "OMP001",
        _PLOOP
        + "!$omp parallel\n!$omp do\ndo i = 1, n\ndo j = 1, n\nb(i) = a(j)\nend do\nend do\n!$omp critical\ntmp = 1\n"
        "!$omp end critical\n!$omp end parallel\nend subroutine\n",
        [],
    ),
    # OMP002 accumulation-without-reduction
    ("OMP002", _PLOOP + "!$omp parallel do\ndo i = 1, n\ns = s + a(i)\nend do\nend subroutine\n", [8]),
    ("OMP002", _PLOOP + "!$omp parallel do reduction(+:s)\ndo i = 1, n\ns = s + a(i)\nend do\nend subroutine\n", []),
    # OMP003 collapse-imperfect-nest
    (
        "OMP003",
        "subroutine s()\n!$omp parallel do collapse(2)\ndo j = 1, m\nc = 1\ndo i = 1, n\nend do\nend do\nend subroutine\n",
        [2],
    ),
    (
        "OMP003",
        "subroutine s()\n!$omp parallel do collapse(2)\ndo j = 1, m\ndo i = 1, n\nend do\nx = 1\nend do\nend subroutine\n",
        [2],
    ),
    (
        "OMP003",
        "subroutine s()\n!$omp parallel do collapse(2)\ndo j = 1, m\ndo i = 1, n\nend do\nend do\nend subroutine\n",
        [],
    ),
    # ACC011 acc-collapse-imperfect-nest
    (
        "ACC011",
        "subroutine s()\n!$acc parallel loop collapse(2)\ndo j = 1, m\nc = 1\ndo i = 1, n\nend do\nend do\nend subroutine\n",
        [2],
    ),
    (
        "ACC011",
        "subroutine s()\n!$acc parallel loop collapse(2)\ndo j = 1, m\ndo i = 1, n\nend do\nend do\nend subroutine\n",
        [],
    ),
    # OMP007 mpi-in-threaded-region-without-thread-support
    (
        "OMP007",
        "program p\ncall mpi_init(ierr)\n!$omp parallel\ncall mpi_barrier(comm, ierr)\n!$omp end parallel\nend program\n",
        [4],
    ),
    (
        "OMP007",
        "program p\ncall mpi_init_thread(3, prov, ierr)\n!$omp parallel\ncall mpi_barrier(comm, ierr)\n!$omp end parallel\nend program\n",
        [],
    ),
    # ACC002 atomic-in-compute-region
    (
        "ACC002",
        "subroutine s(n)\n!$acc parallel loop\ndo i = 1, n\n!$acc atomic update\nx = x + 1\nend do\nend subroutine\n",
        [4],
    ),
    ("ACC002", "subroutine s()\n!$acc atomic update\nx = x + 1\nend subroutine\n", []),
    # ACC003 firstprivate-associate-name
    (
        "ACC003",
        "subroutine s(g)\nassociate (dx => g%dx)\n!$acc parallel loop firstprivate(dx)\ndo i = 1, n\nend do\nend associate\nend subroutine\n",
        [3],
    ),
    (
        "ACC003",
        "subroutine s(g)\nassociate (dx => g%dx)\n!$acc parallel loop copyin(dx)\ndo i = 1, n\nend do\nend associate\nend subroutine\n",
        [],
    ),
    # ACC004 reduction-into-device-module-variable
    (
        "ACC004",
        "module m\nreal, allocatable :: tot\n!$acc declare create(tot)\ncontains\nsubroutine s(n)\ninteger, intent(in) :: n\n"
        "!$acc parallel loop reduction(+:tot)\ndo i = 1, n\ntot = tot + 1\nend do\nend subroutine\nend module\n",
        [7],
    ),
    (
        "ACC004",
        "module m\nreal, allocatable :: tot\n!$acc declare create(tot)\ncontains\nsubroutine s(n)\nreal :: tot\n"
        "!$acc parallel loop reduction(+:tot)\ndo i = 1, n\ntot = tot + 1\nend do\nend subroutine\nend module\n",
        [],
    ),
    # ACC006 missing-acc-routine
    (
        "ACC006",
        "module m\ncontains\nsubroutine cell(x)\nreal, intent(inout) :: x\nend subroutine\nsubroutine s(a, n)\n"
        "!$acc parallel loop\ndo i = 1, n\ncall cell(a(i))\nend do\nend subroutine\nend module\n",
        [9],
    ),
    (
        "ACC006",
        "module m\ncontains\nsubroutine cell(x)\n!$acc routine seq\nreal, intent(inout) :: x\nend subroutine\nsubroutine s(a, n)\n"
        "!$acc parallel loop\ndo i = 1, n\ncall cell(a(i))\nend do\nend subroutine\nend module\n",
        [],
    ),
    # ACC008 timer-without-acc-wait
    (
        "ACC008",
        "subroutine s()\n!$acc parallel loop async(1)\ndo i = 1, n\nend do\ncall system_clock(t1)\nend subroutine\n",
        [5],
    ),
    (
        "ACC008",
        "subroutine s()\ncall system_clock(t0)\n!$acc parallel loop async(1)\ndo i = 1, n\nend do\n!$acc wait\ncall system_clock(t1)\nend subroutine\n",
        [],
    ),
    # MPI001 request-never-completed
    (
        "MPI001",
        "subroutine s(buf, n)\ninteger :: req, ierr\ncall mpi_isend(buf, n, mpi_real, 1, 0, comm, req, ierr)\nend subroutine\n",
        [3],
    ),
    (
        "MPI001",
        "subroutine s(buf, n)\ninteger :: req, ierr\ncall mpi_isend(buf, n, mpi_real, 1, 0, comm, req, ierr)\n"
        "call mpi_wait(req, mpi_status_ignore, ierr)\nend subroutine\n",
        [],
    ),
    (
        "MPI001",
        "subroutine s(buf, n, req)\ncall mpi_isend(buf, n, mpi_real, 1, 0, comm, req, ierr)\nend subroutine\n",
        [],
    ),
    # MDN001 double-precision (opt-in)
    ("MDN001", "subroutine s()\ndouble precision :: x\nend subroutine\n", [2]),
    ("MDN001", "subroutine s()\nreal(rk) :: x\nend subroutine\n", []),
    # MDN002 double-precision-literal (opt-in)
    ("MDN002", "subroutine s()\nx = 1.0d-3\nend subroutine\n", [2]),
    ("MDN002", "subroutine s()\nx = 1.0e-3_rk + d1\nend subroutine\n", []),
    # MDN011 old-style-array-constructor
    ("MDN011", "subroutine s()\na = (/ 1, 2 /)\nend subroutine\n", [2]),
    ("MDN011", "subroutine s()\na = [1, 2]\n100 format (/, a)\nend subroutine\n", []),
    # MDN021 deprecated-relational-operator
    ("MDN021", "subroutine s()\nif (a .eq. b .or. c .GE. d) x = 1\nend subroutine\n", [2]),
    ("MDN021", "subroutine s()\nl = a .eqv. b\nprint *, '.eq.'\nend subroutine\n", []),
    # MDN031 include-statement (opt-in)
    ("MDN031", "subroutine s()\ninclude 'consts.inc'\nend subroutine\n", [2]),
    ("MDN031", "subroutine s()\nuse consts, only: pi\nend subroutine\n", []),
    # MDN041 out-of-line-attribute
    (
        "MDN041",
        "subroutine s(a, b)\nreal :: a, b\ndimension a(10)\nintent(in) :: b\nparameter (n = 1)\nend subroutine\n",
        [3, 4, 5],
    ),
    ("MDN041", "module m\nreal, dimension(10) :: a\nprivate :: a\nsave\nend module\n", []),
    # MDN051 superfluous-save
    ("MDN051", "module m\nreal, save :: t\nsave\nend module\n", [2, 3]),
    ("MDN051", "subroutine s()\nreal, save :: t\nend subroutine\n", []),
    # MDN201 old-mpi-module (opt-in)
    ("MDN201", "subroutine s()\nuse mpi\nend subroutine\n", [2]),
    ("MDN201", "subroutine s()\nuse mpi_f08\nend subroutine\n", []),
    # PRT011 literal-kind
    ("PRT011", "subroutine s()\nreal(8) :: x\ninteger(kind=4) :: i\nend subroutine\n", [2, 3]),
    ("PRT011", "subroutine s()\nreal(rk) :: x\nend subroutine\n", []),
    # PRT012 literal-kind-suffix
    ("PRT012", "subroutine s()\nx = 1.0_8 + 2_4\nend subroutine\n", [2]),
    ("PRT012", "subroutine s()\nx = 1.0_rk + a_1\nend subroutine\n", []),
    # PRT021 star-kind
    ("PRT021", "subroutine s()\nreal*8 :: x\ninteger * 4 i\nend subroutine\n", [2, 3]),
    ("PRT021", "subroutine s()\ncharacter*8 :: c\nend subroutine\n", []),
    # PRT031 invalid-tab
    ("PRT031", "subroutine s()\n\tx = 1\nend subroutine\n", [2]),
    ("PRT031", "subroutine s()\nx = 1 ! a\tb\nend subroutine\n", []),
    # PRT061 non-portable-system-call (opt-in)
    ("PRT061", "subroutine s()\ncall system('ls')\nend subroutine\n", [2]),
    ("PRT061", "subroutine s()\ncall execute_command_line('ls')\nend subroutine\n", []),
    # PRT062 gfortran-random-extension (opt-in)
    ("PRT062", "subroutine s()\nx = rand()\nend subroutine\n", [2]),
    ("PRT062", "subroutine s()\ncall random_number(x)\nend subroutine\n", []),
]


# ── wave A3: G4 (correctness, style, obsolescent) and medium-confidence HPC rules ──
_KINDS = "module k\ninteger, parameter :: r8p = selected_real_kind(15, 307)\ninteger, parameter :: r4p = kind(1.0)\nend module\n"
_WS = "subroutine s(a, b, n)\ninteger, intent(in) :: n\nreal :: a(n), b(n)\n!$omp parallel\n!$omp do\ndo i = 1, n\na(i) = i\nend do\n"
_RANK = "subroutine init()\ncall mpi_comm_rank(comm, myrank, ierr)\nend subroutine\n"
CASES += [
    # COR022 missing-default-pointer-initialisation
    (
        "COR022",
        "module m\ntype :: node\ntype(node), pointer :: next, prev => null()\nreal :: x\ncontains\n"
        "procedure, pointer :: p\nend type\nend module\n",
        [3],
    ),
    (
        "COR022",
        "module m\ntype :: node\ntype(node), pointer :: next => null()\nend type\nreal, pointer :: q\nend module\n",
        [],
    ),
    # COR062 stat-without-errmsg (opt-in)
    ("COR062", "subroutine s(n)\nallocate(a(n), stat=ierr)\nif (ierr /= 0) stop\nend subroutine\n", [2]),
    ("COR062", "subroutine s(n)\nallocate(a(n), stat=ierr, errmsg=msg)\nallocate(b(n))\nend subroutine\n", []),
    # COR070 missing-default-case
    (
        "COR070",
        "subroutine s(k)\nselect case (k)\ncase (1)\nselect case (k)\ncase (2)\ncase default\nend select\nend select\n"
        "end subroutine\n",
        [2],
    ),
    ("COR070", "subroutine s(k)\nselect case (k)\ncase (1)\ncase default\nend select\nend subroutine\n", []),
    ("COR070", "subroutine s(q)\nselect type (q)\ntype is (real)\nend select\nend subroutine\n", []),
    # COR071 missing-class-default (opt-in)
    ("COR071", "subroutine s(q)\nselect type (q)\ntype is (real)\nend select\nend subroutine\n", [2]),
    ("COR071", "subroutine s(q)\nselect type (q)\ntype is (real)\nclass default\nend select\nend subroutine\n", []),
    # COR072 missing-rank-default (opt-in)
    ("COR072", "subroutine s(a)\nselect rank (a)\nrank (1)\nend select\nend subroutine\n", [2]),
    ("COR072", "subroutine s(a)\nselect rank (a)\nrank (1)\nrank default\nend select\nend subroutine\n", []),
    # COR080 magic-number-in-array-size (opt-in)
    ("COR080", "subroutine s()\nreal :: q(5, 0:100)\nend subroutine\n", [2]),
    ("COR080", "subroutine s(n)\nreal :: q(nvar, 0:n), w(1), x(:)\nend subroutine\n", []),
    # COR081 magic-io-unit (opt-in)
    (
        "COR081",
        "subroutine s()\nopen(10, file='a')\nwrite(unit=6, fmt=*) x\nif (ok) read(5, *) y\nend subroutine\n",
        [2, 3, 4],
    ),
    ("COR081", "subroutine s()\nopen(newunit=u, file='a')\nwrite(*, *) x\nwrite(u, *) y\nend subroutine\n", []),
    # COR082 missing-action-specifier (opt-in)
    ("COR082", "subroutine s()\nopen(newunit=u, file='a')\nend subroutine\n", [2]),
    ("COR082", "subroutine s()\nopen(newunit=u, file='a', action='read')\nend subroutine\n", []),
    # COR090 missing-exit-or-cycle-label
    ("COR090", "subroutine s()\nouter: do i = 1, n\nif (i > 2) exit\nend do outer\nend subroutine\n", [3]),
    (
        "COR090",
        "subroutine s()\nouter: do i = 1, n\ndo j = 1, n\nif (j > 2) exit\nend do\nif (i > 2) exit outer\nend do outer\n"
        "end subroutine\n",
        [],
    ),
    # COR091 exit-or-cycle-in-unlabelled-loop (opt-in)
    ("COR091", "subroutine s()\ndo i = 1, n\nif (i > 2) cycle\nend do\nend subroutine\n", [3]),
    ("COR091", "subroutine s()\nl: do i = 1, n\nif (i > 2) cycle l\nend do l\nend subroutine\n", []),
    # COR092 missing-end-label
    (
        "COR092",
        "subroutine s()\nouter: do i = 1, n\nend do\nchk: if (x > 0) then\nend if\nsel: select case (k)\nend select\n"
        "end subroutine\n",
        [3, 5, 7],
    ),
    (
        "COR092",
        "subroutine s()\nouter: do i = 1, n\nif (x > 0) then\nend if\nend do outer\nb: block\nend block b\n"
        "w: where (a > 0) a = 1\nend subroutine\n",
        [],
    ),
    # COR100 misleading-inline-if-semicolon
    ("COR100", "subroutine s()\nif (e /= 0) print *, 'x'; stop\nend subroutine\n", [2]),
    ("COR100", "subroutine s()\nx = 1; y = 2\nif (e /= 0) then; stop; end if\nend subroutine\n", []),
    # COR101 misleading-inline-if-continuation
    ("COR101", "subroutine s()\nif (verbose) &\n  call report(x)\nend subroutine\n", [2]),
    ("COR101", "subroutine s()\nif (verbose) call report(x, &\n  y)\nif (a .and. &\n  b) x = 1\nend subroutine\n", []),
    # COR110 nonportable-shortcircuit-inquiry
    (
        "COR110",
        "subroutine s(t, p)\nif (present(t) .and. t > 0) x = t\n"
        "do while (associated(p) .and. p%v > 0)\nend do\nend subroutine\n",
        [2, 3],
    ),
    (
        "COR110",
        "subroutine s(t, u)\nif (present(t) .and. present(u)) x = t\nif (present(t)) then\nend if\n"
        "if (allocated(a) .and. associated(p, q)) x = 1\nend subroutine\n",
        [],
    ),
    # COR120 unreachable-statement
    ("COR120", "subroutine s(x)\nx = x + 1\nreturn\nprint *, x\nend subroutine\n", [4]),
    (
        "COR120",
        "subroutine s(x)\nif (x > 0) return\nprint *, x\ndo i = 1, n\nif (i > 2) then\ncycle\nend if\nend do\n"
        "go to 10\n10 continue\nselect case (i)\ncase (1)\nstop\ncase default\nend select\nstop = 1\nx = 2\n"
        "end subroutine\n",
        [],
    ),
    # OBS014 goto-end-do
    ("OBS014", "subroutine s()\ndo i = 1, n\nif (b(i)) go to 10\na(i) = 0\n10 end do\nend subroutine\n", [3]),
    ("OBS014", "subroutine s()\ndo i = 1, n\nif (b(i)) go to 20\n10 end do\n20 continue\nend subroutine\n", []),
    # STY001 multiple-modules (opt-in)
    ("STY001", "module a\nend module\nmodule b\nend module\n", [3]),
    ("STY001", "module a\nend module\n", []),
    # STY002 program-with-module (opt-in)
    ("STY002", "module a\nend module\nprogram p\nend program\n", [3]),
    ("STY002", "program p\ncontains\nsubroutine s()\nend subroutine\nend program\n", []),
    # STY003 function-missing-result (opt-in)
    ("STY003", "module m\ncontains\nfunction f(x)\nend function\nend module\n", [3]),
    ("STY003", "module m\ncontains\nfunction f(x) result(r)\nend function\nend module\n", []),
    # STY010 inconsistent-array-declaration
    ("STY010", "subroutine s()\nreal, dimension(5) :: x, y(2)\nend subroutine\n", [2]),
    ("STY010", "subroutine s()\nreal, dimension(5) :: x, y\nreal :: z(2)\nend subroutine\n", []),
    # STY011 mixed-scalar-array-declaration (opt-in)
    ("STY011", "subroutine s()\nreal :: x, y(3)\nend subroutine\n", [2]),
    ("STY011", "subroutine s()\nreal :: x, y\nreal :: a(3), b(2)\nend subroutine\n", []),
    # STY020 too-complex (opt-in)
    ("STY020", "subroutine s()\n" + "if (x > 0) y = 1\n" * 10 + "end subroutine\n", [1]),
    ("STY020", "subroutine s()\n" + "if (x > 0) y = 1\n" * 9 + "end subroutine\n", []),
    # STY021 too-many-arguments (opt-in)
    ("STY021", "subroutine s(a, b, c, d, e, f, g, h, i)\nend subroutine\n", [1]),
    ("STY021", "subroutine s(a, b, c, d, e, f, g, h)\nend subroutine\n", []),
    # FOR002 loop-order-not-column-major (opt-in)
    (
        "FOR002",
        "subroutine s(a, b, n)\nreal :: a(n, n), b(n, n)\ndo i = 1, n\ndo j = 1, n\na(i, j) = b(i, j) + f(j, i)\n"
        "end do\nend do\nend subroutine\n",
        [4],
    ),
    (
        "FOR002",
        "subroutine s(a, b, n)\nreal :: a(n, n), b(n, n)\ndo j = 1, n\ndo i = 1, n\na(i, j) = b(i, j)\nend do\nend do\n"
        "do i = 1, n\ndo j = 1, n\na(i, j) = b(j, i)\nend do\nend do\nend subroutine\n",
        [],
    ),
    (
        "FOR002",
        "subroutine s(q, nb, nv)\nreal :: q(nb, nv)\n!$acc parallel loop\ndo b = 1, nb\ndo v = 1, nv\nq(b, v) = 0\n"
        "end do\nend do\nend subroutine\n",
        [],
    ),
    # FOR003 lower-bounds-lost-in-assumed-shape (opt-in)
    (
        "FOR003",
        "module m\ncontains\nsubroutine smooth(u, v)\nreal, intent(inout) :: u(:), v(0:)\nu(1) = v(0)\nend subroutine\n"
        "subroutine drv(ng, ni)\nreal :: q(1-ng:ni+ng), w(ni)\nreal, allocatable :: z(:)\nallocate(z(0:ni))\n"
        "call smooth(q, q)\ncall smooth(w, w)\ncall smooth(v=w, u=z)\nend subroutine\nend module\n",
        [11, 13],
    ),
    (
        "FOR003",
        "module m\ncontains\nsubroutine relay(u)\nreal, intent(inout) :: u(:)\ncall work(u)\nend subroutine\n"
        "subroutine drv(ng, ni)\nreal :: q(1-ng:ni+ng)\ncall relay(q)\nend subroutine\nend module\n",
        [],
    ),
    (
        "FOR003",
        "module m\ncontains\nsubroutine smooth(u)\nreal, intent(inout), allocatable :: u(:)\nend subroutine\n"
        "subroutine drv(ng, ni)\nreal, allocatable :: q(:)\nallocate(q(1-ng:ni))\ncall smooth(q)\ncall other(q)\n"
        "end subroutine\nend module\n",
        [],
    ),
    # FOR006 array-of-finalizable-type-not-finalised
    (
        "FOR006",
        "module m\ntype :: field\ncontains\nfinal :: free\nend type\ncontains\nsubroutine free(self)\n"
        "type(field), intent(inout) :: self\nend subroutine\nsubroutine use_it()\ntype(field), allocatable :: f(:)\n"
        "type(field) :: g\nend subroutine\nend module\n",
        [11],
    ),
    (
        "FOR006",
        "module m\ntype :: field\ncontains\nfinal :: free\nend type\ncontains\nimpure elemental subroutine free(self)\n"
        "type(field), intent(inout) :: self\nend subroutine\nsubroutine use_it()\ntype(field), allocatable :: f(:)\n"
        "end subroutine\nend module\n",
        [],
    ),
    # FOR007 default-real-literal-precision-loss
    (
        "FOR007",
        _KINDS + "subroutine s()\nuse k\nreal(r8p) :: dt, c = 0.1\ndouble precision :: e\ndt = 0.1 * cfl\ne = 1.0e-3\n"
        "end subroutine\n",
        [7, 9, 10],
    ),
    (
        "FOR007",
        _KINDS
        + "subroutine s()\nuse k\nreal(r8p) :: dt, h = 0.5\nreal(r4p) :: x\nreal :: y\ndt = 0.1_r8p + 2.0 + 1.0d-1\n"
        "x = 0.1\ny = 0.1\nz = 0.1\nend subroutine\n",
        [],
    ),
    # NUM001 uncompensated-global-sum (opt-in)
    (
        "NUM001",
        "subroutine s()\ncall mpi_allreduce(res_loc, residual, 1, mpi_double_precision, mpi_sum, comm, ierr)\nend subroutine\n",
        [2],
    ),
    (
        "NUM001",
        "subroutine s()\ncall mpi_allreduce(n_loc, n_tot, 1, mpi_integer, mpi_sum, comm, ierr)\n"
        "call mpi_allreduce(res_loc, residual, 1, mpi_double_precision, mpi_max, comm, ierr)\nend subroutine\n",
        [],
    ),
    # OMP004 nowait-dependent-read (opt-in)
    (
        "OMP004",
        _WS + "!$omp end do nowait\n!$omp do\ndo i = 1, n\nb(i) = a(n - i + 1)\nend do\n!$omp end do\n"
        "!$omp end parallel\nend subroutine\n",
        [12],
    ),
    (
        "OMP004",
        _WS + "!$omp end do nowait\n!$omp barrier\n!$omp do\ndo i = 1, n\nb(i) = a(i)\nend do\n!$omp end parallel\n"
        "end subroutine\n",
        [],
    ),
    (
        "OMP004",
        "subroutine s(a, b, n)\n!$omp parallel\n!$omp do schedule(static)\ndo i = 1, n\na(i) = i\nend do\n"
        "!$omp end do nowait\n!$omp do schedule(static)\ndo i = 1, n\nb(i) = a(i)\nend do\n!$omp end parallel\n"
        "end subroutine\n",
        [],
    ),
    # OMP005 serialisation-in-innermost-loop
    (
        "OMP005",
        "subroutine s()\n!$omp parallel do\ndo i = 1, n\n!$omp critical\nt = t + w(i)\n!$omp end critical\nend do\n"
        "end subroutine\n",
        [4],
    ),
    (
        "OMP005",
        "subroutine s()\n!$omp parallel\n!$omp critical\nt = t + 1\n!$omp end critical\n!$omp end parallel\n"
        "do i = 1, n\n!$omp atomic\nt = t + 1\nend do\nend subroutine\n",
        [],
    ),
    # OMP006 target-map-in-loop (opt-in)
    (
        "OMP006",
        "subroutine s(u, f, n)\ndo it = 1, 10\n!$omp target teams distribute parallel do map(tofrom: u) map(to: f)\n"
        "do i = 1, n\nu(i) = u(i) + f(i)\nend do\nend do\nend subroutine\n",
        [3],
    ),
    (
        "OMP006",
        "subroutine s(u, f, n)\n!$omp target data map(tofrom: u) map(to: f)\ndo it = 1, 10\n"
        "!$omp target teams distribute parallel do map(tofrom: u)\ndo i = 1, n\nu(i) = u(i) + f(i)\nend do\nend do\n"
        "!$omp end target data\n!$omp target map(tofrom: u)\n!$omp end target\nend subroutine\n",
        [],
    ),
    # ACC005 strided-section-argument-in-kernel
    (
        "ACC005",
        "subroutine s(d, v, nb)\nreal :: d(nb, 3), v(nb)\n!$acc parallel loop\ndo b = 1, nb\n"
        "call metrics(dxyz=d(b, 1:3), vol=v(b))\ncall other(d(1:nb:2, 1))\nend do\nend subroutine\n",
        [5, 6],
    ),
    (
        "ACC005",
        "subroutine s(d, v, nb)\nreal :: d(nb, 3), v(nb), w(3, 4)\n!$acc parallel loop private(w)\ndo b = 1, nb\n"
        "call metrics(d(:, 1), v(b))\ncall other(w(1, 1:3))\nend do\ncall metrics(d(b, 1:3), v)\nend subroutine\n",
        [],
    ),
    # ACC007 device-routine-assumed-shape-lower-bound
    (
        "ACC007",
        "subroutine st(q, r, i)\n!$acc routine seq\nreal, intent(in) :: q(1-ng:), r(:, 0:)\ninteger, value :: i\nend subroutine\n",
        [3, 3],
    ),
    (
        "ACC007",
        "subroutine st(q, lo, hi)\n!$acc routine seq\nreal, intent(in) :: q(lo:hi)\nend subroutine\n"
        "subroutine host(q)\nreal, intent(in) :: q(0:)\nend subroutine\n",
        [],
    ),
    # ACC009 mpi-on-device-data-without-update (opt-in)
    (
        "ACC009",
        "subroutine s(halo, hin, n)\n!$acc data copy(halo, hin)\n"
        "call mpi_sendrecv(halo, n, mpi_real8, 1, 0, hin, n, mpi_real8, 0, 0, comm, st, ierr)\n!$acc end data\n"
        "end subroutine\n",
        [3, 3],
    ),
    (
        "ACC009",
        "subroutine s(halo, hin, n)\n!$acc data copy(halo, hin)\n!$acc update self(halo)\n"
        "call mpi_sendrecv(halo, n, mpi_real8, 1, 0, hin, n, mpi_real8, 0, 0, comm, st, ierr)\n!$acc update device(hin)\n"
        "!$acc host_data use_device(halo)\ncall mpi_send(halo, n, mpi_real8, 1, 0, comm, ierr)\n!$acc end host_data\n"
        "!$acc end data\ncall mpi_send(other, n, mpi_real8, 1, 0, comm, ierr)\nend subroutine\n",
        [],
    ),
    # ACC010 private-array-in-contained-kernel (opt-in)
    (
        "ACC010",
        "subroutine outer()\ncall fill()\ncontains\nsubroutine fill()\nreal :: buf(5), t\n"
        "!$acc parallel loop private(buf, t)\ndo i = 1, n\nend do\nend subroutine\nend subroutine\n",
        [6],
    ),
    (
        "ACC010",
        "module m\ncontains\nsubroutine fill()\nreal :: buf(5)\n!$acc parallel loop private(buf)\ndo i = 1, n\nend do\n"
        "end subroutine\nend module\n",
        [],
    ),
    # MPI002 isend-buffer-modified-before-completion
    (
        "MPI002",
        "subroutine s(n)\ncall mpi_isend(halo, n, mpi_real8, 1, 0, comm, req, ierr)\nhalo = 0\n"
        "call mpi_wait(req, mpi_status_ignore, ierr)\nend subroutine\n",
        [3],
    ),
    (
        "MPI002",
        "subroutine s(n)\ncall mpi_isend(halo, n, mpi_real8, 1, 0, comm, req(1), ierr)\nx = halo(1)\n"
        "call mpi_waitall(1, req, mpi_statuses_ignore, ierr)\nhalo = 0\nend subroutine\n",
        [],
    ),
    # MPI003 irecv-buffer-used-before-completion
    (
        "MPI003",
        "subroutine s(n)\ncall mpi_irecv(halo, n, mpi_real8, 1, 0, comm, req, ierr)\nq(0) = halo(1)\n"
        "call mpi_wait(req, mpi_status_ignore, ierr)\nend subroutine\n",
        [3],
    ),
    (
        "MPI003",
        "subroutine s(n)\ncall mpi_irecv(halo, n, mpi_real8, 1, 0, comm, req, ierr)\n"
        "call mpi_isend(sb, n, mpi_real8, 1, 0, comm, req2, ierr)\ncall mpi_wait(req, mpi_status_ignore, ierr)\n"
        "q(0) = halo(1)\nend subroutine\n",
        [],
    ),
    (
        "MPI003",
        "subroutine s(n)\ncall mpi_irecv(rbuf(k), n, mpi_real8, 1, 0, comm, req, ierr)\nrbuf(1:n) = sbuf(1:n)\n"
        "call mpi_wait(req, mpi_status_ignore, ierr)\nend subroutine\n",
        [],
    ),
    # MPI004 collective-in-rank-branch
    (
        "MPI004",
        _RANK
        + "subroutine s()\nif (myrank == 0) then\nread(u, *) dt\ncall mpi_bcast(dt, 1, mpi_real8, 0, comm, ierr)\n"
        "else\ncall mpi_barrier(comm, ierr)\nend if\nif (myrank > 0) call mpi_barrier(comm, ierr)\nend subroutine\n",
        [7, 9, 11],
    ),
    (
        "MPI004",
        _RANK + "subroutine s()\nif (myrank == 0) then\nread(u, *) dt\nend if\nif (nproc > 1) then\n"
        "call mpi_bcast(dt, 1, mpi_real8, 0, comm, ierr)\nend if\nend subroutine\n",
        [],
    ),
    (  # every branch calls the same collectives: every rank reaches them (a false positive before)
        "MPI004",
        _RANK
        + "subroutine s()\nif (myrank == 0) then\nread(u, *) dt\ncall mpi_bcast(dt, 1, mpi_real8, 0, comm, ierr)\n"
        "else\ncall mpi_bcast(dt, 1, mpi_real8, 0, comm, ierr)\nend if\nselect case (myrank)\ncase (0)\n"
        "call mpi_barrier(comm, ierr)\ncase default\ncall mpi_barrier(comm, ierr)\nend select\nend subroutine\n",
        [],
    ),
    (  # no else: the ranks matching neither condition never call it
        "MPI004",
        _RANK + "subroutine s()\nif (myrank == 0) then\ncall mpi_barrier(comm, ierr)\nelse if (myrank == 1) then\n"
        "call mpi_barrier(comm, ierr)\nend if\nend subroutine\n",
        [6, 8],
    ),
    # MPI005 blocking-send-before-receive (opt-in)
    (
        "MPI005",
        "subroutine s()\ncall mpi_send(sb, n, mpi_real8, right, 0, comm, ierr)\n"
        "call mpi_recv(rb, n, mpi_real8, left, 0, comm, st, ierr)\nend subroutine\n",
        [2],
    ),
    (
        "MPI005",
        _RANK + "subroutine s()\nif (mod(myrank, 2) == 0) then\ncall mpi_send(sb, n, mpi_real8, 1, 0, comm, ierr)\n"
        "call mpi_recv(rb, n, mpi_real8, 1, 0, comm, st, ierr)\nelse\n"
        "call mpi_recv(rb, n, mpi_real8, 0, 0, comm, st, ierr)\ncall mpi_send(sb, n, mpi_real8, 0, 0, comm, ierr)\n"
        "end if\nend subroutine\n",
        [],
    ),
    # MPI006 any-source-order-dependent-sum (opt-in)
    (
        "MPI006",
        "subroutine s()\nreal(8) :: total, part\ndo k = 1, np\n"
        "call mpi_recv(part, 1, mpi_real8, mpi_any_source, 0, comm, st, ierr)\ntotal = total + part\nend do\nend subroutine\n",
        [4],
    ),
    (
        "MPI006",
        "subroutine s()\nreal(8) :: total, part\ninteger :: cnt\ndo k = 1, np\n"
        "call mpi_recv(part, 1, mpi_real8, k, 0, comm, st, ierr)\ntotal = total + part\n"
        "call mpi_recv(ip, 1, mpi_integer, mpi_any_source, 0, comm, st, ierr)\ncnt = cnt + ip\nend do\nend subroutine\n",
        [],
    ),
]


@pytest.mark.parametrize(("rule_id", "code", "expected"), CASES, ids=[f"{c[0]}-{i}" for i, c in enumerate(CASES)])
def test_rule_cases(rule_id, code, expected):
    assert _lines(rule_id, code) == expected


def test_every_rule_has_a_positive_case():
    covered = {rule_id for rule_id, _, expected in CASES if expected}
    engine_rules = {"LNT001", "LNT002", "LNT003", "LNT004"}  # tested below
    feedback_rules = {"ACC001", "ACC012", "OMP008", "PRF001"}  # tested in test_feedback.py on real logs
    assert set(RULES) - engine_rules - feedback_rules <= covered


def test_rules_are_documented_consistently():
    for rid, rul in RULES.items():
        assert re.fullmatch(r"[A-Z]{3}\d{3}", rid)
        assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", rul.name)
        assert rul.summary and rul.rationale.strip()
        assert rid in rul.explain()
    names = [r.name for r in RULES.values()]
    assert len(names) == len(set(names))
    equivalents = [r.equivalent for r in RULES.values() if r.equivalent]
    assert len(equivalents) == len(set(equivalents))


def test_fixed_form_obsolescent_code():
    code = "      SUBROUTINE S\n      COMMON /C/ X\n      DO 10 I = 1, 3\n   10 X = X + 1\n      END\n"
    assert _lines("OBS001", code, "t.f") == [2]
    assert _lines("OBS013", code, "t.f") == [3]


def test_preprocessor_defines_select_linted_code():
    code = "subroutine s()\n#ifdef MPI\ninclude 'mpif.h'\n#else\ncommon /c/ x\n#endif\nend subroutine\n"
    assert _lines("OBS020", code, "t.F90", defines={"MPI": "1"}) == [3]
    assert _lines("OBS001", code, "t.F90", defines={"MPI": "1"}) == []
    assert _lines("OBS001", code, "t.F90") == [5]


# ── engine: selection ──────────────────────────────────────────────────────────


def test_select_rules_default_prefix_all_and_ignore():
    default = {r.id for r in select_rules()}
    assert "COR003" not in default and "COR001" in default
    assert {r.id for r in select_rules(["COR00"])} == {"COR001", "COR002", "COR003"}
    assert {r.id for r in select_rules(["ALL"])} == set(RULES)
    assert "COR040" not in {r.id for r in select_rules([], ["COR04"])}
    with pytest.raises(ValueError, match="XYZ"):
        select_rules(["XYZ"])


# ── engine: suppressions ───────────────────────────────────────────────────────

_SUPPRESS_RULES = [RULES[r] for r in ("COR020", "LNT001", "LNT002", "LNT003")]


def _found(code: str) -> list[tuple[int, str]]:
    return [(f.line, f.rule) for f in lint_text(textwrap.dedent(code), "t.f90", _SUPPRESS_RULES)]


def test_inline_suppression_with_reason():
    code = "subroutine s()\ninteger :: n = 0 ! fobis: ignore[COR020] counter kept on purpose\nend subroutine\n"
    assert _found(code) == []


def test_own_line_suppression_applies_to_next_statement():
    code = "subroutine s()\n! fobis: ignore[COR020] intended\ninteger :: n = 0\ninteger :: m = 0\nend subroutine\n"
    assert _found(code) == [(4, "COR020")]


def test_suppression_covers_a_continued_statement():
    code = "subroutine s()\ninteger :: n = &\n  0 ! fobis: ignore[COR020] intended\nend subroutine\n"
    assert _found(code) == []


def test_suppression_without_reason_unused_and_unknown():
    code = (
        "subroutine s()\n"
        "integer :: n = 0 ! fobis: ignore[COR020]\n"
        "integer :: m ! fobis: ignore[COR020] stale\n"
        "integer :: k ! fobis: ignore[COR999] typo\n"
        "end subroutine\n"
    )
    assert _found(code) == [(2, "LNT001"), (3, "LNT002"), (4, "LNT003")]


def test_unused_suppression_of_a_rule_not_run_is_not_reported():
    code = "subroutine s()\ninteger :: m ! fobis: ignore[OBS001] not selected\nend subroutine\n"
    assert _found(code) == []


def test_preprocessor_assumption_reported_as_info():
    findings = lint_text("#if FOO(1)\n#endif\n", "t.F90", [RULES["LNT004"]])
    assert [(f.rule, f.severity) for f in findings] == [("LNT004", "info")]


# ── engine: files and baseline ─────────────────────────────────────────────────


def _project(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.f90").write_text("subroutine a()\ninteger :: n = 0\nend subroutine\n")
    (tmp_path / "src" / "b.F").write_text("      SUBROUTINE B\n      COMMON /C/ X\n      END\n")
    (tmp_path / "src" / "notes.txt").write_text("not fortran\n")
    (tmp_path / ".fobis_deps" / "dep").mkdir(parents=True)
    (tmp_path / ".fobis_deps" / "dep" / "d.f90").write_text("subroutine d()\nend\n")
    return tmp_path


def test_discover_files_skips_fetched_dependencies(tmp_path):
    root = _project(tmp_path)
    files = discover_files([str(root)], extensions=[".f90", ".F"])
    assert [f.split("/")[-1] for f in files] == ["a.f90", "b.F"]
    assert discover_files([str(root)], extensions=[".f90", ".F"], exclude=["b.F"])[-1].endswith("a.f90")


def test_baseline_round_trip_hides_recorded_findings(tmp_path):
    root = _project(tmp_path)
    files = discover_files([str(root / "src")], extensions=[".f90", ".F"])
    rules = [RULES["COR020"], RULES["OBS001"]]
    result = lint_files(files, rules)
    assert len(result.findings) == 2
    baseline = tmp_path / "baseline.json"
    assert write_baseline(str(baseline), result.findings) == 2
    # a line shift does not invalidate the baseline: fingerprints ignore line numbers
    (root / "src" / "a.f90").write_text("subroutine a()\n! moved\ninteger :: n = 0\ninteger :: k = 1\nend subroutine\n")
    again = lint_files(files, rules)
    apply_baseline(again, load_baseline(str(baseline)))
    assert again.baselined == 2
    assert [(f.rule, f.line) for f in again.findings] == [("COR020", 4)]


def test_load_baseline_missing_and_invalid(tmp_path):
    assert not load_baseline(str(tmp_path / "none.json"))
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(ValueError, match="invalid lint baseline"):
        load_baseline(str(bad))


# ── reports ────────────────────────────────────────────────────────────────────


def _result() -> LintResult:
    code = "subroutine s()\ninteger :: n = 0\ncommon /c/ x\nend subroutine\n"
    findings = lint_text(code, "src/s.f90", select_rules(["COR020", "OBS001"]))
    return LintResult(findings=findings, files=1)


def test_render_text():
    text = render(_result(), "text")
    assert "src/s.f90:2: COR020 [warning]" in text
    assert "2 finding(s) in 1 file(s): COR020 x1, OBS001 x1" in text


def test_render_json():
    data = json.loads(render(_result(), "json"))
    assert [f["rule"] for f in data["findings"]] == ["COR020", "OBS001"]
    assert data["findings"][0]["name"] == "initialisation-in-declaration"


def test_render_sarif():
    log = json.loads(render(_result(), "sarif"))
    run = log["runs"][0]
    assert log["version"] == "2.1.0"
    assert [r["id"] for r in run["tool"]["driver"]["rules"]] == ["COR020", "OBS001"]
    first = run["results"][0]
    assert first["ruleId"] == "COR020" and first["level"] == "warning"
    assert first["locations"][0]["physicalLocation"]["region"]["startLine"] == 2
    assert first["partialFingerprints"]["fobisLint/v1"]
    for rule in run["tool"]["driver"]["rules"]:  # the help link is the rule's generated page
        page = rule["helpUri"].split("/FoBiS/", 1)[1]
        assert (Path(__file__).resolve().parent.parent / "docs" / f"{page}.md").is_file(), rule["helpUri"]


def test_render_github():
    lines = render(_result(), "github").splitlines()
    assert lines[0].startswith("::warning file=src/s.f90,line=2,endLine=2,title=COR020 initialisation-in-declaration::")


# ── CLI ────────────────────────────────────────────────────────────────────────


def _cli_project(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "m.F90").write_text(
        "module m\nimplicit none\nprivate\ncontains\nsubroutine s(n)\ninteger :: n\n"
        "#ifdef USE_MPI\ninclude 'mpif.h'\n#else\ncommon /c/ x\n#endif\nend subroutine s\nend module m\n"
    )
    (tmp_path / "fobos").write_text(
        "[modes]\nmodes = gnu\n\n[gnu]\ncompiler = gnu\ncflags = -c -DUSE_MPI\nsrc = ./src/\n\n[lint]\nignore = COR040\n"
    )
    monkeypatch.chdir(tmp_path)


def _run(args, capsys) -> tuple[int, str]:
    try:
        run_fobis(fake_args=["lint", *args])
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    return code, capsys.readouterr().out


def test_cli_lint_uses_mode_defines_and_lint_section(tmp_path, monkeypatch, capsys):
    _cli_project(tmp_path, monkeypatch)
    code, out = _run([], capsys)
    assert code == 1
    assert "src/m.F90:6: COR010" in out and "src/m.F90:8: OBS020" in out
    assert "OBS001" not in out  # the #else branch is not compiled in mode gnu


def test_cli_baseline_update_then_clean_run(tmp_path, monkeypatch, capsys):
    _cli_project(tmp_path, monkeypatch)
    code, _ = _run(["--update-baseline"], capsys)
    assert code == 0 and (tmp_path / ".fobis-lint-baseline.json").exists()
    code, out = _run([], capsys)
    assert code == 0
    assert "2 hidden by the baseline" in out


def test_cli_exit_zero_select_and_format(tmp_path, monkeypatch, capsys):
    _cli_project(tmp_path, monkeypatch)
    code, out = _run(["--select", "OBS", "--format", "json", "--exit-zero"], capsys)
    assert code == 0
    assert [f["rule"] for f in json.loads(out)["findings"]] == ["OBS020"]


def test_cli_list_and_explain(tmp_path, monkeypatch, capsys):
    _cli_project(tmp_path, monkeypatch)
    code, out = _run(["--list-rules"], capsys)
    assert code == 0 and "COR020  initialisation-in-declaration" in out
    code, out = _run(["--explain", "cor020"], capsys)
    assert code == 0 and "save attribute" in out.lower()
    code, _ = _run(["--explain", "NOPE01"], capsys)
    assert code == 1


def test_cli_rejects_unknown_selector_and_format(tmp_path, monkeypatch, capsys):
    _cli_project(tmp_path, monkeypatch)
    assert _run(["--select", "XYZ"], capsys)[0] == 1
    assert _run(["--format", "xml"], capsys)[0] == 1


# ── fixes ──────────────────────────────────────────────────────────────────────


def test_apply_fixes_rewrites_only_code():
    from fobis.lint import apply_fixes

    code = "subroutine s()\nif (a .eq. b) x = (/ 1, 2 /) ! keep .eq. in comment\nprint *, '.ne.'\nend subroutine\n"
    findings = lint_text(code, "t.f90", [RULES["MDN021"], RULES["MDN011"]])
    fixed, applied = apply_fixes(code, findings)
    assert applied == 3
    assert fixed.splitlines()[1] == "if (a == b) x = [ 1, 2 ] ! keep .eq. in comment"
    assert fixed.splitlines()[2] == "print *, '.ne.'"
    assert not lint_text(fixed, "t.f90", [RULES["MDN021"], RULES["MDN011"]])


def test_apply_fixes_on_continued_statement():
    from fobis.lint import apply_fixes

    code = "subroutine s()\nif (a .lt. b .and. &\n    c .ge. d) x = 1\nend subroutine\n"
    fixed, applied = apply_fixes(code, lint_text(code, "t.f90", [RULES["MDN021"]]))
    assert applied == 2
    assert "a < b" in fixed and "c >= d" in fixed


def test_a_finding_whose_edit_was_skipped_is_not_fixed(tmp_path, monkeypatch):
    """--fix skips an edit overlapping an earlier one, but used to count its finding as fixed (and drop it)."""
    from fobis.fobis import _lint_fixes
    from fobis.lint.rule import Edit, Finding

    (tmp_path / "s.f90").write_text("x = a .eq. b\n")
    monkeypatch.chdir(tmp_path)
    first = Finding("MDN021", "s.f90", 1, "old operator", "info", fixes=(Edit(1, 6, 10, "=="),))
    overlap = Finding("XXX000", "s.f90", 1, "same span", "info", fixes=(Edit(1, 5, 9, "!="),))
    left = _lint_fixes([first, overlap], True, lambda message: None)
    assert (tmp_path / "s.f90").read_text() == "x = a == b\n"
    assert left == [overlap]


def test_cli_diff_and_fix(tmp_path, monkeypatch, capsys):
    (tmp_path / "s.f90").write_text("subroutine s()\nif (a .eq. b) x = 1\nend subroutine\n")
    monkeypatch.chdir(tmp_path)
    code, out = _run(["s.f90", "--select", "MDN021", "--diff"], capsys)
    assert code == 0
    assert "-if (a .eq. b) x = 1" in out and "+if (a == b) x = 1" in out
    assert ".eq." in (tmp_path / "s.f90").read_text()  # --diff changes nothing
    code, out = _run(["s.f90", "--select", "MDN021", "--fix"], capsys)
    assert code == 0
    assert "if (a == b) x = 1" in (tmp_path / "s.f90").read_text()


# ── cross-file rules ───────────────────────────────────────────────────────────


def test_cross_file_device_routine_and_saved_local(tmp_path):
    (tmp_path / "kernels.f90").write_text(
        "module kernels\ncontains\nsubroutine cell(x)\nreal, intent(inout) :: x\nreal :: w = 2.0\nx = x * w\n"
        "end subroutine\nend module\n"
    )
    (tmp_path / "driver.f90").write_text(
        "module driver\nuse kernels, only: cell\ncontains\nsubroutine run(a, n)\ninteger, intent(in) :: n\n"
        "real, intent(inout) :: a(n)\n!$acc parallel loop\ndo i = 1, n\ncall cell(a(i))\nend do\nend subroutine\nend module\n"
    )
    files = discover_files([str(tmp_path)], extensions=[".f90"])
    result = lint_files(files, [RULES["ACC006"], RULES["FOR001"]])
    found = sorted((f.rule, f.path.split("/")[-1], f.line) for f in result.findings)
    assert found == [("ACC006", "driver.f90", 9), ("FOR001", "kernels.f90", 5)]


def test_omp_temporary_updated_in_iteration_is_not_an_accumulation():
    code = (
        "subroutine s(a, n)\ninteger, intent(in) :: n\nreal, intent(in) :: a(n)\nreal :: t\n"
        "!$omp parallel do\ndo i = 1, n\nt = a(i)\nt = t * 2\nt = t + 1\nend do\nend subroutine\n"
    )
    found = [(f.rule, f.line) for f in lint_text(code, "t.f90", [RULES["OMP001"], RULES["OMP002"]])]
    assert found == [("OMP001", 7)]  # reported once, at the first write, as a shared temporary


def test_c_headers_are_skipped(tmp_path):
    (tmp_path / "zlib.h").write_text("/* C */\ntypedef int z_int;\nextern int deflate(void);\n")
    (tmp_path / "consts.h").write_text("integer, parameter :: n = 1\ncommon /c/ x\n")
    files = discover_files([str(tmp_path)], extensions=[".h"])
    result = lint_files(files, [RULES["OBS001"]])
    assert [f.path.split("/")[-1] for f in result.findings] == ["consts.h"]
    assert [p.split("/")[-1] for p in result.skipped] == ["zlib.h"]
    assert "1 C header(s) skipped" in render(result, "text")


def test_tabs_reported_once_per_file():
    findings = lint_text("subroutine s()\n\tx = 1\n\ty = 2\nend subroutine\n", "t.f90", [RULES["PRT031"]])
    assert [(f.line, f.message) for f in findings] == [(2, "tab character in code (and 1 more line(s))")]
