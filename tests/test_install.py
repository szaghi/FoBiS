"""Tests for FoBiS.py install functionality."""

import pytest

from tests.helpers import run_install


@pytest.mark.parametrize("n", range(1, 5))
def test_install(monkeypatch, n):
    """Test install scenario n."""
    assert run_install(monkeypatch, f"install-test{n}"), f"install-test{n} failed"
