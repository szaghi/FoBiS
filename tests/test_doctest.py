"""Tests for FoBiS.py inline doctest functionality."""

import pytest

from fobis.fobis import run_fobis
from tests.helpers import run_doctest


@pytest.mark.parametrize("n", range(1, 4))
def test_doctest(monkeypatch, n):
    """Test doctest scenario n."""
    assert run_doctest(monkeypatch, f"doctest-test{n}"), f"doctest-test{n} failed"


_MODULE = """module arithmetic
implicit none
private
public :: add
contains
  function add(a, b) result(c)
  !< Add two integers.
  !<
  !<```fortran
  !< {statement}
  !<```
  !=> 45 <<<
  integer, intent(in) :: a
  integer, intent(in) :: b
  integer             :: c

  c = a + b
  endfunction add
endmodule arithmetic
"""


def _run_doctests(monkeypatch, tmp_path, statement):
    """Run the doctests of a module with a single doctest executing the given statement, expecting 45."""
    (tmp_path / "arithmetic.f90").write_text(_MODULE.format(statement=statement))
    monkeypatch.chdir(tmp_path)
    run_fobis(fake_args=["doctests", "--compiler", "gnu", "--quiet", "--build-dir", "build"])


def test_doctest_passed_exits_cleanly(monkeypatch, tmp_path):
    """A passing doctest does not make the command fail."""
    _run_doctests(monkeypatch, tmp_path, 'print "(I0)", add(a=12, b=33)')


def test_doctest_wrong_result_fails(monkeypatch, tmp_path):
    """A doctest giving a wrong result makes the command exit with an error."""
    with pytest.raises(SystemExit) as excinfo:
        _run_doctests(monkeypatch, tmp_path, 'print "(I0)", add(a=12, b=34)')
    assert excinfo.value.code == 1


def test_doctest_runtime_error_fails(monkeypatch, tmp_path):
    """A doctest exiting with an error is a failed doctest, not a silently skipped one."""
    with pytest.raises(SystemExit) as excinfo:
        _run_doctests(monkeypatch, tmp_path, "error stop 3")
    assert excinfo.value.code == 1
