"""models.py — the local model store: GGUF files pulled from the Hugging Face Hub, pinned and verified.

A model is named by a *spec*: ``hf:<org>/<repo>[@<revision>]/<path/to/file>.gguf``, a local GGUF path, or an
alias of `RECOMMENDED`. Pulling resolves the revision to a commit hash (so the pin is always concrete), reads
the expected sha256 and size of each file from the Hub tree API, downloads with resume (``.part`` file and
HTTP ``Range``), verifies, and records the result in ``models/manifest.json``. Split GGUFs
(``-00001-of-0000N.gguf``) are pulled part by part; the spec names the first part, as llama.cpp expects.

Nothing is downloaded implicitly: only `ModelStore.pull` downloads, and the CLI calls it only for
``fobis llm pull``. ``HF_TOKEN`` (gated repositories) is sent to the Hub endpoint only: the header is not
forwarded when the Hub redirects a download to its CDN.
"""

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

import hashlib
import http.client
import json
import os
import posixpath
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field

from .errors import ChecksumMismatchError, ConfigError, DownloadError, ModelMissingError

DEFAULT_ENDPOINT = "https://huggingface.co"
CHUNK = 1 << 20
_SPLIT_RE = re.compile(r"^(?P<stem>.*)-(?P<index>\d{5})-of-(?P<count>\d{5})\.gguf$")
_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")

Progress = Callable[[str, int, int], None]  # (file name, bytes done, bytes total)


@dataclass(frozen=True)
class Recommended:
    """A curated model: alias, pinned spec, download size, licence, what it is good for."""

    alias: str
    spec: str
    size: int
    license: str
    note: str


RECOMMENDED: dict[str, Recommended] = {
    r.alias: r
    for r in (
        Recommended(
            "coder-0.5b",
            "hf:Qwen/Qwen2.5-Coder-0.5B-Instruct-GGUF@ebb2015119c907b064c512bf053e945850b5875f/"
            "qwen2.5-coder-0.5b-instruct-q4_k_m.gguf",
            491_400_064,
            "Apache-2.0",
            "smoke tests, laptops without GPU; weak at reasoning",
        ),
        Recommended(
            "coder-1.5b",
            "hf:Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF@f86cb2c1fa58255f8052cc32aeede1b7482d4361/"
            "qwen2.5-coder-1.5b-instruct-q4_k_m.gguf",
            1_117_320_768,
            "Apache-2.0",
            "commit messages on CPU",
        ),
        Recommended(
            "coder-7b",
            "hf:Qwen/Qwen2.5-Coder-7B-Instruct-GGUF@13fb94bfda8c8cf22497dc57b78f391a9acb426a/"
            "qwen2.5-coder-7b-instruct-q4_k_m.gguf",
            4_683_073_536,
            "Apache-2.0",
            "default choice: 8 GB GPU, or a recent CPU",
        ),
        Recommended(
            "coder-14b",
            "hf:Qwen/Qwen2.5-Coder-14B-Instruct-GGUF@d0a692ef765eefbf2fabb130b3cb2e8917e3d225/"
            "qwen2.5-coder-14b-instruct-q4_k_m.gguf",
            8_988_110_272,
            "Apache-2.0",
            "12-16 GB GPU",
        ),
        Recommended(
            "coder-30b-a3b",
            "hf:unsloth/Qwen3-Coder-30B-A3B-Instruct-GGUF@b17cb02dd882d5b6ab62fc777ad2995f19668350/"
            "Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf",
            18_556_689_568,
            "Apache-2.0",
            "24 GB GPU; mixture of experts (3B active), fast for its size",
        ),
    )
}


@dataclass(frozen=True)
class ModelSpec:
    """A parsed model spec: a Hub file (``repo``, ``revision``, ``file``) or a local ``path``."""

    repo: str = ""
    revision: str | None = None
    file: str = ""
    path: str = ""

    @property
    def is_local(self) -> bool:
        return bool(self.path)

    def __str__(self) -> str:
        if self.is_local:
            return self.path
        rev = f"@{self.revision}" if self.revision else ""
        return f"hf:{self.repo}{rev}/{self.file}"


