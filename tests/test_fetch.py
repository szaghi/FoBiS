"""Tests for FoBiS.py fetch dependency modes."""

import tempfile

import pytest

from fobis.Fetcher import Fetcher
from tests.helpers import run_build

# ── unit tests: save_config / load_config ────────────────────────────────────


def test_fetch_sources_dep_goes_to_src_key():
    """use=sources dep must appear under 'src', not 'dependon'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        fetcher = Fetcher(deps_dir=tmpdir)
        deps_info = [
            {"name": "src_dep", "path": "/fake/src_dep", "mode": "", "use": "sources"},
            {"name": "fobos_dep", "path": "/fake/fobos_dep", "mode": "gnu", "use": "fobos"},
        ]
        fetcher.save_config(deps_info)
        cfg = fetcher.load_config()

        assert "src" in cfg
        assert "/fake/src_dep" in cfg["src"]
        assert "/fake/src_dep" not in " ".join(cfg.get("dependon", []))
        assert "dependon" in cfg
        assert any("/fake/fobos_dep/fobos:gnu" in e for e in cfg["dependon"])
        assert "/fake/fobos_dep" not in cfg.get("src", [])


def test_fetch_default_use_is_sources():
    """Default use=sources must produce 'src' key only — no 'dependon'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        fetcher = Fetcher(deps_dir=tmpdir)
        deps_info = [{"name": "dep", "path": "/fake/default", "mode": "", "use": "sources"}]
        fetcher.save_config(deps_info)
        cfg = fetcher.load_config()

        assert "src" in cfg
        assert "dependon" not in cfg


def test_fetch_fobos_dep_no_mode_no_colon():
    """use=fobos dep without a mode must have no colon suffix in the fobos path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        fetcher = Fetcher(deps_dir=tmpdir)
        deps_info = [{"name": "dep", "path": "/fake/fobos_dep", "mode": "", "use": "fobos"}]
        fetcher.save_config(deps_info)
        cfg = fetcher.load_config()

        assert "dependon" in cfg
        assert cfg["dependon"] == ["/fake/fobos_dep/fobos"]


def test_fetch_load_config_empty():
    """load_config on a missing file must return an empty dict."""
    with tempfile.TemporaryDirectory() as tmpdir:
        fetcher = Fetcher(deps_dir=tmpdir)
        assert fetcher.load_config() == {}


# ── integration tests ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("n", range(1, 5))
def test_fetch_dep_integration(monkeypatch, n):
    """Test fetch dependency integration scenario n."""
    assert run_build(monkeypatch, f"fetch-dep-test{n}"), f"fetch-dep-test{n} failed"
