"""Tests for ``fobis query`` (phase V6 of PLAN-verification.md): every query kind on a two-file project with
generics, type-bound procedures (also on subscripted objects), contained procedures, a module variable renamed on
``use``, intents of actual arguments, ``;``-separated statements, OpenACC regions and device data, MPI calls; the
errors; the CLI with the mode's sources."""

from __future__ import annotations

import json

import pytest

from fobis.analysis.project import build_index
from fobis.analysis.query import CodeGraph, QueryError, query, render_text
from fobis.fobis import run_fobis
from fobis.lint.engine import analyse

MODULE = """\
module m
implicit none
real :: g
real, allocatable :: field(:)
!$acc declare create(g)
type :: t
contains
procedure :: run => t_run
procedure :: val => t_val
end type t
interface gen
module procedure a, b
end interface gen
contains
subroutine a(x)
real, intent(out) :: x
x = g
call b(x)
call inner()
contains
subroutine inner()
g = 2.0 ; field = g
end subroutine inner
end subroutine a
subroutine b(x)
real, intent(inout) :: x
x = f(x) + 1
end subroutine b
real function f(y)
real, intent(in) :: y
f = y
end function f
subroutine t_run(self)
class(t), intent(in) :: self
end subroutine t_run
real function t_val(self)
class(t), intent(in) :: self
t_val = g
end function t_val
end module m
"""
PROGRAM = """\
program p
use m, only: gen, t, gg => g, field
implicit none
type(t) :: obj, objs(3)
real :: z
integer :: i, ierr
!$acc data copyin(field)
!$acc parallel loop
do i = 1, 2
  field(i) = gg + obj%val()
end do
!$acc end data
call gen(z)
call obj%run()
call objs(i)%run()
call a(gg)
read(*, *) gg
allocate(field(10))
call mpi_allreduce(z, z, 1, 1, 1, 1, ierr)
call mpi_barrier(1, ierr)
call external_thing(z)
end program p
"""


@pytest.fixture(scope="module")
def graph():
    files = {name: analyse(text, name) for name, text in (("m.f90", MODULE), ("p.f90", PROGRAM))}
    return CodeGraph(files, build_index(files.values()))


def _lines(result):
    return sorted(i["line"] for i in result.items)


def test_calls(graph):
    callees = query(graph, "callees", "p")
    assert {(i["line"], i["name"], i["how"]) for i in callees.items} == {
        (10, "val", "binding"),
        (13, "gen", "generic"),
        (14, "run", "binding"),
        (15, "run", "binding"),  # objs(i)%run: a subscripted object
        (16, "a", "unique"),
        (19, "mpi_allreduce", "unresolved"),
        (20, "mpi_barrier", "unresolved"),
        (21, "external_thing", "unresolved"),
    }
    assert "external_thing, mpi_allreduce, mpi_barrier" in callees.notes[0]
    callers = query(graph, "callers", "b")
    assert [(i["caller"], i["how"], i.get("candidate", False)) for i in callers.items] == [
        ("m::a", "contained", False),
        ("p", "generic", True),
    ]
    assert "candidate" in callers.notes[0]
    assert _lines(query(graph, "callers", "m::t_run")) == [14, 15]
    assert _lines(query(graph, "callers", "f")) == [27]  # a function reference
    assert query(graph, "callers", "nothere").notes == ["nothere is not defined in the analysed sources"]


def test_accesses(graph):
    writers = query(graph, "writers", "m::g")
    assert [(i["unit"], i["line"], i["is"], i.get("how")) for i in writers.items] == [
        ("m::a::inner", 22, "host module variable", "assignment"),
        ("p", 16, "use, renamed from g", "actual argument of m::a, intent(out)"),
        ("p", 17, "use, renamed from g", "read statement"),
    ]
    readers = query(graph, "readers", "m::g")
    assert sorted((i["unit"], i["line"]) for i in readers.items) == [
        ("m::a", 17),
        ("m::a::inner", 22),  # field = g, after the semicolon
        ("m::t_val", 38),
        ("p", 10),
    ]
    field = query(graph, "writers", "field")
    assert sorted((i["line"], i.get("how")) for i in field.items) == [
        (10, "assignment"),
        (18, "allocate"),
        (22, "assignment"),
    ]
    with pytest.raises(QueryError, match="is not a variable name"):
        query(graph, "writers", "m::")


def test_names_regions_device_mpi(graph):
    defines = query(graph, "defines", "run")
    assert [(i["kind"], i["qualified"], i["detail"]) for i in defines.items] == [("binding", "m::t%run", "t_run")]
    assert [i["kind"] for i in query(graph, "defines", "gen").items] == ["generic"]
    assert query(graph, "uses", "m").items[0]["only"] == ["field", "gen", "gg", "t"]
    interface = query(graph, "interface", "a")
    assert interface.items[0]["signature"].splitlines() == ["subroutine a(x)", "real, intent(out) :: x"]
    assert query(graph, "interface", "gen").items == [{"generic": "gen", "specifics": ["a", "b"]}]
    region = query(graph, "region", "p.f90:10")
    assert [(i["construct"], i["line"], i["end_line"]) for i in region.items] == [
        ("data", 7, 11),
        ("parallel loop", 8, 11),
    ]
    assert region.items[0]["clauses"] == {"copyin": ["field"]}
    assert "no OpenMP/OpenACC region" in query(graph, "region", "p.f90:16").notes[0]
    device = query(graph, "device", "field")
    assert [(i["line"], i.get("implicit", False)) for i in device.items] == [(7, False), (8, True)]
    assert "declared device-resident in module m" in query(graph, "device", "g").notes[-1]
    mpi = query(graph, "mpi")
    assert [(i["routine"], i["kind"]) for i in mpi.items] == [
        ("mpi_allreduce", "collective"),
        ("mpi_barrier", "collective"),
    ]
    assert len(query(graph, "mpi", "collective").items) == 2 and not query(graph, "mpi", "io").items
    assert "m.f90:18: m::a [call, contained] -> m::b: call b(x)" in render_text(query(graph, "callers", "b"))
    for kind, argument, message in (
        ("who", "x", "unknown query"),
        ("callers", "", "needs an argument"),
        ("region", "p.f90", "FILE:LINE"),
    ):
        with pytest.raises(QueryError, match=message):
            query(graph, kind, argument)


def test_cli(tmp_path, monkeypatch, capsys):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "m.f90").write_text(MODULE)
    (tmp_path / "src" / "p.f90").write_text(PROGRAM)
    (tmp_path / "fobos").write_text("[modes]\nmodes = gnu\n\n[gnu]\ncompiler = gnu\nsrc = ./src/\n")
    monkeypatch.chdir(tmp_path)
    run_fobis(fake_args=["query", "callers", "b", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["files"] == 2 and [i["caller"] for i in data["items"]] == ["m::a", "p"]
    run_fobis(fake_args=["query", "mpi"])
    out = capsys.readouterr().out
    assert "src/p.f90:19: mpi_allreduce [collective] in p" in out and "(2 file(s) analysed)" in out
    with pytest.raises(SystemExit) as exit_info:
        run_fobis(fake_args=["query", "who", "x"])
    assert exit_info.value.code == 2