def parse_spec(text: str) -> ModelSpec:
    """Parse *text*: an alias of `RECOMMENDED`, ``hf:<org>/<repo>[@<rev>]/<file>.gguf`` or a local path.

    Raises
    ------
    ConfigError
        A ``hf:`` spec that is malformed or does not name a ``.gguf`` file.
    """
    text = text.strip()
    if text in RECOMMENDED:
        text = RECOMMENDED[text].spec
    if not text.startswith("hf:"):
        return ModelSpec(path=os.path.abspath(os.path.expanduser(text)))
    parts = text[3:].split("/")
    if len(parts) < 3 or not parts[0] or not parts[1] or not all(parts[2:]):
        raise ConfigError(f"model spec {text!r}: expected hf:<org>/<repo>[@<revision>]/<file>.gguf")
    repo_name, _, revision = parts[1].partition("@")
    file = "/".join(parts[2:])
    if not file.lower().endswith(".gguf"):
        raise ConfigError(f"model spec {text!r}: the file must be a .gguf")
    return ModelSpec(repo=f"{parts[0]}/{repo_name}", revision=revision or None, file=file)


def split_parts(file: str) -> list[str]:
    """The files of a split GGUF named by its first part (``x-00001-of-00003.gguf``); ``[file]`` otherwise."""
    match = _SPLIT_RE.match(file)
    if not match:
        return [file]
    count = int(match.group("count"))
    return [f"{match.group('stem')}-{i:05d}-of-{count:05d}.gguf" for i in range(1, count + 1)]


@dataclass
class HubClient:
    """Minimal Hugging Face Hub client (stdlib).

    Attributes
    ----------
    endpoint : str
        Hub base URL (``HF_ENDPOINT`` for mirrors).
    token : str or None
        Access token for gated repositories, sent as ``Authorization: Bearer`` to *endpoint* only.
    urlopen : callable
        ``urlopen(request, timeout=...)``; injectable for tests.
    timeout : float
        Socket timeout in seconds.
    """

    endpoint: str = DEFAULT_ENDPOINT
    token: str | None = None
    urlopen: Callable = field(default=urllib.request.urlopen)
    timeout: float = 60.0

    @classmethod
    def from_env(cls) -> HubClient:
        """Client configured by ``HF_ENDPOINT`` and ``HF_TOKEN``."""
        endpoint = os.environ.get("HF_ENDPOINT", "").strip().rstrip("/") or DEFAULT_ENDPOINT
        return cls(endpoint=endpoint, token=os.environ.get("HF_TOKEN", "").strip() or None)

    def _request(self, url: str, headers: dict[str, str] | None = None) -> urllib.request.Request:
        request = urllib.request.Request(url, headers=headers or {})
        request.add_header("User-Agent", "fobis-llm")
        if self.token:
            # Unredirected: urllib does not forward it when the Hub redirects the download to its CDN.
            request.add_unredirected_header("Authorization", f"Bearer {self.token}")
        return request

    def _open(self, url: str, headers: dict[str, str] | None = None):
        try:
            return self.urlopen(self._request(url, headers), timeout=self.timeout)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                hint = (
                    "the repository is gated or private: accept its licence on the Hub and set HF_TOKEN"
                    if not self.token
                    else "HF_TOKEN is not authorised for this repository (licence not accepted?)"
                )
                raise DownloadError(f"{url}: HTTP {exc.code}: {hint}") from exc
            if exc.code == 404:
                raise DownloadError(f"{url}: not found (check the repository, revision and file name)") from exc
            raise DownloadError(f"{url}: HTTP {exc.code} {exc.reason}") from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            reason = getattr(exc, "reason", exc)
            raise DownloadError(f"cannot reach {url}: {reason}") from exc

    def _json(self, url: str):
        with self._open(url) as response:
            return json.loads(response.read().decode())

    def resolve_revision(self, repo: str, revision: str | None) -> str:
        """The commit hash of *revision* (a branch, tag or hash; ``main`` when None)."""
        if revision and _SHA1_RE.match(revision):
            return revision
        quoted = urllib.parse.quote(revision or "main", safe="")
        data = self._json(f"{self.endpoint}/api/models/{repo}/revision/{quoted}")
        sha = data.get("sha", "") if isinstance(data, dict) else ""
        if not _SHA1_RE.match(sha):
            raise DownloadError(f"{repo}@{revision or 'main'}: the Hub returned no commit hash")
        return sha

    def file_info(self, repo: str, commit: str, file: str) -> tuple[int, str]:
        """(size, sha256) of *file* at *commit*, from the tree API (LFS object id)."""
        folder = posixpath.dirname(file)
        url = f"{self.endpoint}/api/models/{repo}/tree/{commit}" + (f"/{urllib.parse.quote(folder)}" if folder else "")
        for entry in self._json(url):
            if entry.get("path") == file:
                lfs = entry.get("lfs") or {}
                if not lfs.get("oid"):
                    raise DownloadError(f"{repo}/{file}: not stored with LFS, no sha256 to verify against")
                return int(lfs.get("size", entry.get("size", 0))), lfs["oid"]
        raise DownloadError(f"{repo}@{commit[:12]}: no file {file!r}")

    def download(
        self,
        repo: str,
        commit: str,
        file: str,
        dest: str,
        size: int,
        sha256: str,
        progress: Progress | None = None,
    ) -> None:
        """Download *file* to *dest*, resuming ``dest.part``; verify *size* and *sha256*.

        Raises
        ------
        DownloadError
            HTTP or network failure (the ``.part`` file is kept for a later resume).
        ChecksumMismatchError
            The completed file does not match; the ``.part`` file is deleted.
        """
        part = dest + ".part"
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        digest = hashlib.sha256()
        done = 0
        if os.path.exists(part):
            done = os.path.getsize(part)
            if done > size:
                os.remove(part)
                done = 0
            else:
                with open(part, "rb") as handle:
                    for block in iter(lambda: handle.read(CHUNK), b""):
                        digest.update(block)
        name = posixpath.basename(file)
        if done < size:
            url = f"{self.endpoint}/{repo}/resolve/{commit}/{urllib.parse.quote(file)}"
            with self._open(url, {"Range": f"bytes={done}-"} if done else None) as response:
                if done and getattr(response, "status", 200) != 206:
                    done, digest = 0, hashlib.sha256()  # the server ignored the range: start over
                with open(part, "ab" if done else "wb") as handle:
                    try:
                        for block in iter(lambda: response.read(CHUNK), b""):
                            handle.write(block)
                            digest.update(block)
                            done += len(block)
                            if progress:
                                progress(name, done, size)
                    except (http.client.HTTPException, OSError) as exc:
                        raise DownloadError(
                            f"{repo}/{file}: download interrupted after {done} of {size} bytes ({exc!r}); "
                            "pull again to resume"
                        ) from exc
        if done < size:  # the connection ended early without an error (urllib returns b"")
            raise DownloadError(
                f"{repo}/{file}: download interrupted after {done} of {size} bytes; pull again to resume"
            )
        if done != size or digest.hexdigest() != sha256:
            os.remove(part)
            raise ChecksumMismatchError(
                f"{repo}/{file}: got {done} bytes with sha256 {digest.hexdigest()[:16]}..., expected {size} bytes "
                f"with sha256 {sha256[:16]}...; the partial file was deleted, pull again"
            )
        os.replace(part, dest)


