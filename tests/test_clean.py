"""Tests for FoBiS.py clean functionality."""

import pytest

from tests.helpers import run_clean


@pytest.mark.parametrize("n", range(1, 2))
def test_clean(monkeypatch, n):
    """Test clean scenario n."""
    assert run_clean(monkeypatch, f"clean-test{n}"), f"clean-test{n} failed"
