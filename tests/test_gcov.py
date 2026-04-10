"""Tests for Gcov.py — gcov file analysis and reporting."""

from __future__ import annotations

import pytest

from fobis.Gcov import Gcov, _mermaid_pie


# ── Helpers ────────────────────────────────────────────────────────────────────

# Synthetic gcov file content covering the main parse paths:
#   - subroutine/function procedure detection
#   - normal counts, "#####" (unexecuted), "-" (not executable)
#   - "=====" (excluded), "N*" (branch-hit), bad integer (ValueError path)
#   - LCOV_EXCL_LINE, LCOV_EXCL_START/END markers
_GCOV_CONTENT = """\
        -:    0:Source:test.f90
       10:    1:  subroutine executed_sub(x)
        -:    2:    implicit none
        5:    3:    integer :: x
    #####:    4:    x = 0
        -:    5:  end subroutine executed_sub
        0:    6:  subroutine unexecuted_sub()
        -:    7:    implicit none
        -:    8:  end subroutine unexecuted_sub
        3:    9:  function my_func()
        -:   10:    integer :: r
        3:   11:    r = 42
        -:   12:  end function my_func
    =====:   13:    excluded_line
      10*:   14:    branched_line
"""

# Gcov content exercising LCOV exclusion markers
_GCOV_LCOV = """\
        -:    0:Source:lcov.f90
    #####:    1:    normal_uncovered
    #####:    2:    excl_line !LCOV_EXCL_LINE
       10:    3:    start_block !LCOV_EXCL_START
    #####:    4:    inside_block
       10:    5:    end_block !LCOV_EXCL_END
    #####:    6:    after_block
"""

# Gcov content with a bad (non-integer) coverage counter — triggers ValueError path
_GCOV_BADINT = """\
        -:    0:Source:bad.f90
     ????:    1:    some_line
"""


def _write_gcov(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content)
    return str(p)


# ── _mermaid_pie ───────────────────────────────────────────────────────────────


def test_mermaid_pie_contains_title_and_values():
    result = _mermaid_pie("My Chart", "80", "20")
    assert "My Chart" in result
    assert '"Executed" : 80' in result
    assert '"Unexecuted" : 20' in result
    assert "```mermaid" in result


# ── Gcov init and empty parse ──────────────────────────────────────────────────


def test_gcov_init_no_filename():
    g = Gcov()
    assert g.filename is None
    assert g.coverage == []
    assert g.procedures == []


def test_gcov_parse_no_filename():
    g = Gcov()
    g.parse()
    assert g.metrics["coverage"] is None
    assert g.metrics["procedures"] is None


def test_gcov_parse_nonexistent_file():
    g = Gcov(filename="/nonexistent/path.gcov")
    g.parse()
    assert g.coverage == []


# ── Main parse path ────────────────────────────────────────────────────────────


def test_gcov_parse_detects_procedures(tmp_path):
    path = _write_gcov(tmp_path, "test.gcov", _GCOV_CONTENT)
    g = Gcov(filename=path)
    g.parse()
    proc_names = [p[1] for p in g.procedures]
    assert "executed_sub" in proc_names
    assert "unexecuted_sub" in proc_names
    assert "my_func" in proc_names


def test_gcov_parse_procedure_hits(tmp_path):
    path = _write_gcov(tmp_path, "test.gcov", _GCOV_CONTENT)
    g = Gcov(filename=path)
    g.parse()
    hits = {p[1]: p[2] for p in g.procedures}
    assert hits["executed_sub"] == 10
    assert hits["unexecuted_sub"] == 0
    assert hits["my_func"] == 3


def test_gcov_parse_populates_metrics(tmp_path):
    path = _write_gcov(tmp_path, "test.gcov", _GCOV_CONTENT)
    g = Gcov(filename=path)
    g.parse()
    assert g.metrics["coverage"] is not None
    assert g.metrics["procedures"] is not None
    # metrics["coverage"] = [lnumber, elnumber, unelnumber, pct_exec, pct_unexec, ahits]
    assert int(g.metrics["coverage"][0]) > 0  # at least one executable line


def test_gcov_parse_special_coverage_tokens(tmp_path):
    """===== and N* tokens are parsed without error."""
    path = _write_gcov(tmp_path, "test.gcov", _GCOV_CONTENT)
    g = Gcov(filename=path)
    g.parse()
    # If we get here without exception, special tokens were handled correctly.
    assert g.coverage  # non-empty


