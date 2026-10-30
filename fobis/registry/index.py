"""
Package indexes: schema, providers, cache and the index graph.

An index (``index.toml``) names packages by their source URL::

    schema  = 1
    name    = "szaghi"
    follows = ["https://github.com/someone/fortran-index"]

    [package.penf]
    source      = "https://github.com/szaghi/PENF"
    description = "Portability Environment for Fortran"
    provides    = ["penf"]

It holds no versions, dependencies or hashes: the source is the authority (Go's model). An index is reached through a
provider chosen from its URL: a local directory or file, a static ``*.toml`` file over HTTP(S), or a git repository
(``index.toml`` at its root). Fetched indexes are cached in ``~/.fobis/indexes/<name>/`` (``FOBIS_INDEX_DIR``).
"""

from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any

SCHEMA = 1
INDEX_FILE = "index.toml"
DEFAULT_DEPTH = 2
HTTP_TIMEOUT = 30

_PACKAGE_KEYS = {"source", "description", "license", "keywords", "mirrors", "provides", "recipe"}
_TOP_KEYS = {"schema", "name", "description", "follows", "package"}
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class RegistryError(Exception):
    """An index cannot be read, or is not a valid index."""


@dataclass
class Package:
    """One package entry of an index."""

    name: str
    source: str
    description: str = ""
    license: str = ""
    keywords: list[str] = field(default_factory=list)
    mirrors: list[str] = field(default_factory=list)
    provides: list[str] = field(default_factory=list)
    recipe: str = ""
    index: str = ""  # the qualified name of the index it was read from (filled when loaded through an IndexSet)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"name": self.name, "source": self.source}
        for key in ("description", "license", "keywords", "mirrors", "provides", "recipe", "index"):
            value = getattr(self, key)
            if value:
                data[key] = value
        return data


@dataclass
class Index:
    """A parsed index."""

    name: str
    packages: dict[str, Package] = field(default_factory=dict)
    follows: list[str] = field(default_factory=list)
    description: str = ""
    origin: str = ""  # URL or path it was read from

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "origin": self.origin,
            "description": self.description,
            "follows": self.follows,
            "packages": [p.to_dict() for p in self.packages.values()],
        }


def _load_toml(text: str) -> dict:
    from ..fpm import FpmError, load_toml

    try:
        return load_toml(text)
    except (FpmError, ValueError) as error:
        raise RegistryError(f"not valid TOML: {error}") from error


def _strings(value: Any, where: str) -> list[str]:
    if isinstance(value, str):
        return [value]
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise RegistryError(f"{where} must be a list of strings")
    return list(value)


def load_index(text: str, origin: str = "") -> Index:
    """
    Parse and validate an index.

    Parameters
    ----------
    text : str
      the TOML text
    origin : str
      where it was read from (for messages)

    Raises
    ------
    RegistryError
      not TOML, unknown keys, a missing ``source``, a schema newer than this FoBiS
    """
    where = f"index {origin}: " if origin else "index: "
    try:
        data = _load_toml(text)
    except RegistryError as error:
        raise RegistryError(where + str(error)) from None
    unknown = sorted(set(data) - _TOP_KEYS)
    if unknown:
        raise RegistryError(where + f"unknown key(s) {', '.join(unknown)}")
    schema = data.get("schema", SCHEMA)
    if not isinstance(schema, int) or schema < 1:
        raise RegistryError(where + "schema must be a positive integer")
    if schema > SCHEMA:
        raise RegistryError(where + f"schema {schema} is newer than this FoBiS reads ({SCHEMA}): upgrade FoBiS")
    name = data.get("name", "")
    if not isinstance(name, str) or (name and not _NAME.match(name)):
        raise RegistryError(where + f"name {name!r} is not a valid index name")
    try:
        follows = _strings(data.get("follows", []), "follows")
    except RegistryError as error:
        raise RegistryError(where + str(error)) from None
    packages_data = data.get("package", {})
    if not isinstance(packages_data, dict):
        raise RegistryError(where + "[package.NAME] tables expected")
    packages: dict[str, Package] = {}
    for pname, entry in packages_data.items():
        if not _NAME.match(pname):
            raise RegistryError(where + f"package name {pname!r} is not valid")
        if not isinstance(entry, dict):
            raise RegistryError(where + f"[package.{pname}] must be a table")
        unknown = sorted(set(entry) - _PACKAGE_KEYS)
        if unknown:
            raise RegistryError(where + f"[package.{pname}]: unknown key(s) {', '.join(unknown)}")
        source = entry.get("source")
        if not isinstance(source, str) or not source.strip():
            raise RegistryError(where + f"[package.{pname}]: 'source' (the package URL) is required")
        try:
            package = Package(
                name=pname,
                source=source.strip(),
                description=str(entry.get("description", "")),
                license=str(entry.get("license", "")),
                keywords=_strings(entry.get("keywords", []), f"[package.{pname}] keywords"),
                mirrors=_strings(entry.get("mirrors", []), f"[package.{pname}] mirrors"),
                provides=[m.lower() for m in _strings(entry.get("provides", []), f"[package.{pname}] provides")],
                recipe=str(entry.get("recipe", "")),
            )
        except RegistryError as error:
            raise RegistryError(where + str(error)) from None
        packages[pname] = package
    return Index(
        name=name, packages=packages, follows=follows, description=str(data.get("description", "")), origin=origin
    )


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)  # a JSON string is a valid TOML basic string


