"""Tests for FoBiS.py build functionality."""

import pytest

from tests.helpers import OPENCOARRAYS, PREFORM, run_build


@pytest.mark.parametrize("n", range(1, 33))
def test_build(monkeypatch, n):
    """Test build scenario n."""
    if n == 15 and not OPENCOARRAYS:
        pytest.skip("opencoarrays (caf) not available")
    if n == 5 and not PREFORM:
        pytest.skip("PreForM.py not available")
    assert run_build(monkeypatch, f"build-test{n}"), f"build-test{n} failed"
