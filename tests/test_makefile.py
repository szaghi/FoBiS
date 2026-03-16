"""Tests for FoBiS.py Makefile generation."""

import pytest

from tests.helpers import make_makefile


@pytest.mark.parametrize("n", range(1, 3))
def test_makefile(monkeypatch, n):
    """Test Makefile generation scenario n."""
    assert make_makefile(monkeypatch, f"makefile-test{n}"), f"makefile-test{n} failed"
