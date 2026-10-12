"""pack.py — knowledge packs: metadata, chunks, locations."""

# Copyright (C) 2015  Stefano Zaghi
#
# This file is part of FoBiS.py.
#
# FoBiS.py is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# FoBiS.py is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with FoBiS.py. If not, see <http://www.gnu.org/licenses/>.

from __future__ import annotations

import configparser
import json
import os
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from importlib.resources.abc import Traversable  # Python 3.11+; type checking only
    from typing import TypeAlias

    PackPath: TypeAlias = Path | Traversable

INDEX_VERSION = 1
# Filesystem location of the shipped packs (for building them); reading goes through `shipped_root`, which also
# works when FoBiS runs from a zip archive (the standalone fobis.pyz).
SHIPPED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "packs")
_PACK_KEYS = ("name", "version", "title", "license", "attribution", "source", "source_rev", "status", "notice")


class PackError(ValueError):
    """A knowledge pack is missing, malformed or cannot be built."""


@dataclass(frozen=True)
class Chunk:
    """A retrievable piece of a pack: one section (or part of a long section) of one document.

    Attributes
    ----------
    id : str
        Stable, citable identifier ``pack:doc#heading-slug``.
    pack, doc : str
    heading : str
        Heading path, ``"Data environment > Data-sharing attribute clauses"``.
    text : str
        Markdown text of the section.
    symbols : tuple of str
        Exact technical names the section is about (directives, clauses, routines, constraint ids).
    """

    id: str
    pack: str
    doc: str
    heading: str
    text: str
    symbols: tuple[str, ...] = ()


@dataclass
class Pack:
    """A knowledge pack: metadata plus its chunks."""

    name: str
    path: PackPath
    meta: dict[str, str] = field(default_factory=dict)
    chunks: list[Chunk] = field(default_factory=list)
    scope: str = "shipped"  # shipped | user | project

    @property
    def license(self) -> str:
        return self.meta.get("license", "")

    def notice(self) -> str:
        """Text of the pack's NOTICE file ('' when absent)."""
        notice = self.path / self.meta.get("notice", "NOTICE")
        return notice.read_text(encoding="utf-8") if notice.is_file() else ""


def _as_path(path: str | PackPath) -> PackPath:
    return Path(path) if isinstance(path, str) else path


def read_meta(path: str | PackPath) -> dict[str, str]:
    """The ``[pack]`` section of ``<path>/pack.ini``.

    Raises
    ------
    PackError
        The file is missing or has no ``[pack]`` section with a ``name``.
    """
    ini = _as_path(path) / "pack.ini"
    parser = configparser.ConfigParser()
    try:
        parser.read_string(ini.read_text(encoding="utf-8"))
    except (OSError, configparser.Error) as exc:
        raise PackError(f"{ini}: {exc}") from exc
    if not parser.has_option("pack", "name"):
        raise PackError(f"{ini}: no [pack] section with a name")
    return {key: parser.get("pack", key) for key in _PACK_KEYS if parser.has_option("pack", key)}


def write_meta(path: str, meta: dict[str, str]) -> None:
    """Write ``<path>/pack.ini``."""
    parser = configparser.ConfigParser()
    parser["pack"] = {key: meta[key] for key in _PACK_KEYS if meta.get(key)}
    with open(os.path.join(path, "pack.ini"), "w", encoding="utf-8") as handle:
        parser.write(handle)


def load_pack(path: str | PackPath, scope: str = "shipped") -> Pack:
    """Load the pack stored in directory *path* (a filesystem path or a package resource).

    Raises
    ------
    PackError
        Metadata or index missing or malformed.
    """
    path = _as_path(path)
    meta = read_meta(path)
    index = path / "index.json"
    try:
        data = json.loads(index.read_text(encoding="utf-8"))
        if data.get("version") != INDEX_VERSION:
            raise PackError(f"{index}: index version {data.get('version')}, expected {INDEX_VERSION}")
        chunks = [
            Chunk(
                id=c["id"],
                pack=meta["name"],
                doc=c["doc"],
                heading=c["heading"],
                text=c["text"],
                symbols=tuple(c.get("symbols", ())),
            )
            for c in data["chunks"]
        ]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise PackError(f"{index}: {exc}") from exc
    return Pack(name=meta["name"], path=path, meta=meta, chunks=chunks, scope=scope)


def user_dir() -> str:
    """Directory of the user's packs: ``$XDG_CONFIG_HOME/fobis/kb`` (default ``~/.config/fobis/kb``)."""
    base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return os.path.join(base, "fobis", "kb")


def project_dir(root: str = ".") -> str:
    """Directory of a project's packs: ``<root>/.fobis/kb``."""
    return os.path.join(root, ".fobis", "kb")


def shipped_root() -> PackPath:
    """The directory of the shipped packs, as a package resource."""
    return files("fobis.kb") / "packs"


def pack_dirs(root: str = ".") -> list[tuple[str, PackPath]]:
    """(scope, directory) holding packs, narrowest scope first: project, user, shipped."""
    return [("project", Path(project_dir(root))), ("user", Path(user_dir())), ("shipped", shipped_root())]


def discover_packs(root: str = ".") -> list[Pack]:
    """Every installed pack; on a name clash the narrowest scope wins (project > user > shipped).

    Malformed packs are skipped here; `load_pack` reports why.
    """
    found: dict[str, Pack] = {}
    for scope, directory in pack_dirs(root):
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir(), key=lambda p: p.name):
            if not (path / "pack.ini").is_file():
                continue
            try:
                pack = load_pack(path, scope)
            except PackError:
                continue
            found.setdefault(pack.name, pack)
    return sorted(found.values(), key=lambda p: p.name)
