"""``fobis build --timings`` (issue #218, phase 0): every compile and link measured."""

from __future__ import annotations

import json
import os
import shutil
import types

import pytest

from fobis import timings
from fobis.fobis import run_fobis

GFORTRAN = shutil.which("gfortran") is not None


def _pfile(name, deps=(), include=False):
    return types.SimpleNamespace(name=name, pfile_dep=list(deps), include=include)


def _record(file, start, seconds, kind="compile", status=0, rss=None):
    return {"file": file, "kind": kind, "status": status, "start": start, "seconds": seconds, "peak_rss_kib": rss}


def test_summary_of_known_durations():
    # a <- b <- d, a <- c <- d: critical path a + c + d = 1 + 5 + 2 = 8; serial 1 + 2 + 5 + 2 = 10
    a = _pfile("a")
    b = _pfile("b", [a])
    c = _pfile("c", [a])
    d = _pfile("d", [b, c])
    records = [
        _record("a", 0.0, 1.0),
        _record("b", 1.0, 2.0),
        _record("c", 1.0, 5.0, rss=2048),
        _record("d", 6.0, 2.0),
        _record("d.exe", 8.0, 0.5, kind="link"),
    ]
    summary = timings.summarise(records, timings.compiled_dependencies([a, b, c, d]), jobs=2)
    assert summary["serial_seconds"] == 10.0
    assert summary["critical_path_seconds"] == 8.0
    assert summary["makespan_seconds"] == 8.0
    assert summary["lower_bound_seconds"] == 8.0
    assert summary["efficiency"] == round(10 / 16, 3)
    assert summary["link_seconds"] == 0.5
    assert summary["peak_rss_kib"] == 2048
    assert [s["file"] for s in summary["slowest"]][:2] == ["c", "b"]


def test_include_stands_for_what_it_includes():
    a = _pfile("a")
    inc = _pfile("x.inc", [a], include=True)
    b = _pfile("b", [inc])
    assert timings.compiled_dependencies([a, inc, b])["b"] == ["a"]


def test_files_not_compiled_cost_nothing():
    a = _pfile("a")
    b = _pfile("b", [a])
    summary = timings.summarise([_record("b", 0.0, 3.0)], timings.compiled_dependencies([a, b]), jobs=4)
    assert summary["critical_path_seconds"] == 3.0
    assert summary["compiles"] == 1


def test_run_measured_reports_status_output_and_memory():
    status, output, rss = timings.run_measured(["sh", "-c", "echo hello; exit 3"])
    assert status == 3
    assert output == "hello\n"
    if hasattr(os, "wait4"):
        assert rss and rss > 0


def test_run_measured_missing_command():
    status, output, _ = timings.run_measured("no-such-compiler-xyz -c a.f90")
    assert status == 127
    assert "command not found" in output


def _project(root):
    src = root / "src"
    src.mkdir()
    (src / "a.f90").write_text("module a\ncontains\nsubroutine sa()\nend subroutine\nend module\n")
    (src / "b.f90").write_text("module b\nuse a\nend module\n")
    (src / "p.f90").write_text("program p\nuse b\nend program\n")
    return src


@pytest.mark.skipif(not GFORTRAN, reason="gfortran not on PATH")
def test_build_writes_the_timings(tmp_path, monkeypatch, capsys):
    _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    run_fobis(fake_args=["build", "--src", "src", "-j", "2", "--timings"])
    document = json.loads((tmp_path / "obj" / timings.TIMINGS_FILE).read_text())
    assert document["schema"] == timings.SCHEMA
    compiled = sorted(r["file"] for r in document["records"] if r["kind"] == "compile")
    assert compiled == ["src/a.f90", "src/b.f90", "src/p.f90"]
    assert [r["kind"] for r in document["records"]].count("link") == 1
    assert document["summary"]["compiles"] == 3
    assert document["summary"]["critical_path_seconds"] > 0
    assert "Timings (3 compiles, 0 failed, -j 2)" in capsys.readouterr().out


@pytest.mark.skipif(not GFORTRAN, reason="gfortran not on PATH")
def test_no_timings_without_the_option(tmp_path, monkeypatch):
    _project(tmp_path)
    monkeypatch.chdir(tmp_path)
    run_fobis(fake_args=["build", "--src", "src"])
    assert not (tmp_path / "obj" / timings.TIMINGS_FILE).exists()


@pytest.mark.skipif(not GFORTRAN, reason="gfortran not on PATH")
def test_a_failed_build_is_measured_too(tmp_path, monkeypatch):
    src = _project(tmp_path)
    (src / "b.f90").write_text("module b\nuse a\ninteger :: = 1\nend module\n")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        run_fobis(fake_args=["build", "--src", "src", "--timings"])
    document = json.loads((tmp_path / "obj" / timings.TIMINGS_FILE).read_text())
    assert document["summary"]["failed_compiles"] == 1
