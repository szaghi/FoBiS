"""Tests for ``fobis bindings`` (phase V12 of PLAN-verification.md): C types from kinds (default, selected_int_kind,
selected_real_kind through the project index, iso_c_binding, double precision; character and quad refused), what is
bound and why the rest is not (private specifics called through their public generic, optional, allocatable,
assumed size, extents that are dummies, intents, value, array results, header-typed results, already bind(c)), and
the generated shim, header and ctypes wrapper used for real: built with gfortran into a shared library, called from
C (gcc) and from Python, results compared with the Fortran ones."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys

import pytest

from fobis import bindings as bd
from fobis.ai.impact import _is_public
from fobis.fobis import run_fobis

MODULE = """\
module calc
implicit none
private
integer, parameter :: ik = selected_int_kind(15)
integer, parameter :: rk = selected_real_kind(15, 307)
public :: ik, rk, scale, add_into, total, pair, twice, describe, maybe, grow, raw, counted, flag, fixed
interface twice
  module procedure twice_int, twice_real
end interface twice
contains
pure function scale(x, f) result(y)
  real(rk), intent(in) :: x(:)
  real(rk), intent(in), value :: f
  real(rk) :: y(size(x))
  y = f * x
end function scale
subroutine add_into(n, a, b)
  integer, intent(in) :: n
  real(rk), intent(in) :: a(n)
  real(rk), intent(inout) :: b(n)
  b = b + a
end subroutine add_into
integer(ik) function total(v)
  integer(ik), intent(in) :: v(:)
  total = sum(v)
end function total
pure function pair(i) result(p)
  integer, intent(in) :: i
  integer :: p(2)
  p = [i, -i]
end function pair
integer function twice_int(i)
  integer, intent(in) :: i
  twice_int = 2 * i
end function twice_int
real(rk) function twice_real(x)
  real(rk), intent(in) :: x
  twice_real = 2 * x
end function twice_real
subroutine describe(s)
  character(*), intent(in) :: s
end subroutine describe
subroutine maybe(x)
  real(rk), intent(in), optional :: x
end subroutine maybe
subroutine grow(v)
  real(rk), allocatable, intent(inout) :: v(:)
end subroutine grow
subroutine raw(a)
  real(rk), intent(in) :: a(*)
end subroutine raw
subroutine counted(x, n)
  real(rk), intent(out) :: x
  integer, intent(out) :: n
  x = 1.5_rk
  n = 7
end subroutine counted
logical function flag(b)
  logical, intent(in) :: b
  flag = .not. b
end function flag
integer function fixed(i) bind(c)
  integer, intent(in), value :: i
  fixed = i
