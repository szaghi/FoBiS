"""
Sources that are not git repositories: release manifests on static hosting, and redirect pages.

HTTP has no way to list the versions behind a URL, so a static host publishes one file, ``fortran-releases.toml``
(the GOPROXY idea in one file), at the URL itself, at ``<url>/fortran-releases.toml`` or at
``<url>/.well-known/fortran-releases.toml``::

    schema = 1
    name   = "some-lib"
    [[release]]
    version = "2.1.0"
    archive = "some-lib-2.1.0.tar.gz"   # relative to the manifest, or absolute
    sha256  = "..."

Anything that serves static files can host: a web server, an object store, a ``file://`` directory.

A redirect page (Go's vanity import paths) gives a package a stable URL on its owner's domain: an HTML page holding
``<meta name="fortran-source" content="git https://host/repo">`` (or ``manifest URL``) sends the probe there.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
import urllib.parse
from dataclasses import dataclass, field

from ..SemVer import Version
from .index import RegistryError, http_get, local_path
from .sources import SourceError, SourceInfo, default_name, inspect_tree, sort_versions

MANIFEST = "fortran-releases.toml"
SCHEMA = 1
GIT_HOSTS = ("github.com", "gitlab.com", "bitbucket.org", "codeberg.org", "git.sr.ht", "salsa.debian.org")
MAX_REDIRECTS = 3
_META = re.compile(r"""<meta\s+name=["']fortran-source["']\s+content=["']\s*(git|manifest)\s+([^"'\s]+)\s*["']""", re.I)


@dataclass
class Release:
    version: str
    archive: str  # absolute URL of the archive
    sha256: str


@dataclass
class Manifest:
    url: str  # where the manifest itself was read
    name: str = ""
    releases: list[Release] = field(default_factory=list)

    def release(self, version: str) -> Release | None:
        return next((r for r in self.releases if r.version.lstrip("v") == version.lstrip("v")), None)


def parse_manifest(text: str, url: str) -> Manifest:
    """Parse and validate a release manifest read from *url* (archive URLs made absolute)."""
    from ..fpm import FpmError, load_toml

    try:
        data = load_toml(text)
    except (FpmError, ValueError) as error:
        raise SourceError(f"{url}: not valid TOML: {error}") from error
    unknown = sorted(set(data) - {"schema", "name", "release"})
    if unknown:
        raise SourceError(f"{url}: unknown key(s) {', '.join(unknown)}")
    if data.get("schema", SCHEMA) != SCHEMA:
        raise SourceError(f"{url}: schema {data.get('schema')} is not {SCHEMA}: upgrade FoBiS")
    releases = []
    for i, entry in enumerate(data.get("release", [])):
        if not isinstance(entry, dict) or not all(
            isinstance(entry.get(k), str) for k in ("version", "archive", "sha256")
        ):
            raise SourceError(f"{url}: release {i + 1} needs version, archive and sha256 strings")
        unknown = sorted(set(entry) - {"version", "archive", "sha256"})
        if unknown:
            raise SourceError(f"{url}: release {entry['version']}: unknown key(s) {', '.join(unknown)}")
        if not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"].lower()):
            raise SourceError(f"{url}: release {entry['version']}: sha256 must be 64 hexadecimal digits")
        releases.append(Release(entry["version"], urllib.parse.urljoin(url, entry["archive"]), entry["sha256"].lower()))
    return Manifest(url=url, name=str(data.get("name", "")), releases=releases)


def _as_url(location: str) -> str:
    """A local path as a ``file://`` URL (so that relative archive names join), other URLs unchanged."""
    if "://" in location:
        return location
    return "file://" + urllib.parse.quote(os.path.abspath(os.path.expanduser(location)))


def _candidates(url: str) -> list[str]:
    base = url.rstrip("/")
    if base.endswith(MANIFEST):
        return [base]
    return [base + "/" + MANIFEST, base + "/.well-known/" + MANIFEST]


def find_manifest(url: str) -> Manifest | None:
    """The manifest a URL designates (the file itself, or one of the well-known places under it), or None."""
    for candidate in _candidates(_as_url(url)):
        path = local_path(candidate)
        if path is not None and not os.path.isfile(path):
            continue
        try:
            text = http_get(candidate).decode("utf-8")
        except RegistryError:
            continue
        return parse_manifest(text, candidate)
    return None


def _looks_like_git(url: str) -> bool:
    if url.startswith(("git@", "ssh://", "git://")) or url.rstrip("/").endswith(".git"):
        return True
    host = urllib.parse.urlparse(url).netloc.lower()
    return any(host == h or host.endswith("." + h) for h in GIT_HOSTS)


@dataclass
class Located:
    """Where a source URL leads: a git repository or a release manifest (after any redirect)."""

    kind: str  # git, manifest
    url: str  # the URL to use (the redirect target)
    manifest: Manifest | None = None
    via: list[str] = field(default_factory=list)  # redirect pages followed


_LOCATED: dict[str, Located] = {}


def locate(url: str) -> Located:
    """
    The probe chain of a source URL: redirect page -> git repository -> release manifest. Memoised per process.

    Raises
    ------
    SourceError
      a redirect loop or too many redirects
    """
    if url in _LOCATED:
        return _LOCATED[url]
    via: list[str] = []
    current = url
    while True:
        located = _locate_one(current)
        if located.kind != "redirect":
            located.via = via
            _LOCATED[url] = located
            return located
        if current in via or len(via) >= MAX_REDIRECTS:
            raise SourceError(f"{url}: too many redirects ({' -> '.join([*via, current])})")
        via.append(current)
        current = located.url


def _locate_one(url: str) -> Located:
    path = local_path(url)
    if path is not None:
        if (os.path.isfile(path) and path.endswith(MANIFEST)) or os.path.isfile(os.path.join(path, MANIFEST)):
            return Located("manifest", url, find_manifest(url))
        return Located("git", url)
    if _looks_like_git(url) or not url.startswith(("http://", "https://")):
        return Located("git", url)
    try:
        body = http_get(url)
    except RegistryError:
        return Located("git", url)  # nothing served at the URL itself: a git smart-HTTP server answers elsewhere
    text = body.decode("utf-8", errors="replace")
    meta = _META.search(text)
    if meta:
        target = urllib.parse.urljoin(url, meta.group(2))
        return Located("redirect", target)
    if url.rstrip("/").endswith(MANIFEST) or re.search(r"^\s*\[\[release\]\]", text, re.M):
        return Located("manifest", url, parse_manifest(text, url))
    manifest = find_manifest(url)
    if manifest is not None:
        return Located("manifest", manifest.url, manifest)
    return Located("git", url)


def is_manifest_source(url: str) -> bool:
    return locate(url).kind == "manifest"


def probe_manifest(url: str, inspect: bool = True) -> SourceInfo:
    """A `SourceInfo` of a manifest source (with *inspect*: the newest release downloaded and read)."""
    located = locate(url)
    manifest = located.manifest or find_manifest(located.url)
    if manifest is None:
        raise SourceError(f"{url}: no {MANIFEST} found")
    versions, _ = sort_versions([r.version for r in manifest.releases])
    info = SourceInfo(url=url, provider="manifest", versions=versions, latest=versions[0] if versions else "")
    info.name = manifest.name
    if inspect and info.latest:
        with tempfile.TemporaryDirectory(prefix="fobis-probe-") as scratch:
            dest = os.path.join(scratch, "src")
            fetch_release(manifest.release(info.latest), dest)
            inspect_tree(dest, info)
    if not info.name:
        info.name = default_name(url.rstrip("/").removesuffix(MANIFEST).rstrip("/"))
    return info


def select_release(manifest: Manifest, constraint: str = "", version: str = "") -> Release:
    """The release of an exact *version*, else the newest satisfying *constraint*, else the newest."""
    from ..SemVer import resolve

    if version:
        release = manifest.release(version)
        if release is None:
            raise SourceError(f"{manifest.url}: no release {version}")
        return release
    candidates = [r.version for r in manifest.releases]
    if constraint:
        chosen = resolve(candidates, constraint)
        if chosen is None:
            raise SourceError(f"{manifest.url}: no release satisfies {constraint}")
        return manifest.release(chosen)
    versions, _ = sort_versions(candidates)
    if not versions:
        raise SourceError(f"{manifest.url}: no release with a semantic version")
    return manifest.release(versions[0])


def fetch_release(release: Release, dest: str) -> str:
    """
    Download *release*'s archive, check its sha256, extract it into *dest* (created; its single top directory
    flattened). Returns the sha256.

    Raises
    ------
    SourceError
      download failure, checksum mismatch, an archive member escaping *dest*
    """
    from ..llm.errors import DownloadError
    from ..llm.runtime import _extract, _flatten

    with tempfile.TemporaryDirectory(prefix="fobis-release-") as scratch:
        name = os.path.basename(urllib.parse.urlparse(release.archive).path) or "archive.tar.gz"
        archive = os.path.join(scratch, name)
        data = http_get(release.archive)
        digest = hashlib.sha256(data).hexdigest()
        if digest != release.sha256:
            raise SourceError(
                f"{release.archive}: sha256 {digest[:16]}... does not match the manifest's {release.sha256[:16]}..."
            )
        with open(archive, "wb") as fh:
            fh.write(data)
        unpacked = os.path.join(scratch, "unpacked")
        os.makedirs(unpacked)
        try:
            _extract(archive, unpacked)
        except (DownloadError, OSError, EOFError, ValueError) as error:
            raise SourceError(f"{release.archive}: {error}") from error
        except Exception as error:  # tarfile.ReadError, zipfile.BadZipFile
            raise SourceError(f"{release.archive}: not a .tar.gz or .zip archive ({error})") from error
        _flatten(unpacked)
        if os.path.exists(dest):
            shutil.rmtree(dest)
        os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
        shutil.move(unpacked, dest)
    return digest


def newest(manifest: Manifest) -> str:
    versions = sorted((Version(r.version), r.version) for r in manifest.releases if _is_version(r.version))
    return versions[-1][1] if versions else ""


def _is_version(text: str) -> bool:
    try:
        Version(text)
    except ValueError:
        return False
    return True
