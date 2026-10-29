"""
The installed-package store: ``<root>/<toolchain key>/<name>/<version>/{bin,lib,include,lib/pkgconfig}``.

``root`` is ``$FOBIS_PKGS_DIR`` or ``~/.fobis/pkgs``. Every install leaves a receipt in ``<root>/receipts.json``
(name, source, version, identity, toolchain, prefix, backend, the files written and the application shims), so that
``fobis pkg list/uninstall/upgrade`` know exactly what they handle: uninstall removes the recorded files only.
"""

from __future__ import annotations

import datetime
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from typing import Any

RECEIPTS = "receipts.json"


def default_root() -> str:
    return os.environ.get("FOBIS_PKGS_DIR") or os.path.join(os.path.expanduser("~"), ".fobis", "pkgs")


@dataclass
class Receipt:
    name: str
    source: str
    version: str
    identity: str  # git tree hash or archive sha256
    key: str  # toolchain key
    prefix: str
    backend: str
    toolchain: dict[str, Any] = field(default_factory=dict)
    files: list[str] = field(default_factory=list)  # relative to prefix
    shims: list[str] = field(default_factory=list)  # absolute paths of the application links
    modules: list[str] = field(default_factory=list)
    installed_at: str = ""
    spec: str = ""  # what the user asked (name, INDEX:NAME, URL) and the version constraint, for upgrade
    constraint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Store:
    root: str = field(default_factory=default_root)

    def prefix(self, key: str, name: str, version: str) -> str:
        return os.path.join(self.root, key, name, version.lstrip("v") or "unversioned")

    def receipts(self) -> list[Receipt]:
        path = os.path.join(self.root, RECEIPTS)
        if not os.path.isfile(path):
            return []
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return [Receipt(**entry) for entry in data.get("packages", [])]

    def _save(self, receipts: list[Receipt]) -> None:
        os.makedirs(self.root, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.root, prefix=".receipts-")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({"schema": 1, "packages": [r.to_dict() for r in receipts]}, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, os.path.join(self.root, RECEIPTS))

    def find(self, name: str, key: str = "") -> list[Receipt]:
        return [r for r in self.receipts() if r.name == name and (not key or r.key == key)]

    def record(self, receipt: Receipt) -> None:
        """Add a receipt, replacing the one of the same name, toolchain and version."""
        receipt.installed_at = receipt.installed_at or datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="seconds"
        )
        kept = [
            r
            for r in self.receipts()
            if not (r.name == receipt.name and r.key == receipt.key and r.version == receipt.version)
        ]
        self._save([*kept, receipt])

    def forget(self, receipt: Receipt) -> None:
        self._save(
            [
                r
                for r in self.receipts()
                if not (r.name == receipt.name and r.key == receipt.key and r.version == receipt.version)
            ]
        )

    def remove(self, receipt: Receipt) -> list[str]:
        """Delete the recorded files and shims of *receipt* (nothing else), prune empty directories, forget it."""
        removed = []
        for shim in receipt.shims:
            if os.path.islink(shim) and os.path.realpath(shim).startswith(os.path.realpath(receipt.prefix) + os.sep):
                os.remove(shim)
                removed.append(shim)
        for rel in receipt.files:
            path = os.path.join(receipt.prefix, rel)
            if os.path.isfile(path) or os.path.islink(path):
                os.remove(path)
                removed.append(path)
        for dirpath, _dirnames, _filenames in sorted(os.walk(receipt.prefix), key=lambda t: -t[0].count(os.sep)):
            if os.path.isdir(dirpath) and not os.listdir(dirpath):
                os.rmdir(dirpath)
        parent = os.path.dirname(receipt.prefix)
        while parent.startswith(self.root + os.sep) and os.path.isdir(parent) and not os.listdir(parent):
            os.rmdir(parent)
            parent = os.path.dirname(parent)
        self.forget(receipt)
        return removed


def files_under(prefix: str) -> list[str]:
    """Every file under *prefix*, relative to it, sorted."""
    found = []
    for dirpath, _dirnames, filenames in os.walk(prefix):
        for filename in filenames:
            found.append(os.path.relpath(os.path.join(dirpath, filename), prefix))
    return sorted(found)


def link_applications(executables: list[str], bin_dir: str) -> tuple[list[str], list[str]]:
    """
    Symlink each executable into *bin_dir*. A name already there is left alone unless it is a link into the same
    store (an older version of the same package). Returns (links made, names refused).
    """
    os.makedirs(bin_dir, exist_ok=True)
    made, refused = [], []
    for exe in executables:
        link = os.path.join(bin_dir, os.path.basename(exe))
        if os.path.lexists(link):
            target = os.path.realpath(link)
            if not (os.path.islink(link) and _same_store(target, exe)):
                refused.append(link)
                continue
            os.remove(link)
        os.symlink(exe, link)
        made.append(link)
    return made, refused


def _same_store(target: str, exe: str) -> bool:
    """Whether *target* is the same application of another version of the same package in the store."""
    # <root>/<key>/<name>/<version>/bin/<exe>: same root/key/name, same basename
    t, e = target.split(os.sep), os.path.realpath(exe).split(os.sep)
    return len(t) == len(e) and t[:-4] == e[:-4] and t[-2:] == e[-2:]


def copy_tree(src: str, dest: str) -> None:
    """Copy a directory tree, merging into *dest*."""
    shutil.copytree(src, dest, dirs_exist_ok=True)
