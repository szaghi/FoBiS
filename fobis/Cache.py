"""
Cache.py — Build artifact cache for FoBiS.py.

Implements issue #172: content-addressed binary cache that skips rebuilding
unchanged ``use=fobos`` dependencies.

Cache key = SHA-256(source_commit | compiler | cflags_hash | fobis_version).
"""

from __future__ import annotations

import configparser
import hashlib
import os
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .utils import print_fake


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def normalise_cflags(cflags: str) -> str:
    """
    Sort flags, strip whitespace, remove duplicates.

    Parameters
    ----------
    cflags : str

    Returns
    -------
    str
    """
    flags = cflags.split()
    seen: set[str] = set()
    unique = [f for f in flags if not (f in seen or seen.add(f))]
    return " ".join(sorted(unique))


# ---------------------------------------------------------------------------
# Cache key
# ---------------------------------------------------------------------------


@dataclass
class CacheKey:
    """Identifies a unique build configuration."""

    source_commit: str
    compiler: str
    cflags_hash: str
    fobis_version: str

    def digest(self) -> str:
        """SHA-256 hex digest of all fields joined with '|'."""
        raw = "|".join([self.source_commit, self.compiler, self.cflags_hash, self.fobis_version])
        return hashlib.sha256(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Cache entry metadata
# ---------------------------------------------------------------------------


@dataclass
class CacheEntry:
    """Metadata for a single cache entry."""

    dep_name: str
    key_digest: str
    size_bytes: int
    timestamp: float
    compiler: str
    cflags_hash: str
    source_commit: str


# ---------------------------------------------------------------------------
# BuildCache
# ---------------------------------------------------------------------------


class BuildCache:
    """
    Content-addressed build artifact cache.

    Parameters
    ----------
    cache_dir : str
        Root directory for the cache store.
    disabled : bool
        When True, all hit() calls return False and store() is a no-op.
    print_n : callable, optional
    print_w : callable, optional
    """

    def __init__(
        self,
        cache_dir: str | None = None,
        disabled: bool = False,
        print_n: Callable[..., None] | None = None,
        print_w: Callable[..., None] | None = None,
    ) -> None:
        if cache_dir is None:
            cache_dir = os.environ.get("FOBIS_CACHE_DIR", os.path.join(os.path.expanduser("~"), ".fobis", "cache"))
        self.cache_dir = cache_dir
        self.disabled = disabled
        self.print_n = print_n if print_n is not None else print_fake
        self.print_w = print_w if print_w is not None else print_fake

    def key_for(self, dep_name: str, commit: str, compiler: str, cflags: str) -> CacheKey:
        """
        Compute the cache key for a given dependency build configuration.

        Parameters
        ----------
        dep_name : str
        commit : str
        compiler : str
        cflags : str
        """
        from . import __version__

        normalised = normalise_cflags(cflags)
        cflags_hash = hashlib.sha256(normalised.encode()).hexdigest()[:16]
        return CacheKey(
            source_commit=commit,
            compiler=compiler,
            cflags_hash=cflags_hash,
            fobis_version=__version__,
        )

    def _entry_path(self, key: CacheKey) -> str:
        digest = key.digest()
        return os.path.join(self.cache_dir, digest[:2], digest)

    def hit(self, key: CacheKey) -> bool:
        """Return True if artifacts for this key are in the cache."""
        if self.disabled:
            return False
        entry = self._entry_path(key)
        meta = os.path.join(entry, "meta.ini")
        return os.path.isdir(entry) and os.path.isfile(meta)

    def restore(self, key: CacheKey, target_dir: str) -> bool:
        """
        Copy cached artifacts to *target_dir*.

        Parameters
        ----------
        key : CacheKey
        target_dir : str

        Returns
        -------
        bool
            True on success.
        """
        if self.disabled:
            return False
        entry = self._entry_path(key)
        if not self.hit(key):
            return False
        try:
            for sub in ("lib", "include"):
                src = os.path.join(entry, sub)
                if os.path.isdir(src):
                    dst = os.path.join(target_dir, sub)
                    if os.path.exists(dst):
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
            return True
        except OSError as exc:
            self.print_w(f"Warning: cache restore failed: {exc}")
            return False

    def store(self, key: CacheKey, lib_dir: str, mod_dir: str) -> None:
        """
        Copy built artifacts into the cache under *key*.

        Parameters
        ----------
        key : CacheKey
        lib_dir : str
        mod_dir : str
        """
        if self.disabled:
            return
        entry = self._entry_path(key)
        tmp = entry + ".tmp"
        try:
            os.makedirs(tmp, exist_ok=True)
            if os.path.isdir(lib_dir):
                shutil.copytree(lib_dir, os.path.join(tmp, "lib"))
            if os.path.isdir(mod_dir):
                shutil.copytree(mod_dir, os.path.join(tmp, "include"))
            # write metadata
            cfg = configparser.RawConfigParser()
            cfg.add_section("cache")
            cfg.set("cache", "source_commit", key.source_commit)
            cfg.set("cache", "compiler", key.compiler)
            cfg.set("cache", "cflags_hash", key.cflags_hash)
            cfg.set("cache", "fobis_version", key.fobis_version)
            cfg.set("cache", "timestamp", str(time.time()))
            with open(os.path.join(tmp, "meta.ini"), "w") as f:
                cfg.write(f)
            # atomic rename
            os.makedirs(os.path.dirname(entry), exist_ok=True)
            if os.path.exists(entry):
                shutil.rmtree(entry)
            os.replace(tmp, entry)
            self.print_n(f"[cache] stored {key.digest()[:12]}")
        except OSError as exc:
            self.print_w(f"Warning: cache store failed: {exc}")
            if os.path.exists(tmp):
                shutil.rmtree(tmp, ignore_errors=True)

    def list_entries(self) -> list[CacheEntry]:
        """List all cache entries with metadata."""
        entries: list[CacheEntry] = []
        if not os.path.isdir(self.cache_dir):
            return entries
        for prefix_dir in os.listdir(self.cache_dir):
            prefix_path = os.path.join(self.cache_dir, prefix_dir)
            if not os.path.isdir(prefix_path):
                continue
            for digest_dir in os.listdir(prefix_path):
                entry_path = os.path.join(prefix_path, digest_dir)
                meta_path = os.path.join(entry_path, "meta.ini")
                if not os.path.isfile(meta_path):
                    continue
                cfg = configparser.RawConfigParser()
                cfg.read(meta_path)
                size = sum(
                    os.path.getsize(os.path.join(r, f))
                    for r, _, files in os.walk(entry_path)
                    for f in files
                )
                ts = float(cfg.get("cache", "timestamp", fallback="0"))
                entries.append(
                    CacheEntry(
                        dep_name="",
                        key_digest=digest_dir,
                        size_bytes=size,
                        timestamp=ts,
                        compiler=cfg.get("cache", "compiler", fallback=""),
                        cflags_hash=cfg.get("cache", "cflags_hash", fallback=""),
                        source_commit=cfg.get("cache", "source_commit", fallback=""),
                    )
                )
        return sorted(entries, key=lambda e: e.timestamp, reverse=True)

    def evict_older_than(self, days: int) -> int:
        """
        Delete entries older than *days* days.

        Parameters
        ----------
        days : int

        Returns
        -------
        int
            Count of deleted entries.
        """
        cutoff = time.time() - days * 86400
        deleted = 0
        for entry in self.list_entries():
            if entry.timestamp < cutoff:
                entry_path = os.path.join(self.cache_dir, entry.key_digest[:2], entry.key_digest)
                if os.path.exists(entry_path):
                    shutil.rmtree(entry_path, ignore_errors=True)
                    deleted += 1
        return deleted

    def format_entry_table(self, entries: list[CacheEntry] | None = None) -> str:
        """Return a formatted table string of cache entries."""
        if entries is None:
            entries = self.list_entries()
        if not entries:
            return "  (cache is empty)"
        lines = [f"  {'key':<14} {'compiler':<16} {'size':>8} {'date'}"]
        lines.append(f"  {'---':<14} {'--------':<16} {'----':>8} {'----'}")
        for e in entries:
            size_kb = e.size_bytes // 1024
            date = time.strftime("%Y-%m-%d", time.localtime(e.timestamp))
            lines.append(f"  {e.key_digest[:12]:<14} {e.compiler:<16} {size_kb:>6} KB {date}")
        return "\n".join(lines)
