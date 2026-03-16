"""Tests for FoBiS.py fobos template handling."""

import os

import pytest

from fobis.fobis import run_fobis
from tests.helpers import TESTS_DIR


def test_circular_template_detection(monkeypatch):
    """Circular template references must be detected and abort with SystemExit."""
    monkeypatch.chdir(os.path.join(TESTS_DIR, "template-circular-test1"))
    with pytest.raises(SystemExit):
        run_fobis(fake_args=["build", "-f", "fobos"])