def test_gcov_parse_bad_integer_token(tmp_path):
    """A non-integer, non-special coverage counter triggers the ValueError path → 0."""
    path = _write_gcov(tmp_path, "bad.gcov", _GCOV_BADINT)
    g = Gcov(filename=path)
    g.parse()
    # The "????" line should result in a 0 appended (ValueError → cov_num_int = 0)
    assert 0 in g.coverage


# ── LCOV exclusion markers ────────────────────────────────────────────────────


def test_gcov_parse_lcov_excl_line(tmp_path):
    """LCOV_EXCL_LINE suppresses counting on that single line."""
    path = _write_gcov(tmp_path, "lcov.gcov", _GCOV_LCOV)
    g = Gcov(filename=path)
    g.parse()
    # Line 1 is normal unexecuted → 0; line 2 has LCOV_EXCL_LINE → None
    # Coverage list index 0 = line 1, index 1 = line 2
    assert g.coverage[0] == 0   # normal #####
    assert g.coverage[1] is None  # LCOV_EXCL_LINE suppressed


def test_gcov_parse_lcov_excl_start_end(tmp_path):
    """Lines inside an LCOV_EXCL_START/END block are suppressed."""
    path = _write_gcov(tmp_path, "lcov.gcov", _GCOV_LCOV)
    g = Gcov(filename=path)
    g.parse()
    # index 3 = line 4 (inside block, cov_num="#####", ignoring=True → None)
    assert g.coverage[3] is None


def test_gcov_parse_lcov_nested_start_warns(tmp_path, capsys):
    """Nested LCOV_EXCL_START emits a warning to stderr."""
    content = (
        "        -:    0:Source:x.f90\n"
        "       10:    1:  start1 !LCOV_EXCL_START\n"
        "       10:    2:  start2 !LCOV_EXCL_START\n"
        "       10:    3:  end !LCOV_EXCL_END\n"
    )
    path = _write_gcov(tmp_path, "nested.gcov", content)
    g = Gcov(filename=path)
    g.parse()
    captured = capsys.readouterr()
    assert "nested" in captured.err.lower() or "LCOV_EXCL_START" in captured.err


def test_gcov_parse_lcov_end_outside_zone_warns(tmp_path, capsys):
    """LCOV_EXCL_END without a matching START emits a warning to stderr."""
    content = (
        "        -:    0:Source:x.f90\n"
        "       10:    1:  end !LCOV_EXCL_END\n"
    )
    path = _write_gcov(tmp_path, "stray_end.gcov", content)
    g = Gcov(filename=path)
    g.parse()
    captured = capsys.readouterr()
    assert "LCOV_EXCL_END" in captured.err


# ── save() ─────────────────────────────────────────────────────────────────────


def test_gcov_save_markdown_report(tmp_path):
    path = _write_gcov(tmp_path, "test.gcov", _GCOV_CONTENT)
    g = Gcov(filename=path)
    g.parse()
    out_path = str(tmp_path / "report.md")
    g.save(output=out_path)
    text = open(out_path).read()
    assert "Coverage" in text or "coverage" in text.lower()
    assert "Executed" in text
    assert "Unexecuted" in text
    assert "mermaid" in text  # _mermaid_pie output is included


def test_gcov_save_includes_procedure_tables(tmp_path):
    path = _write_gcov(tmp_path, "test.gcov", _GCOV_CONTENT)
    g = Gcov(filename=path)
    g.parse()
    out_path = str(tmp_path / "report.md")
    g.save(output=out_path)
    text = open(out_path).read()
    assert "executed_sub" in text or "Executed procedures" in text
    assert "unexecuted_sub" in text or "Unexecuted procedures" in text


def test_gcov_save_default_output_path(tmp_path, monkeypatch):
    """When output= is omitted, the report is written next to the gcov file name."""
    monkeypatch.chdir(tmp_path)
    path = _write_gcov(tmp_path, "mymodule.gcov", _GCOV_CONTENT)
    g = Gcov(filename=path)
    g.parse()
    g.save()  # no output= → uses basename-derived filename in cwd
    assert (tmp_path / "mymodule.gcov-report.md").exists()
