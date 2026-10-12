"""Tests for fobis.llm.models — the model store, against a local fake Hugging Face Hub and CDN.

Two real HTTP servers on loopback: the "hub" (revision and tree APIs, ``resolve/`` answering 302) and the
"cdn" it redirects to (file bytes with ``Range`` support). Real sockets, so redirects, resume and the scoping
of the ``Authorization`` header are exercised as urllib really behaves.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from typer.testing import CliRunner

from fobis.llm import ChecksumMismatchError, ConfigError, DownloadError, ModelMissingError
from fobis.llm.models import RECOMMENDED, HubClient, ModelStore, parse_spec, split_parts

COMMIT = "a" * 40
SINGLE = b"GGUF" + bytes(range(256)) * 40
PART1, PART2 = b"GGUF" + b"x" * 3000, b"y" * 1500


class FakeHub:
    """State shared by the hub and cdn handlers."""

    def __init__(self) -> None:
        self.files = {
            "org/repo": {
                "m.gguf": SINGLE,
                "sub/q.gguf": SINGLE[:1000],
                "big-00001-of-00002.gguf": PART1,
                "big-00002-of-00002.gguf": PART2,
                "plain.gguf": None,  # not in LFS
            }
        }
        self.gated = {"org/gated"}
        self.requests: list[tuple[str, str, dict]] = []  # (server, path, headers)
        self.cut_after: int | None = None  # cdn closes the connection after this many bytes
        self.corrupt = False
        self.ignore_range = False
        self.cdn_url = ""
        self.endpoint = ""


def _handler(hub: FakeHub, role: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:
            pass

        def _json(self, data, status=200) -> None:
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            hub.requests.append((role, self.path, dict(self.headers)))
            parts = self.path.strip("/").split("/")
            if role == "cdn":
                return self._serve_file("/".join(parts[:2]), "/".join(parts[2:]))
            if parts[:2] == ["api", "models"]:
                repo = "/".join(parts[2:4])
                if repo in hub.gated and "Authorization" not in self.headers:
                    return self._json({"error": "gated"}, 401)
                if repo not in hub.files and repo not in hub.gated:
                    return self._json({"error": "missing"}, 404)
                if parts[4] == "revision":
                    return self._json({"sha": COMMIT, "id": repo})
                if parts[4] == "tree":
                    folder = "/".join(parts[6:])
                    entries = []
                    for path, data in hub.files.get(repo, {}).items():
                        if os.path.dirname(path) != folder:
                            continue
                        entry = {"type": "file", "path": path, "size": len(data or b"x")}
                        if data is not None:
                            entry["lfs"] = {"oid": hashlib.sha256(data).hexdigest(), "size": len(data)}
                        entries.append(entry)
                    return self._json(entries)
            if "resolve" in parts:
                at = parts.index("resolve")
                repo, file = "/".join(parts[:at]), "/".join(parts[at + 2 :])
                self.send_response(302)
                self.send_header("Location", f"{hub.cdn_url}/{repo}/{file}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return None
            return self._json({"error": "unknown"}, 404)

        def _serve_file(self, repo: str, file: str) -> None:
            data = hub.files[repo][file]
            if hub.corrupt:
                data = data[:-1] + b"!"
            start = 0
            ranged = self.headers.get("Range")
            if ranged and not hub.ignore_range:
                start = int(ranged.split("=")[1].rstrip("-"))
                self.send_response(206)
            else:
                self.send_response(200)
            body = data[start:]
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if hub.cut_after is not None:
                self.wfile.write(body[: hub.cut_after])
                self.wfile.flush()
                self.connection.close()
                hub.cut_after = None
                return
            self.wfile.write(body)

    return Handler


@pytest.fixture
def hub():
    state = FakeHub()
    servers = []
    for role in ("hub", "cdn"):
        server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(state, role))
        threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
        servers.append(server)
    state.cdn_url = f"http://localhost:{servers[1].server_port}"  # another host name, like the real CDN
    state.endpoint = f"http://127.0.0.1:{servers[0].server_port}"
    yield state
    for server in servers:
        server.shutdown()
        server.server_close()


@pytest.fixture
def store(hub, tmp_path):
    return ModelStore(root=str(tmp_path), hub=HubClient(endpoint=hub.endpoint, timeout=5))


def test_parse_spec_forms(tmp_path):
    spec = parse_spec("hf:org/repo@v1.0/sub/m.gguf")
    assert (spec.repo, spec.revision, spec.file) == ("org/repo", "v1.0", "sub/m.gguf")
    assert str(parse_spec("hf:org/repo/m.gguf")) == "hf:org/repo/m.gguf"
    assert parse_spec("coder-7b").revision == RECOMMENDED["coder-7b"].spec.split("@")[1].split("/")[0]
    local = parse_spec(str(tmp_path / "x.gguf"))
    assert local.is_local and local.path == str(tmp_path / "x.gguf")
    for bad in ("hf:org/m.gguf", "hf:org/repo/readme.md", "hf://repo/m.gguf"):
        with pytest.raises(ConfigError):
            parse_spec(bad)


def test_recommended_are_pinned_and_parseable():
    for model in RECOMMENDED.values():
        spec = parse_spec(model.spec)
        assert len(spec.revision) == 40 and spec.file.endswith(".gguf") and model.license == "Apache-2.0"


def test_split_parts():
    assert split_parts("m.gguf") == ["m.gguf"]
    assert split_parts("d/m-00001-of-00003.gguf") == [f"d/m-0000{i}-of-00003.gguf" for i in (1, 2, 3)]


def test_pull_resolves_revision_verifies_and_records(store, hub):
    model, downloaded = store.pull("hf:org/repo/m.gguf")
    assert downloaded and model.revision == COMMIT and model.spec == f"hf:org/repo@{COMMIT}/m.gguf"
    with open(model.path, "rb") as handle:
        assert handle.read() == SINGLE
    assert model.path == os.path.join(store.root, "org", "repo", COMMIT, "m.gguf")
    assert not os.path.exists(model.path + ".part")
    with open(store.manifest_path) as handle:
        manifest = json.load(handle)
    assert manifest[model.spec]["parts"][0]["sha256"] == hashlib.sha256(SINGLE).hexdigest()
    count = len(hub.requests)
    assert store.pull("hf:org/repo/m.gguf")[1] is False  # second pull: nothing downloaded
    assert not [r for r in hub.requests[count:] if r[0] == "cdn"]


def test_pull_file_in_subfolder_and_locate(store):
    model, _ = store.pull("hf:org/repo/sub/q.gguf")
    assert model.path.endswith(os.path.join(COMMIT, "sub", "q.gguf"))
    assert store.locate("hf:org/repo/sub/q.gguf") == model.path
    assert store.locate(f"hf:org/repo@{COMMIT[:8]}/sub/q.gguf") == model.path


def test_pull_split_model_downloads_every_part(store):
    model, _ = store.pull("hf:org/repo/big-00001-of-00002.gguf")
    assert [os.path.basename(p["path"]) for p in model.parts] == [
        "big-00001-of-00002.gguf",
        "big-00002-of-00002.gguf",
    ]
    assert model.size == len(PART1) + len(PART2) and model.path.endswith("big-00001-of-00002.gguf")


def _read(path: str) -> bytes:
    with open(path, "rb") as handle:
        return handle.read()


def test_interrupted_download_resumes_with_range(store, hub):
    hub.cut_after = 500
    with pytest.raises(DownloadError, match="interrupted"):
        store.pull("hf:org/repo/m.gguf")
    part = os.path.join(store.root, "org", "repo", COMMIT, "m.gguf.part")
    assert os.path.getsize(part) == 500
    model, downloaded = store.pull("hf:org/repo/m.gguf")
    assert downloaded and _read(model.path) == SINGLE
    ranges = [r[2].get("Range") for r in hub.requests if r[0] == "cdn"]
    assert ranges[-1] == "bytes=500-"


def test_resume_restarts_when_the_server_ignores_range(store, hub):
    hub.cut_after = 500
    with pytest.raises(DownloadError):
        store.pull("hf:org/repo/m.gguf")
    hub.ignore_range = True
    model, _ = store.pull("hf:org/repo/m.gguf")
    assert _read(model.path) == SINGLE


def test_checksum_mismatch_deletes_the_partial_file(store, hub):
    hub.corrupt = True
    with pytest.raises(ChecksumMismatchError, match="sha256"):
        store.pull("hf:org/repo/m.gguf")
    assert os.listdir(os.path.join(store.root, "org", "repo", COMMIT)) == []
    assert store.entries() == []


def test_token_goes_to_the_hub_only(hub, tmp_path):
    store = ModelStore(root=str(tmp_path), hub=HubClient(endpoint=hub.endpoint, token="secret", timeout=5))
    store.pull("hf:org/repo/m.gguf")
    assert {r[2].get("Authorization") for r in hub.requests if r[0] == "hub"} == {"Bearer secret"}
    assert [r for r in hub.requests if r[0] == "cdn"]
    assert all("Authorization" not in r[2] for r in hub.requests if r[0] == "cdn")


def test_gated_missing_and_non_lfs_errors(store):
    with pytest.raises(DownloadError, match="HF_TOKEN"):
        store.pull("hf:org/gated/m.gguf")
    with pytest.raises(DownloadError, match="not found"):
        store.pull("hf:nobody/none/m.gguf")
    with pytest.raises(DownloadError, match="no file"):
        store.pull("hf:org/repo/absent.gguf")
    with pytest.raises(DownloadError, match="LFS"):
        store.pull("hf:org/repo/plain.gguf")
    with pytest.raises(ConfigError, match="local file"):
        store.pull("/tmp/x.gguf")


def test_unreachable_hub(tmp_path):
    import socket

    with socket.socket() as probe:  # a port nobody listens on: connection refused at once
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    store = ModelStore(root=str(tmp_path), hub=HubClient(endpoint=f"http://127.0.0.1:{port}", timeout=2))
    with pytest.raises(DownloadError, match="cannot reach"):
        store.pull("hf:org/repo/m.gguf")


def test_disk_space_is_checked_before_downloading(store, monkeypatch):
    import shutil

    monkeypatch.setattr(shutil, "disk_usage", lambda path: shutil._ntuple_diskusage(10, 10, 10))
    with pytest.raises(DownloadError, match="free"):
        store.pull("hf:org/repo/m.gguf")


def test_locate_missing_and_local(store, tmp_path):
    with pytest.raises(ModelMissingError, match=re.escape("fobis llm pull hf:org/repo/m.gguf")):
        store.locate("hf:org/repo/m.gguf")
    with pytest.raises(ModelMissingError, match="does not exist"):
        store.locate(str(tmp_path / "none.gguf"))
    local = tmp_path / "mine.gguf"
    local.write_bytes(b"GGUF")
    assert store.locate(str(local)) == str(local)


def test_remove_deletes_files_entry_and_empty_directories(store):
    store.pull("hf:org/repo/m.gguf")
    store.pull("hf:org/repo/sub/q.gguf")
    removed = store.remove("hf:org/repo/m.gguf")
    assert [m.file for m in removed] == ["m.gguf"]
    assert [m.file for m in store.entries()] == ["sub/q.gguf"]
    store.remove("hf:org/repo/sub/q.gguf")
    assert store.entries() == [] and os.listdir(store.root) == ["manifest.json"]
    with pytest.raises(ModelMissingError):
        store.remove("hf:org/repo/m.gguf")


def test_corrupt_manifest_is_a_config_error(store):
    os.makedirs(store.root)
    with open(store.manifest_path, "w") as handle:
        handle.write("{not json")
    with pytest.raises(ConfigError, match="manifest"):
        store.entries()


def test_hub_client_from_env(monkeypatch):
    monkeypatch.setenv("HF_ENDPOINT", "https://mirror.example/")
    monkeypatch.setenv("HF_TOKEN", " tok ")
    client = HubClient.from_env()
    assert client.endpoint == "https://mirror.example" and client.token == "tok"
    monkeypatch.delenv("HF_ENDPOINT")
    monkeypatch.delenv("HF_TOKEN")
    assert HubClient.from_env().token is None


def test_cli_pull_list_rm_recommended(hub, tmp_path, monkeypatch):
    from fobis.cli import app

    monkeypatch.setenv("FOBIS_LLM_DIR", str(tmp_path))
    monkeypatch.setenv("HF_ENDPOINT", hub.endpoint)
    monkeypatch.delenv("HF_TOKEN", raising=False)
    runner = CliRunner()
    out = runner.invoke(app, ["llm", "recommended"]).output
    assert "coder-7b" in out and "Apache-2.0" in out
    assert "No model" in runner.invoke(app, ["llm", "list"]).output
    result = runner.invoke(app, ["llm", "pull", "hf:org/repo/m.gguf"])
    assert result.exit_code == 0 and "Pulled hf:org/repo@" in result.output
    assert "Already in the store" in runner.invoke(app, ["llm", "pull", "hf:org/repo/m.gguf"]).output
    rows = json.loads(runner.invoke(app, ["llm", "list", "--json"]).output)
    assert rows[0]["size"] == len(SINGLE) and rows[0]["revision"] == COMMIT
    assert "Removed" in runner.invoke(app, ["llm", "rm", "hf:org/repo/m.gguf"]).output
    failed = runner.invoke(app, ["llm", "pull", "hf:org/gated/m.gguf"])
    assert failed.exit_code == 1 and "HF_TOKEN" in failed.output
