"""Tests for fobis.Cache — build artifact cache (issue #172)."""

from __future__ import annotations

import configparser
import os
import tempfile
import time
from unittest.mock import MagicMock, call, patch

import pytest

from fobis.Cache import BuildCache, CacheKey, normalise_cflags


# ── normalise_cflags ─────────────────────────────────────────────────────────


def test_normalise_cflags_sorts():
    assert normalise_cflags("-O2 -g") == normalise_cflags("-g -O2")


def test_normalise_cflags_deduplicates():
    result = normalise_cflags("-O2 -O2 -g")
    assert result.count("-O2") == 1


def test_normalise_cflags_strips_whitespace():
    result = normalise_cflags("  -O2   -g  ")
    assert "  " not in result


# ── CacheKey ─────────────────────────────────────────────────────────────────


def test_cache_key_deterministic():
    k1 = CacheKey("abc123", "gfortran-12", "deadbeef01234567", "3.7.0")
    k2 = CacheKey("abc123", "gfortran-12", "deadbeef01234567", "3.7.0")
    assert k1.digest() == k2.digest()


def test_cache_key_sensitive_to_cflags():
    k1 = CacheKey("abc123", "gfortran-12", "aaaaaaaaaaaa0000", "3.7.0")
    k2 = CacheKey("abc123", "gfortran-12", "bbbbbbbbbbbb0000", "3.7.0")
    assert k1.digest() != k2.digest()


def test_cache_key_sensitive_to_compiler():
    k1 = CacheKey("abc123", "gfortran-12", "deadbeef01234567", "3.7.0")
    k2 = CacheKey("abc123", "gfortran-13", "deadbeef01234567", "3.7.0")
    assert k1.digest() != k2.digest()