def default_root() -> str:
    """The LLM directory: ``$FOBIS_LLM_DIR`` or ``~/.fobis/llm``."""
    return os.path.abspath(os.path.expanduser(os.environ.get("FOBIS_LLM_DIR") or os.path.join("~", ".fobis", "llm")))


@dataclass
class StoredModel:
    """A pulled model as recorded in the manifest."""

    spec: str
    repo: str
    revision: str
    file: str
    parts: list[dict]
    pulled_at: str

    @property
    def path(self) -> str:
        """Path of the first (or only) file: what llama-server's ``-m`` takes."""
        return self.parts[0]["path"]

    @property
    def size(self) -> int:
        return sum(p["size"] for p in self.parts)


class ModelStore:
    """The models directory and its manifest.

    Parameters
    ----------
    root : str or None
        LLM directory (`default_root` when None); models live in ``<root>/models``.
    hub : HubClient or None
        Hub client (`HubClient.from_env` when None).
    """

    def __init__(self, root: str | None = None, hub: HubClient | None = None) -> None:
        self.root = os.path.join(root or default_root(), "models")
        self.hub = hub or HubClient.from_env()

    @property
    def manifest_path(self) -> str:
        return os.path.join(self.root, "manifest.json")

    def _load(self) -> dict:
        try:
            with open(self.manifest_path, encoding="utf-8") as handle:
                data = json.load(handle)
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            raise ConfigError(f"unreadable model manifest {self.manifest_path}: {exc}") from exc
        return data if isinstance(data, dict) else {}

    def _save(self, data: dict) -> None:
        os.makedirs(self.root, exist_ok=True)
        tmp = self.manifest_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp, self.manifest_path)

    def entries(self) -> list[StoredModel]:
        """The pulled models, sorted by spec."""
        return [StoredModel(spec=spec, **entry) for spec, entry in sorted(self._load().items())]

    def _match(self, spec: ModelSpec) -> list[StoredModel]:
        """Stored models matching *spec*; a spec without revision matches every stored revision."""
        found = []
        for model in self.entries():
            if model.repo != spec.repo or model.file != spec.file:
                continue
            if spec.revision is None or model.revision.startswith(spec.revision):
                found.append(model)
        return found

    def locate(self, text: str) -> str:
        """Path of the GGUF named by *text* (alias, spec or local path), without downloading anything.

        Raises
        ------
        ModelMissingError
            The model is not in the store (the message gives the ``fobis llm pull`` command to run) or the
            local file is missing.
        """
        spec = parse_spec(text)
        if spec.is_local:
            if not os.path.isfile(spec.path):
                raise ModelMissingError(f"model file {spec.path} does not exist")
            return spec.path
        for model in self._match(spec):
            if all(os.path.isfile(p["path"]) for p in model.parts):
                return model.path
        raise ModelMissingError(f"model {text} is not in the store {self.root}: run 'fobis llm pull {text}'")

    def pull(self, text: str, progress: Progress | None = None) -> tuple[StoredModel, bool]:
        """Download the model named by *text* unless already stored; returns (model, downloaded).

        Raises
        ------
        ConfigError
            *text* names a local file (nothing to pull).
        DownloadError, ChecksumMismatchError
            See `HubClient.download`; also when the disk has no room for the download.
        """
        spec = parse_spec(text)
        if spec.is_local:
            raise ConfigError(f"{spec.path} is a local file: use it directly, there is nothing to pull")
        commit = self.hub.resolve_revision(spec.repo, spec.revision)
        resolved = str(ModelSpec(repo=spec.repo, revision=commit, file=spec.file))
        existing = self._load().get(resolved)
        if existing and all(os.path.isfile(p["path"]) for p in existing["parts"]):
            return StoredModel(spec=resolved, **existing), False
        files = split_parts(spec.file)
        infos = [self.hub.file_info(spec.repo, commit, f) for f in files]
        directory = os.path.join(self.root, *spec.repo.split("/"), commit)
        os.makedirs(directory, exist_ok=True)
        missing = sum(
            size - _partial(_dest(directory, f))
            for f, (size, _) in zip(files, infos, strict=True)
            if not os.path.isfile(_dest(directory, f))
        )
        free = shutil.disk_usage(directory).free
        if missing > free:
            raise DownloadError(f"{missing / 1e9:.1f} GB to download but only {free / 1e9:.1f} GB free in {directory}")
        parts = []
        for f, (size, sha256) in zip(files, infos, strict=True):
            dest = _dest(directory, f)
            if not os.path.isfile(dest):
                self.hub.download(spec.repo, commit, f, dest, size, sha256, progress)
            parts.append({"path": dest, "sha256": sha256, "size": size})
        entry = {
            "repo": spec.repo,
            "revision": commit,
            "file": spec.file,
            "parts": parts,
            "pulled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        data = self._load()
        data[resolved] = entry
        self._save(data)
        return StoredModel(spec=resolved, **entry), True

    def remove(self, text: str) -> list[StoredModel]:
        """Delete the stored models matching *text* (files, manifest entries, empty directories).

        Raises
        ------
        ModelMissingError
            Nothing matches.
        """
        spec = parse_spec(text)
        matches = [] if spec.is_local else self._match(spec)
        if not matches:
            raise ModelMissingError(f"no stored model matches {text}")
        data = self._load()
        for model in matches:
            for part in model.parts:
                for path in (part["path"], part["path"] + ".part"):
                    if os.path.exists(path):
                        os.remove(path)
            data.pop(model.spec, None)
            _prune(os.path.dirname(model.path), self.root)
        self._save(data)
        return matches


def _dest(directory: str, file: str) -> str:
    return os.path.join(directory, *file.split("/"))


def _partial(dest: str) -> int:
    """Bytes already downloaded into ``dest.part``."""
    return os.path.getsize(dest + ".part") if os.path.exists(dest + ".part") else 0


def _prune(directory: str, stop: str) -> None:
    """Remove *directory* and its parents up to *stop* (excluded) while they are empty."""
    stop = os.path.abspath(stop)
    directory = os.path.abspath(directory)
    while directory.startswith(stop + os.sep) and os.path.isdir(directory) and not os.listdir(directory):
        os.rmdir(directory)
        directory = os.path.dirname(directory)
