"""Tests for FoBiS.py build functionality."""

import pytest

from tests.helpers import OPENCOARRAYS, run_build


@pytest.mark.parametrize("n", range(1, 33))
def test_build(n):
    """Test build scenario n."""
    if n == 15 and not OPENCOARRAYS:
        pytest.skip("opencoarrays (caf) not available")
    assert run_build(f"build-test{n}"), f"build-test{n} failed"
