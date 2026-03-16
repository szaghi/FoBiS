"""Tests for FoBiS.py inline doctest functionality."""

import pytest

from tests.helpers import run_doctest


@pytest.mark.parametrize("n", range(1, 4))
def test_doctest(n):
    """Test doctest scenario n."""
    assert run_doctest(f"doctest-test{n}"), f"doctest-test{n} failed"