def test_cache_key_normalises_cflags_order():
    """The cache key helper (via key_for) normalises flag order."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = BuildCache(cache_dir=tmpdir)
        k1 = cache.key_for("dep", "abc123", "gfortran", "-O2 -g")
        k2 = cache.key_for("dep", "abc123", "gfortran", "-g -O2")
    assert k1.digest() == k2.digest()


# ── hit / miss ───────────────────────────────────────────────────────────────


def test_cache_hit_returns_true(tmp_path):
    cache = BuildCache(cache_dir=str(tmp_path))
    key = CacheKey("c0ffee", "gfortran", "aaaa", "3.7.0")
    entry = os.path.join(str(tmp_path), key.digest()[:2], key.digest())
    os.makedirs(entry, exist_ok=True)
    # Create meta.ini
    cfg = configparser.RawConfigParser()
    cfg.add_section("cache")
    cfg.set("cache", "source_commit", "c0ffee")
    cfg.set("cache", "compiler", "gfortran")
    cfg.set("cache", "cflags_hash", "aaaa")
    cfg.set("cache", "fobis_version", "3.7.0")
    cfg.set("cache", "timestamp", str(time.time()))
    with open(os.path.join(entry, "meta.ini"), "w") as f:
        cfg.write(f)
    assert cache.hit(key) is True


def test_cache_miss_returns_false(tmp_path):
    cache = BuildCache(cache_dir=str(tmp_path))
    key = CacheKey("deadc0de", "gfortran", "0000", "3.7.0")
    assert cache.hit(key) is False


def test_no_cache_flag_disables_hit(tmp_path):
    cache = BuildCache(cache_dir=str(tmp_path), disabled=True)
    key = CacheKey("c0ffee", "gfortran", "aaaa", "3.7.0")
    # Even if the entry dir exists, disabled cache always returns False
    entry = os.path.join(str(tmp_path), key.digest()[:2], key.digest())
    os.makedirs(entry, exist_ok=True)
    open(os.path.join(entry, "meta.ini"), "w").close()
    assert cache.hit(key) is False


# ── restore ──────────────────────────────────────────────────────────────────


def test_cache_restore_copies_files(tmp_path):
    cache = BuildCache(cache_dir=str(tmp_path))
    key = CacheKey("abc", "gfortran", "xx", "3.7.0")
    entry = os.path.join(str(tmp_path), key.digest()[:2], key.digest())
    lib_src = os.path.join(entry, "lib")
    os.makedirs(lib_src, exist_ok=True)
    # Write meta.ini so hit() returns True
    cfg = configparser.RawConfigParser()
    cfg.add_section("cache")
    cfg.set("cache", "source_commit", "abc")
    cfg.set("cache", "compiler", "gfortran")
    cfg.set("cache", "cflags_hash", "xx")
    cfg.set("cache", "fobis_version", "3.7.0")
    cfg.set("cache", "timestamp", str(time.time()))
    with open(os.path.join(entry, "meta.ini"), "w") as f:
        cfg.write(f)

    target = str(tmp_path / "target")
    os.makedirs(target)

    with patch("shutil.copytree") as mock_copy:
        result = cache.restore(key, target)

    assert result is True
    mock_copy.assert_called()


# ── store ────────────────────────────────────────────────────────────────────


def test_cache_store_writes_meta(tmp_path):
    lib_dir = tmp_path / "lib"
    mod_dir = tmp_path / "mod"
    lib_dir.mkdir()
    mod_dir.mkdir()
    cache_dir = tmp_path / "cache"

    cache = BuildCache(cache_dir=str(cache_dir))
    key = CacheKey("feed", "gfortran", "bbbb", "3.7.0")
    cache.store(key, str(lib_dir), str(mod_dir))

    # meta.ini should exist inside the entry directory
    entry = os.path.join(str(cache_dir), key.digest()[:2], key.digest())
    meta_path = os.path.join(entry, "meta.ini")
    assert os.path.isfile(meta_path)

    cfg = configparser.RawConfigParser()
    cfg.read(meta_path)
    assert cfg.get("cache", "compiler") == "gfortran"
    assert cfg.get("cache", "cflags_hash") == "bbbb"
    assert cfg.get("cache", "source_commit") == "feed"
    # Timestamp must be a valid float
    ts = float(cfg.get("cache", "timestamp"))
    assert ts > 0


def test_cache_store_disabled_is_noop(tmp_path):
    cache = BuildCache(cache_dir=str(tmp_path), disabled=True)
    key = CacheKey("abc", "gfortran", "cc", "3.7.0")
    cache.store(key, str(tmp_path), str(tmp_path))
    # Nothing written into the cache dir (still empty)
    assert list(tmp_path.iterdir()) == []


# ── evict_older_than ─────────────────────────────────────────────────────────


def test_evict_older_than(tmp_path):
    cache = BuildCache(cache_dir=str(tmp_path))
    now = time.time()

    # Create two entries: one old (31 days), one recent (1 day)
    for age_days, commit in [(31, "old000"), (1, "new000")]:
        key = CacheKey(commit, "gfortran", "dd", "3.7.0")
        entry = os.path.join(str(tmp_path), key.digest()[:2], key.digest())
        os.makedirs(entry, exist_ok=True)
        ts = now - age_days * 86400
        cfg = configparser.RawConfigParser()
        cfg.add_section("cache")
        cfg.set("cache", "source_commit", commit)
        cfg.set("cache", "compiler", "gfortran")
        cfg.set("cache", "cflags_hash", "dd")
        cfg.set("cache", "fobis_version", "3.7.0")
        cfg.set("cache", "timestamp", str(ts))
        with open(os.path.join(entry, "meta.ini"), "w") as f:
            cfg.write(f)

    deleted = cache.evict_older_than(30)
    assert deleted == 1


# ── unwritable cache dir ──────────────────────────────────────────────────────


def test_unwritable_cache_dir_warns_not_aborts(tmp_path):
    """PermissionError during store must emit a warning, not raise."""
    lib_dir = tmp_path / "lib"
    mod_dir = tmp_path / "mod"
    lib_dir.mkdir()
    mod_dir.mkdir()

    warnings = []
    cache = BuildCache(cache_dir="/nonexistent/unwritable", print_w=warnings.append)
    key = CacheKey("abc", "gfortran", "ee", "3.7.0")

    with patch("os.makedirs", side_effect=PermissionError("denied")):
        cache.store(key, str(lib_dir), str(mod_dir))  # must not raise

    assert any("Warning" in w or "cache" in w.lower() for w in warnings)
