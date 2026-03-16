"""Tests for FoBiS.py install functionality."""

import pytest

from tests.helpers import run_install


@pytest.mark.parametrize("n", range(1, 5))
def test_install(n):
    """Test install scenario n."""
    assert run_install(f"install-test{n}"), f"install-test{n} failed"