end function fixed
end module calc
"""


def _bindings():
    from fobis.analysis.project import build_index
    from fobis.fobis import _generic_specifics
    from fobis.lint.engine import analyse

    file_units = analyse(MODULE, "calc.f90")
    project = build_index([file_units])
    module = file_units.units[0]
    return {b.procedure: b for b in bd.plan(module, project, _is_public, _generic_specifics(module))}


def test_types():
    class Project:
        kind_parameters = {"i8": "selected_int_kind(18)", "i2": "selected_int_kind(4)"}

        def real_precision(self, kind, local=None):
            return {"r4": 6, "r8": 15, "r16": 33}.get(kind)

    project = Project()
    for spec, c in (
        ("integer", "int32_t"),
        ("integer(i8)", "int64_t"),
        ("integer(kind=i2)", "int16_t"),
        ("integer(int8)", "int8_t"),
        ("integer*8", "int64_t"),
        ("real", "float"),
        ("real(r8)", "double"),
        ("real(kind=c_float)", "float"),
        ("double precision", "double"),
        ("logical", "bool"),
    ):
        assert bd.resolve_type(spec, project)[0].c == c, spec
    assert "character" in bd.resolve_type("character(len=*)", project)[1]
    assert "33 digits" in bd.resolve_type("real(r16)", project)[1]
    assert "cannot be resolved" in bd.resolve_type("integer(mystery)", project)[1]


def test_plan():
    found = _bindings()
    assert sorted(b for b, v in found.items() if not v.skipped) == [
        "add_into",
        "counted",
        "flag",
        "pair",
        "total",
        "twice_int",
        "twice_real",
    ]
    assert found["twice_int"].call == "twice"  # a private specific, called through its public generic
    assert found["scale"].skipped == "the result is an array without a literal shape"
    assert "character" in found["describe"].skipped and found["maybe"].skipped == "argument x is optional"
    assert found["grow"].skipped == "argument v is allocatable"
    assert found["raw"].skipped == "argument a is assumed-size or assumed-rank"
    assert found["fixed"].skipped.startswith("already bind(c)")
    assert found["add_into"].arguments[1].dims == ["n"] and found["pair"].result.dims == ["2"]
    assert found["total"].result.ctype.c == "int64_t"  # integer(ik) in the header, ik = selected_int_kind(15)
    assert bd.report(list(found.values())).startswith("7 of 13 procedure(s) bound")


@pytest.mark.skipif(shutil.which("gfortran") is None or shutil.which("gcc") is None, reason="gfortran and gcc")
def test_built_and_called(tmp_path):
    found = list(_bindings().values())
    (tmp_path / "calc.f90").write_text(MODULE)
    (tmp_path / "calc_c.f90").write_text(bd.shim(found, "calc"))
    (tmp_path / "calc.h").write_text(bd.header(found, "calc"))
    (tmp_path / "calc.py").write_text(bd.python(found, "calc"))
    subprocess.run(
        ["gfortran", "-fPIC", "-shared", "calc.f90", "calc_c.f90", "-o", "libcalc.so"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "call.c").write_text(
        '#include <stdio.h>\n#include "calc.h"\nint main(void) {\n'
        "  int64_t v[3] = {10000000000, 2, 3}; double a[2] = {1.0, 2.0}, b[2] = {0.5, 0.5}, x; int32_t n = 2, p[2], c;\n"
        "  calc_add_into(&n, a, b); calc_pair(&n, p); calc_counted(&x, &c);\n"
        '  printf("%lld %g %g %d %d %g %d %d\\n", (long long)calc_total(v, 3), b[0], b[1], p[0], p[1], x, c,\n'
        "         calc_twice_int(&n));\n  return 0;\n}\n"
    )
    subprocess.run(
        ["gcc", "call.c", "-L.", "-lcalc", "-Wl,-rpath,.", "-o", "call"], cwd=tmp_path, check=True, capture_output=True
    )
    out = subprocess.run(["./call"], cwd=tmp_path, check=True, capture_output=True, text=True).stdout
    assert out.split() == ["10000000005", "1.5", "2.5", "2", "-2", "1.5", "7", "4"]
    script = (
        "import sys; sys.path.insert(0, '.'); import calc; calc.load('./libcalc.so');"
        "print(calc.total([10000000000, 2, 3]), calc.add_into(2, [1.0, 2.0], [0.5, 0.5]), calc.pair(3),"
        " calc.counted(), calc.twice_real(1.25), calc.flag(True))"
    )
    out = subprocess.run([sys.executable, "-I", "-c", script], cwd=tmp_path, check=True, capture_output=True, text=True)
    assert out.stdout.strip() == "10000000005 [1.5, 2.5] [3, -3] (1.5, 7) 2.5 False"


def _run(args, capsys):
    try:
        run_fobis(fake_args=args)
        code = 0
    except SystemExit as exc:
        code = exc.code or 0
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_cli(tmp_path, monkeypatch, capsys):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "calc.f90").write_text(MODULE)
    (tmp_path / "fobos").write_text("[project]\nname = Calc\n\n[modes]\nmodes = gnu\n\n[gnu]\nsrc = ./src/\n")
    monkeypatch.chdir(tmp_path)
    code, out, _ = _run(["bindings", "--print", "--json"], capsys)
    data = json.loads(out)
    assert code == 0 and data["files"] == [] and len(data["bindings"]) == 13
    code, out, err = _run(["bindings"], capsys)
    assert code == 0 and "7 of 13 procedure(s) bound" in out + err
    assert sorted(p.name for p in (tmp_path / "bindings").iterdir()) == ["calc.h", "calc.py", "calc_c.f90"]
    assert _run(["bindings"], capsys)[0] == 2  # no overwrite
    assert _run(["bindings", "--force", "--name", "other", "-o", "b2"], capsys)[0] == 0
    assert (tmp_path / "b2" / "other.h").is_file()
    code, out, err = _run(["bindings", "nope"], capsys)
    assert code == 2 and "unknown module(s) nope" in out + err


@pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran")
def test_shim_sees_a_kind_the_module_does_not_export(tmp_path):
    """The bound module is private by default and takes R8P from another module: the shim repeats its use
    statements (before: 'Symbol r8p has no IMPLICIT type')."""
    from fobis.analysis.project import build_index
    from fobis.fobis import _generic_specifics
    from fobis.lint.engine import analyse

    kinds = "module kinds\nuse, intrinsic :: iso_fortran_env, only : R8P => real64\nend module kinds\n"
    nodes = (
        "module nodes\nuse kinds, only : R8P\nimplicit none\nprivate\npublic :: fill\ncontains\n"
        "pure subroutine fill(n, x)\ninteger, intent(in) :: n\nreal(R8P), intent(out) :: x(n)\nx = 1._R8P\n"
        "end subroutine fill\nend module nodes\n"
    )
    units = [analyse(kinds, "kinds.f90"), analyse(nodes, "nodes.f90")]
    module = units[1].units[0]
    found = bd.plan(module, build_index(units), _is_public, _generic_specifics(module))
    (tmp_path / "kinds.f90").write_text(kinds)
    (tmp_path / "nodes.f90").write_text(nodes)
    (tmp_path / "nodes_c.f90").write_text(bd.shim(found, "nodes"))
    result = subprocess.run(
        ["gfortran", "-c", "kinds.f90", "nodes.f90", "nodes_c.f90"], cwd=tmp_path, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
