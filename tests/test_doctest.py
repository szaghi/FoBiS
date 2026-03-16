"""Tests for FoBiS.py inline doctest functionality."""

import pytest

from tests.helpers import run_doctest


@pytest.mark.parametrize("n", range(1, 4))
def test_doctest(monkeypatch, n):
    """Test doctest scenario n."""
    assert run_doctest(monkeypatch, f"doctest-test{n}"), f"doctest-test{n} failed"