def _toml_list(values: list[str]) -> str:
    return "[" + ", ".join(_toml_string(v) for v in values) + "]"


def dump_index(index: Index) -> str:
    """Write an index as TOML, deterministically (packages sorted by name, keys in schema order)."""
    lines = [f"schema = {SCHEMA}"]
    if index.name:
        lines.append(f"name = {_toml_string(index.name)}")
    if index.description:
        lines.append(f"description = {_toml_string(index.description)}")
    if index.follows:
        lines.append(f"follows = {_toml_list(index.follows)}")
    for pname in sorted(index.packages, key=str.lower):
        package = index.packages[pname]
        # a name may hold dots (odbc.f): bare, TOML would read a nested table
        table = pname if "." not in pname else _toml_string(pname)
        lines += ["", f"[package.{table}]", f"source = {_toml_string(package.source)}"]
        for key in ("description", "license", "recipe"):
            if getattr(package, key):
                lines.append(f"{key} = {_toml_string(getattr(package, key))}")
        for key in ("keywords", "mirrors", "provides"):
            if getattr(package, key):
                lines.append(f"{key} = {_toml_list(getattr(package, key))}")
    return "\n".join(lines) + "\n"


# ── providers ─────────────────────────────────────────────────────────────────


def provider_of(url: str) -> str:
    """
    The provider of an index URL: ``dir`` / ``file`` (local, also ``file://``), ``http`` (a static ``*.toml`` over
    HTTP(S)) or ``git`` (anything else: a repository holding ``index.toml`` at its root).
    """
    path = local_path(url)
    if path is not None:
        if os.path.isfile(path):
            return "file"
        is_repo = os.path.isdir(os.path.join(path, ".git")) or os.path.isfile(os.path.join(path, "HEAD"))
        if url.startswith("file://") and is_repo:  # a file:// URL is a remote: its committed state, as git sees it
            return "git"
        if not os.path.exists(path) and not url.startswith("file://"):
            return "dir"  # reported as not found
        if os.path.isdir(path) and not os.path.isfile(os.path.join(path, "HEAD")):
            return "dir"  # a plain path, a checkout included: its working tree (an index being written)
        return "git"  # a bare repository, or a file:// URL git will report
    if url.startswith(("http://", "https://")) and urllib.parse.urlparse(url).path.endswith(".toml"):
        return "http"
    return "git"


def local_path(url: str) -> str | None:
    """The local path of a ``file://`` URL or a plain path; None for a remote URL."""
    if url.startswith("file://"):
        return urllib.parse.unquote(urllib.parse.urlparse(url).path)
    if "://" in url or url.startswith("git@"):
        return None
    return os.path.abspath(os.path.expanduser(url))


