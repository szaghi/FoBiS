"""
Software Heritage as the last resort of a public git source.

Software Heritage archives public repositories and names every directory by an identifier computed like git's tree
hash (``swh:1:dir:<tree>``), so content fetched from it is checked against the lock's ``tree`` exactly. It is a
network service: used only when a dependency asks for it (``:: archive=swh``) and its source and mirrors failed.

Path: origin visit -> snapshot -> ``refs/tags/<tag>`` (release -> revision) -> directory -> vault ``flat`` bundle
(cooked asynchronously: requested, polled, downloaded).
"""

from __future__ import annotations

import io
import json
import os
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request

from .index import RegistryError

DEFAULT_API = "https://archive.softwareheritage.org/api/1/"
POLL_SECONDS = 5.0
TIMEOUT = 900.0


def api_root() -> str:
    return os.environ.get("FOBIS_SWH_API") or DEFAULT_API


def _request(url: str, method: str = "GET") -> bytes:
    request = urllib.request.Request(
        url, method=method, headers={"User-Agent": "FoBiS.py", "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()
    except OSError as error:
        raise RegistryError(f"Software Heritage: {url}: {error}") from error


def _json(url: str, method: str = "GET") -> dict:
    try:
        return json.loads(_request(url, method))
    except ValueError as error:
        raise RegistryError(f"Software Heritage: {url}: not JSON") from error


def directory_of(origin: str, tag: str, api: str | None = None) -> str:
    """The directory (tree) id of *tag* in the latest archived visit of *origin*."""
    api = api or api_root()
    visit = _json(
        urllib.parse.urljoin(api, f"origin/{urllib.parse.quote(origin, safe='')}/visit/latest/?require_snapshot=true")
    )
    snapshot = visit.get("snapshot")
    if not snapshot:
        raise RegistryError(f"Software Heritage has no snapshot of {origin}")
    branches = _json(urllib.parse.urljoin(api, f"snapshot/{snapshot}/")).get("branches", {})
    branch = branches.get(f"refs/tags/{tag}")
    if not branch:
        raise RegistryError(f"Software Heritage: the archived {origin} has no tag {tag}")
    target, kind = branch["target"], branch["target_type"]
    if kind == "release":
        release = _json(urllib.parse.urljoin(api, f"release/{target}/"))
        target, kind = release["target"], release["target_type"]
    if kind != "revision":
        raise RegistryError(f"Software Heritage: tag {tag} of {origin} names a {kind}, not a revision")
    return _json(urllib.parse.urljoin(api, f"revision/{target}/"))["directory"]


def fetch_directory(directory: str, dest: str, api: str | None = None, poll: float = POLL_SECONDS) -> None:
    """Cook (if needed) and download the ``flat`` bundle of a directory, extracted into *dest*."""
    from ..llm.runtime import _flatten, _safe_target

    api = api or api_root()
    url = urllib.parse.urljoin(api, f"vault/flat/swh:1:dir:{directory}/")
    status = _json(url, method="POST")
    deadline = time.monotonic() + TIMEOUT
    while status.get("status") not in ("done", "failed"):
        if time.monotonic() > deadline:
            raise RegistryError(f"Software Heritage: bundle of {directory} not ready after {TIMEOUT:.0f} s")
        time.sleep(poll)
        status = _json(url)
    if status["status"] == "failed":
        raise RegistryError(f"Software Heritage could not cook {directory}: {status.get('progress_message', '')}")
    data = _request(urllib.parse.urljoin(api, status["fetch_url"]))
    with tempfile.TemporaryDirectory(prefix="fobis-swh-") as scratch:
        root = os.path.realpath(scratch)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
            members = tf.getmembers()
            for member in members:
                _safe_target(root, member.name)
                if member.issym() or member.islnk():
                    _safe_target(root, os.path.join(os.path.dirname(member.name), member.linkname))
            if hasattr(tarfile, "data_filter"):
                tf.extractall(root, members=members, filter="data")
            else:
                tf.extractall(root, members=members)
        _flatten(root)
        os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
        import shutil

        shutil.copytree(root, dest)


def fetch_tag(origin: str, tag: str, dest: str, api: str | None = None, poll: float = POLL_SECONDS) -> str:
    """Fetch *tag* of *origin* from Software Heritage into *dest*; returns its directory (git tree) id."""
    directory = directory_of(origin, tag, api)
    fetch_directory(directory, dest, api, poll)
    return directory
