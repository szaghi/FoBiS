"""Tests for FoBiS.py custom rule execution."""

import pytest

from tests.helpers import run_rule


@pytest.mark.parametrize("n", range(1, 2))
def test_rule(monkeypatch, n):
    """Test custom rule scenario n."""
    assert run_rule(monkeypatch, f"rule-test{n}"), f"rule-test{n} failed"
