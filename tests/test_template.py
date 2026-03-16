"""Tests for FoBiS.py fobos template handling."""

import os

import pytest

from fobis.fobis import run_fobis
from tests.helpers import TESTS_DIR


def test_circular_template_detection():
    """Circular template references must be detected and abort with SystemExit."""
    old_pwd = os.getcwd()
    os.chdir(os.path.join(TESTS_DIR, "template-circular-test1"))
    try:
        with pytest.raises(SystemExit):
            run_fobis(fake_args=["build", "-f", "fobos"])
    finally:
        os.chdir(old_pwd)