def git_env() -> dict[str, str]:
    """The environment of every git call of the registry: never prompt for credentials (a missing repo would)."""
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env.setdefault("GIT_ASKPASS", "true")
    return env


def run_git(
    *args: str, cwd: str | None = None, timeout: int = 300, anonymous: bool = False
) -> subprocess.CompletedProcess:
    """
    Run git without a prompt or colours, capturing its output. *anonymous*: without the user's credentials (no
    credential helper, no SSH), to tell whether a repository is readable by anyone.
    """
    env = git_env()
    extra = ["-c", "credential.helper="] if anonymous else []
    if anonymous:
        env["GIT_SSH_COMMAND"] = "false"  # an insteadOf rule turning https into ssh must not use the user's keys
    return subprocess.run(
        ["git", "-c", "color.ui=never", *extra, *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
        check=False,
    )


def http_get(url: str, timeout: int = HTTP_TIMEOUT) -> bytes:
    """GET a URL (http, https or file) and return its body; RegistryError on failure."""
    request = urllib.request.Request(url, headers={"User-Agent": "FoBiS.py"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except (OSError, ValueError) as error:
        raise RegistryError(f"cannot read {url}: {error}") from error


def read_index_text(url: str, cache_dir: str | None = None, refresh: bool = False) -> tuple[str, str]:
    """
    Read the text of the index at *url*.

    A local index is read in place. A remote one is fetched into *cache_dir* (``index.toml`` + ``meta.json``) and,
    unless *refresh*, read from there when cached.

    Returns
    -------
    tuple[str, str]
      ``(text, provider)``
    """
    provider = provider_of(url)
    if provider in ("dir", "file"):
        path = local_path(url) or url
        if provider == "dir":
            path = os.path.join(path, INDEX_FILE)
        if not os.path.isfile(path):
            raise RegistryError(f"index {url}: {path} not found")
        with open(path, encoding="utf-8") as fh:
            return fh.read(), provider
    cached = os.path.join(cache_dir, INDEX_FILE) if cache_dir else None
    if cached and os.path.isfile(cached) and not refresh and _cached_url(cache_dir) == url:
        with open(cached, encoding="utf-8") as fh:
            return fh.read(), provider
    if provider == "http":
        text = http_get(url).decode("utf-8")
    else:
        text = _git_index_text(url, cache_dir)
    if cache_dir:
        _store(cache_dir, url, provider, text)
    return text, provider


def _git_index_text(url: str, cache_dir: str | None) -> str:
    """Shallow-clone (or update) the index repository and read its ``index.toml``."""
    with tempfile.TemporaryDirectory(prefix="fobis-index-") as scratch:
        checkout = os.path.join(scratch, "repo")
        result = run_git("clone", "--depth", "1", "--quiet", url, checkout)
        if result.returncode != 0:
            lines = result.stderr.strip().splitlines()
            raise RegistryError(f"index {url}: git clone failed ({lines[-1] if lines else 'no output'})")
        path = os.path.join(checkout, INDEX_FILE)
        if not os.path.isfile(path):
            raise RegistryError(f"index {url}: the repository has no {INDEX_FILE} at its root")
        with open(path, encoding="utf-8") as fh:
            return fh.read()


def _cached_url(cache_dir: str) -> str:
    try:
        with open(os.path.join(cache_dir, "meta.json"), encoding="utf-8") as fh:
            return json.load(fh).get("url", "")
    except (OSError, ValueError):
        return ""


def cache_meta(cache_dir: str) -> dict[str, Any]:
    """The cache metadata of an index (``url``, ``provider``, ``fetched_at``); empty when not cached."""
    try:
        with open(os.path.join(cache_dir, "meta.json"), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _store(cache_dir: str, url: str, provider: str, text: str) -> None:
    os.makedirs(cache_dir, exist_ok=True)
    for name, content in (
        (INDEX_FILE, text),
        (
            "meta.json",
            json.dumps(
                {
                    "url": url,
                    "provider": provider,
                    "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                },
                indent=2,
            )
            + "\n",
        ),
    ):
        fd, tmp = tempfile.mkstemp(dir=cache_dir, prefix=".tmp-")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, os.path.join(cache_dir, name))


def default_cache_root() -> str:
    """Where fetched indexes are cached: ``$FOBIS_INDEX_DIR``, else ``~/.fobis/indexes``."""
    return os.environ.get("FOBIS_INDEX_DIR") or os.path.join(os.path.expanduser("~"), ".fobis", "indexes")


def _cache_name(url: str) -> str:
    """A directory name for a followed index (no configured name): readable part + short digest of the URL."""
    import hashlib

    stem = re.sub(r"[^A-Za-z0-9]+", "-", url.split("://")[-1]).strip("-")[-40:]
    return f"{stem}-{hashlib.sha256(url.encode()).hexdigest()[:8]}"


# ── the index graph ───────────────────────────────────────────────────────────


@dataclass
class LoadedIndex:
    """An index reached through the graph walk."""

    qualifier: str  # the name used in qualified package names: the configured name for roots, else the index name
    url: str
    index: Index
    depth: int
    via: str = ""  # the qualifier of the index that follows it ("" for a configured root)


@dataclass
class IndexSet:
    """
    The indexes a user reaches: the configured roots (in priority order) and, breadth-first, those they follow.

    Parameters
    ----------
    roots : list[tuple[str, str]]
      ``(name, url)`` of the configured indexes, in priority order
    cache_root : str
      cache directory (``default_cache_root()``)
    depth : int
      how far ``follows`` is walked (0: roots only)
    """

    roots: list[tuple[str, str]]
    cache_root: str = field(default_factory=default_cache_root)
    depth: int = DEFAULT_DEPTH
    loaded: list[LoadedIndex] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def load(self, refresh: bool = False, only: str | None = None, offline: bool = False) -> IndexSet:
        """
        Walk the graph; an index that cannot be read is recorded in ``errors`` and skipped. *offline*: a remote index
        is read from the cache only (a build or a check never reaches the network).
        """
        self.loaded, self.errors = [], []
        seen: set[str] = set()
        queue: list[tuple[str, str, int, str]] = [(name, url, 0, "") for name, url in self.roots]
        used: set[str] = set()
        while queue:
            name, url, depth, via = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            if only and depth == 0 and name != only:
                continue
            cache = os.path.join(self.cache_root, name if depth == 0 else _cache_name(url))
            if offline and provider_of(url) in ("git", "http") and _cached_url(cache) != url:
                continue
            try:
                text, _ = read_index_text(url, cache, refresh=refresh)
                index = load_index(text, origin=url)
            except RegistryError as error:
                self.errors.append(f"{name or url}: {error}")
                continue
            qualifier = name if depth == 0 else (index.name or _cache_name(url))
            if qualifier in used:  # two followed indexes with the same name: keep both, the later one qualified
                qualifier = f"{qualifier}~{_cache_name(url)[-8:]}"
            used.add(qualifier)
            for package in index.packages.values():
                package.index = qualifier
            self.loaded.append(LoadedIndex(qualifier, url, index, depth, via))
            if depth < self.depth:
                queue.extend(("", follow, depth + 1, qualifier) for follow in index.follows)
        return self

    def packages(self) -> list[Package]:
        """Every package of every loaded index, in priority order (roots first, then followed indexes)."""
        return [p for loaded in self.loaded for p in loaded.index.packages.values()]

    def lookup(self, name: str) -> list[Package]:
        """
        The packages a name designates: ``INDEX:NAME`` names one index; a bare name matches every index (case
        insensitive). The same source listed by several indexes counts once (the first, by priority).
        """
        qualifier, _, bare = name.rpartition(":")
        found: list[Package] = []
        sources: set[str] = set()
        for package in self.packages():
            if package.name.lower() != bare.lower() or (qualifier and package.index != qualifier):
                continue
            key = normalise_source(package.source)
            if key in sources:
                continue
            sources.add(key)
            found.append(package)
        return found

    def providers(self, module: str) -> list[Package]:
        """The packages whose cached ``provides`` lists *module* (case insensitive)."""
        module = module.lower()
        found, sources = [], set()
        for package in self.packages():
            if module in package.provides and normalise_source(package.source) not in sources:
                sources.add(normalise_source(package.source))
                found.append(package)
        return found

    def search(self, term: str) -> list[Package]:
        """Packages whose name, description or keywords contain *term* (case insensitive); empty term: all."""
        term = term.lower()
        return [
            p
            for p in self.packages()
            if not term
            or term in p.name.lower()
            or term in p.description.lower()
            or any(term in k.lower() for k in p.keywords)
        ]


def normalise_source(url: str) -> str:
    """A source URL compared with others: lower-case host, no trailing ``/`` or ``.git``."""
    url = url.strip().rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    parts = urllib.parse.urlsplit(url)
    if parts.scheme and parts.netloc:
        return urllib.parse.urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, "", ""))
    return url


def configured_roots(user_config: Any = None, fobos: Any = None) -> list[tuple[str, str]]:
    """
    The configured indexes, in priority order: a project fobos ``[indexes]`` first (its relative paths are relative
    to the fobos), then the user configuration ``[indexes]``; a name configured twice keeps the project's.
    """
    roots: list[tuple[str, str]] = []
    if fobos is not None:
        for name, url in fobos_indexes(fobos):
            roots.append((name, url))
    if user_config is not None:
        names = {n for n, _ in roots}
        roots += [(n, u) for n, u in user_config.indexes if n not in names]
    return roots


def fobos_indexes(fobos: Any) -> list[tuple[str, str]]:
    """``[indexes]`` of a fobos as ``(name, url)``; a relative local path is made relative to the fobos file."""
    config = getattr(fobos, "fobos", None)
    if not config or not config.has_section("indexes"):
        return []
    base = os.path.dirname(os.path.abspath(getattr(fobos, "filename", None) or "fobos"))
    entries = []
    for name, url in config.items("indexes"):
        url = url.strip()
        if local_path(url) is not None and not url.startswith("file://") and not os.path.isabs(os.path.expanduser(url)):
            url = os.path.normpath(os.path.join(base, url))
        entries.append((name, url))
    return entries


def cached_providers(module: str, fobos: Any = None) -> list[Package]:
    """
    The packages of the user's indexes that provide *module*, read OFFLINE (local indexes and cached remote ones):
    used by ``check`` and ``build --explain`` to name a package for a missing module. Never raises.
    """
    from ..UserConfig import UserConfig

    try:
        roots = configured_roots(UserConfig(), fobos)
        if not roots:
            return []
        return IndexSet(roots).load(offline=True).providers(module)
    except Exception:  # a hint must never break the command that asks for it
        return []


def remove_cache(cache_root: str, name: str) -> None:
    """Delete the cache of a configured index (nothing when absent)."""
    path = os.path.join(cache_root, name)
    if os.path.isdir(path) and os.path.isfile(os.path.join(path, "meta.json")):
        shutil.rmtree(path)


# ── building an index ─────────────────────────────────────────────────────────


def build_index(seeds: Index, probe: Any, keep: bool = True) -> tuple[Index, list[str]]:
    """
    Fill an index from its seeds: each package's ``description``, ``license`` and ``provides`` come from probing
    its source (``probe(url) -> SourceInfo``); with *keep*, a field written by hand in the seeds wins.

    Returns
    -------
    tuple[Index, list[str]]
      the built index and one message per source that could not be read (its seed entry is kept as written)
    """
    built = Index(name=seeds.name, follows=list(seeds.follows), description=seeds.description, origin=seeds.origin)
    errors: list[str] = []
    for name, seed in seeds.packages.items():
        package = Package(**{k: v for k, v in vars(seed).items() if k != "index"})
        try:
            info = probe(seed.source)
        except RegistryError as error:
            errors.append(f"{name}: {error}")
            built.packages[name] = package
            continue
        for key, value in (("description", info.description), ("license", info.license)):
            if value and not (keep and getattr(package, key)):
                setattr(package, key, value)
        if info.modules and not (keep and package.provides):
            package.provides = list(info.modules)
        built.packages[name] = package
    return built, errors
